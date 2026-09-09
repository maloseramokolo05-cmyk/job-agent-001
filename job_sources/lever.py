from __future__ import annotations

from agents.models import Job
from .base import JobSource
from .http import safe_get


class LeverSource(JobSource):
    name = "lever"

    def search(self, profile, preferences):
        jobs = []
        for site in preferences.get("lever_sites", []):
            for item in safe_get(f"https://api.lever.co/v0/postings/{site}?mode=json").json():
                categories = item.get("categories", {})
                body = item.get("descriptionPlain", "") + "\n" + "\n".join(
                    entry.get("content", "") for entry in item.get("lists", [])
                )
                jobs.append(Job(
                    title=item.get("text", "Untitled vacancy"), company=site.replace("-", " ").title(),
                    location=categories.get("location", ""), source=self.name,
                    vacancy_url=item.get("hostedUrl", ""), application_url=item.get("applyUrl", ""),
                    vacancy_id=item.get("id", ""), description=body, requirements=body,
                    work_mode=categories.get("workplaceType", ""),
                ))
        return jobs
