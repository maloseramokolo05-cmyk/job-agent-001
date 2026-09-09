from __future__ import annotations

import os
import time

from agents.models import Job
from .base import JobSource
from .http import safe_get
from .relevance import board_company_name, south_africa_relevant


class LeverSource(JobSource):
    name = "lever"

    def search(self, profile, preferences):
        jobs = []
        limit = int(preferences.get("max_jobs_per_source", 60))
        deadline = time.monotonic() + float(os.getenv("SOURCE_TIME_BUDGET_SECONDS", "40"))
        for site in preferences.get("lever_sites", []):
            if len(jobs) >= limit or time.monotonic() >= deadline:
                break
            for item in safe_get(f"https://api.lever.co/v0/postings/{site}?mode=json", timeout=12).json():
                categories = item.get("categories", {})
                body = item.get("descriptionPlain", "") + "\n" + "\n".join(
                    entry.get("content", "") for entry in item.get("lists", [])
                )
                location = categories.get("location", "")
                if not south_africa_relevant(location, body):
                    continue
                jobs.append(Job(
                    title=item.get("text", "Untitled vacancy"), company=board_company_name(site),
                    location=location, source=self.name,
                    vacancy_url=item.get("hostedUrl", ""), application_url=item.get("applyUrl", ""),
                    vacancy_id=item.get("id", ""), description=body, requirements=body,
                    work_mode=categories.get("workplaceType", ""),
                ))
                if len(jobs) >= limit:
                    break
        return jobs
