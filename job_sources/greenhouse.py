from __future__ import annotations

import os
import time

from bs4 import BeautifulSoup

from agents.models import Job
from .base import JobSource
from .http import safe_get
from .relevance import board_company_name, south_africa_relevant


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def search(self, profile, preferences):
        jobs = []
        limit = int(preferences.get("max_jobs_per_source", 60))
        deadline = time.monotonic() + float(os.getenv("SOURCE_TIME_BUDGET_SECONDS", "40"))
        for board in preferences.get("greenhouse_boards", []):
            if len(jobs) >= limit or time.monotonic() >= deadline:
                break
            data = safe_get(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", timeout=12
            ).json()
            for item in data.get("jobs", []):
                location = item.get("location", {}).get("name", "")
                body = BeautifulSoup(item.get("content", ""), "html.parser").get_text("\n", strip=True)
                if not south_africa_relevant(location, body):
                    continue
                jobs.append(Job(
                    title=item.get("title", "Untitled vacancy"), company=board_company_name(board),
                    location=location, source=self.name, vacancy_url=item.get("absolute_url", ""),
                    vacancy_id=str(item.get("id", "")), application_url=item.get("absolute_url", ""),
                    description=body, requirements=body, date_posted=item.get("updated_at"),
                ))
                if len(jobs) >= limit:
                    break
        return jobs
