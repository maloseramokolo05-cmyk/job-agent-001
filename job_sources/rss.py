import os
import time

from defusedxml import ElementTree as ET

from agents.models import Job
from agents.parsers import clean
from .base import JobSource
from .email_extract import enrich_email_route
from .http import safe_get


class RSSSource(JobSource):
    name = "configured-rss"

    def search(self, profile, preferences):
        jobs = []
        limit = int(preferences.get("max_jobs_per_source", 60))
        deadline = time.monotonic() + float(os.getenv("SOURCE_TIME_BUDGET_SECONDS", "40"))
        for feed in preferences.get("search_feeds", []):
            if len(jobs) >= limit or time.monotonic() >= deadline:
                break
            response = safe_get(feed, timeout=12)
            for item in ET.fromstring(response.content).findall(".//item"):
                if len(jobs) >= limit:
                    break
                get = lambda name: clean(item.findtext(name, ""))
                url = get("link")
                job = Job(
                    title=get("title") or "Untitled vacancy",
                    company=get("author") or "South Africa vacancy source",
                    location="South Africa",
                    source=self.name,
                    vacancy_url=url,
                    description=get("description"),
                    requirements=get("description"),
                    application_url=url,
                    vacancy_id=get("guid") or url,
                    date_posted=get("pubDate"),
                )
                jobs.append(enrich_email_route(job))
        return jobs
