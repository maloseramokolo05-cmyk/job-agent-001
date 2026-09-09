from __future__ import annotations

from agents.models import Job
from .base import JobSource
from .http import safe_get


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def search(self, profile, preferences):
        jobs = []
        for board in preferences.get("greenhouse_boards", []):
            data = safe_get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true").json()
            for item in data.get("jobs", []):
                location = item.get("location", {}).get("name", "")
                body = item.get("content", "")
                jobs.append(Job(
                    title=item.get("title", "Untitled vacancy"), company=board.replace("-", " ").title(),
                    location=location, source=self.name, vacancy_url=item.get("absolute_url", ""),
                    vacancy_id=str(item.get("id", "")), application_url=item.get("absolute_url", ""),
                    description=body, requirements=body, date_posted=item.get("updated_at"),
                ))
        return jobs
