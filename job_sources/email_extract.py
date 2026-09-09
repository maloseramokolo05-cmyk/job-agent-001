from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .http import safe_get

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
APPLICATION_WORDS = (
    "apply", "application", "applicants", "candidate", "candidates", "cv", "resume",
    "send", "submit", "email", "vacancy", "recruitment", "recruiter", "careers",
)
REJECT_LOCAL_PARTS = {"noreply", "no-reply", "donotreply", "do-not-reply", "privacy", "webmaster"}


def _clean_email(value: str) -> str:
    return value.strip().strip(".,;:()[]{}<>\"'").lower()


def extract_application_email(text: str) -> tuple[str, str] | tuple[None, None]:
    """Return (email, evidence_excerpt) only when the email appears in application context."""
    if not text:
        return None, None
    for match in EMAIL_RE.finditer(text):
        email = _clean_email(match.group(0))
        local = email.split("@", 1)[0]
        if local in REJECT_LOCAL_PARTS:
            continue
        start = max(0, match.start() - 240)
        end = min(len(text), match.end() + 240)
        context = " ".join(text[start:end].split())
        lowered = context.lower()
        if not any(word in lowered for word in APPLICATION_WORDS):
            continue
        return email, context[:500]
    return None, None


def enrich_email_route(job):
    """Verify an email against the original public vacancy page.

    The method never follows login walls or redirects and never treats an email discovered on an
    unrelated page as an application route.
    """
    page_text = f"{job.description}\n{job.requirements}"
    email, evidence = extract_application_email(page_text)
    source_url = job.vacancy_url
    if not email and source_url:
        try:
            response = safe_get(source_url, timeout=20)
            if "text/html" in response.headers.get("content-type", "").lower():
                from bs4 import BeautifulSoup

                page_text = BeautifulSoup(response.text, "html.parser").get_text("\n", strip=True)
                email, evidence = extract_application_email(page_text)
        except Exception:
            email = None
    if email:
        parsed = urlparse(source_url)
        job.application_email = email
        job.application_method = "EMAIL"
        job.email_verified = True
        job.email_source_url = source_url
        job.verified_at = datetime.now(timezone.utc).isoformat()
        job.metadata = {**job.metadata, "email_evidence": evidence or "", "source_host": parsed.hostname or ""}
    elif source_url:
        job.verified_at = datetime.now(timezone.utc).isoformat()
    return job
