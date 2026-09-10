from __future__ import annotations

import os
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agents.models import Job
from agents.parsers import clean
from backend.database import rows
from .base import JobSource
from .email_extract import enrich_email_route
from .http import safe_get

BASE = "https://www.careers24.com"
LOCATION_LADDER = [
    "Pretoria",
    "Centurion",
    "Midrand",
    "Johannesburg",
    "Sandton",
    "Randburg",
    "Gauteng",
    "South Africa",
]


def _section(text: str) -> str:
    """Keep vacancy content and remove Careers24 navigation/recommendation noise."""
    start_markers = ("Vacancy Details", "Job Description:", "Job Description", "Candidate Requirements")
    start = 0
    for marker in start_markers:
        pos = text.lower().find(marker.lower())
        if pos >= 0:
            start = pos
            break
    cleaned = text[start:]
    stop_markers = (
        "Similar Jobs",
        "More Jobs at",
        "About Careers24.com",
        "Recruiters Directory",
        "Follow Us",
        "© Careers24",
    )
    cut = len(cleaned)
    for marker in stop_markers:
        pos = cleaned.lower().find(marker.lower())
        if pos >= 0:
            cut = min(cut, pos)
    cleaned = cleaned[:cut]
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_between(text: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> str:
    lower = text.lower()
    start = -1
    marker_len = 0
    for marker in starts:
        pos = lower.find(marker.lower())
        if pos >= 0 and (start < 0 or pos < start):
            start = pos
            marker_len = len(marker)
    if start < 0:
        return ""
    body = text[start + marker_len :]
    body_lower = body.lower()
    end = len(body)
    for marker in stops:
        pos = body_lower.find(marker.lower())
        if pos >= 0:
            end = min(end, pos)
    return clean(body[:end])


class Careers24Source(JobSource):
    """Public Careers24 discovery with clean vacancy extraction.

    Browser-form application remains manual. Explicit application emails can be
    verified separately by the email application service.
    """

    name = "careers24"
    application_supported = False

    def _locations(self, preferences):
        values = []
        for location in list(preferences.get("priority_locations") or []) + LOCATION_LADDER:
            value = clean(str(location))
            if value and value.lower() not in {item.lower() for item in values}:
                values.append(value)
        return values

    def _listing_urls(self, preferences):
        queries = preferences.get("careers24_queries") or ["marketing", "administrator"]
        seen = set()
        # Breadth-first: rotate through preferred locations before exhausting
        # every query in one city. This makes duplicate-only runs expand sooner.
        for query in queries[:24]:
            query_slug = re.sub(r"[^a-z0-9]+", "-", str(query).lower()).strip("-")
            if not query_slug:
                continue
            for location in self._locations(preferences):
                location_slug = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
                url = f"{BASE}/jobs/lc-{location_slug}/kw-{query_slug}/"
                if url not in seen:
                    seen.add(url)
                    yield url

    @staticmethod
    def _detail(url: str) -> Job | None:
        response = safe_get(url, timeout=12)
        soup = BeautifulSoup(response.text, "html.parser")
        title_node = soup.find("h1")
        title = clean(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            return None
        full_text = soup.get_text("\n", strip=True)
        vacancy_text = _section(full_text)
        header_text = full_text[: max(2500, full_text.lower().find("vacancy details") + 1)]

        employer_match = re.search(r"Employer:\s*([^\n]+)", vacancy_text, re.I)
        salary_match = re.search(r"Salary:\s*([^\n]+)", full_text[:4000], re.I)
        closing_match = re.search(r"Apply before\s+([^|\n]+)", full_text[:5000], re.I)
        posted_match = re.search(r"Posted\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})", full_text[:6000], re.I)

        location = ""
        for candidate in LOCATION_LADDER:
            if re.search(rf"\b{re.escape(candidate)}\b", header_text, re.I):
                location = candidate
                break

        description = _extract_between(
            vacancy_text,
            ("Job Description:", "Job Description", "Position Overview:"),
            ("Minimum Experience:", "Minimum Qualification:", "Minimum Requirements:", "Candidate Requirements", "Requirements:", "Skills and Attributes:"),
        )
        requirements = _extract_between(
            vacancy_text,
            ("Candidate Requirements", "Minimum Experience:", "Minimum Qualification:", "Minimum Requirements:", "Requirements:"),
            ("Apply", "Previous", "Next"),
        )
        if not description:
            description = vacancy_text[:18000]
        if not requirements:
            requirements = vacancy_text[:18000]

        company = clean(employer_match.group(1)) if employer_match else "Careers24 employer"
        work_mode = ""
        relevant = f"{title}\n{description}\n{requirements}".lower()
        if re.search(r"\bhybrid\b", relevant):
            work_mode = "hybrid"
        elif re.search(r"\bremote\b|work from home|\bwfh\b", relevant):
            work_mode = "remote"
        elif re.search(r"on[- ]?site|office[- ]?based|in[- ]?office", relevant):
            work_mode = "on-site"

        job = Job(
            title=title,
            company=company,
            location=location,
            source="careers24",
            vacancy_url=url,
            application_url=url,
            vacancy_id=url.rstrip("/").split("/")[-1],
            description=description[:30000],
            requirements=requirements[:30000],
            salary=clean(salary_match.group(1)) if salary_match else "",
            date_posted=clean(posted_match.group(1)) if posted_match else None,
            closing_date=clean(closing_match.group(1)) if closing_match else None,
            work_mode=work_mode,
            application_method="WEB",
            metadata={"login_application_may_be_required": True},
        )
        return enrich_email_route(job)

    def search(self, profile, preferences):
        if not preferences.get("careers24_enabled", True):
            return []
        limit = int(preferences.get("max_jobs_per_source", 60))
        deadline = time.monotonic() + float(os.getenv("SOURCE_TIME_BUDGET_SECONDS", "40"))
        jobs = []
        seen = set()
        known_urls = {
            item["vacancy_url"]
            for item in rows("SELECT vacancy_url FROM jobs WHERE source='careers24' AND vacancy_url IS NOT NULL")
        }
        for listing_url in self._listing_urls(preferences):
            if len(jobs) >= limit or time.monotonic() >= deadline:
                break
            try:
                response = safe_get(listing_url, timeout=12)
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception:
                continue
            links = []
            for anchor in soup.select('a[href*="/jobs/adverts/"]'):
                href = urljoin(BASE, anchor.get("href", ""))
                if href and href not in seen:
                    seen.add(href)
                    links.append(href)
            for href in links:
                if len(jobs) >= limit or time.monotonic() >= deadline:
                    break
                if href in known_urls:
                    continue
                try:
                    job = self._detail(href)
                except Exception:
                    continue
                if job:
                    jobs.append(job)
        return jobs
