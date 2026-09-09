from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agents.models import Job
from agents.parsers import clean
from .base import JobSource
from .email_extract import enrich_email_route
from .http import safe_get

BASE = "https://www.careers24.com"


class Careers24Source(JobSource):
    """Read-only discovery adapter for public Careers24 vacancy pages.

    Careers24's authenticated application flow is deliberately not automated. When the original
    vacancy itself publishes an application email, the email route is verified and may be handled by
    the separate email-application service.
    """

    name = "careers24"
    application_supported = False

    def _listing_urls(self, preferences):
        queries = preferences.get("careers24_queries") or ["marketing", "administrator"]
        locations = preferences.get("priority_locations") or ["Gauteng"]
        seen = set()
        for location in locations[:4]:
            location_slug = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
            for query in queries:
                query_slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
                url = f"{BASE}/jobs/lc-{location_slug}/kw-{query_slug}/"
                if url not in seen:
                    seen.add(url)
                    yield url

    @staticmethod
    def _detail(url: str) -> Job | None:
        response = safe_get(url, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")
        title_node = soup.find("h1")
        title = clean(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            return None
        text = soup.get_text("\n", strip=True)
        employer_match = re.search(r"Employer:\s*([^\n]+)", text, re.I)
        salary_match = re.search(r"Salary:\s*([^\n]+)", text, re.I)
        closing_match = re.search(r"Apply before\s+([^|\n]+)", text, re.I)
        location = ""
        for candidate in ("Pretoria", "Centurion", "Midrand", "Johannesburg", "Gauteng", "South Africa"):
            if re.search(rf"\b{re.escape(candidate)}\b", text, re.I):
                location = candidate
                break
        company = clean(employer_match.group(1)) if employer_match else "Careers24 employer"
        job = Job(
            title=title,
            company=company,
            location=location,
            source="careers24",
            vacancy_url=url,
            application_url=url,
            vacancy_id=url.rstrip("/").split("/")[-1],
            description=text[:30000],
            requirements=text[:30000],
            salary=clean(salary_match.group(1)) if salary_match else "",
            closing_date=clean(closing_match.group(1)) if closing_match else None,
            application_method="WEB",
            metadata={"login_application_may_be_required": True},
        )
        return enrich_email_route(job)

    def search(self, profile, preferences):
        if not preferences.get("careers24_enabled", True):
            return []
        limit = int(preferences.get("max_jobs_per_source", 60))
        jobs = []
        seen = set()
        for listing_url in self._listing_urls(preferences):
            if len(jobs) >= limit:
                break
            try:
                response = safe_get(listing_url, timeout=20)
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
                if len(jobs) >= limit:
                    break
                try:
                    job = self._detail(href)
                except Exception:
                    continue
                if job:
                    jobs.append(job)
        return jobs
