from __future__ import annotations

from agents.repository import update_analysis
from agents.scoring import score_job
from backend.database import rows


PROTECTED_HISTORY = {
    "APPLIED",
    "APPLIED_CONFIRMED",
    "INTERVIEW",
    "ASSESSMENT",
    "OFFER",
    "REJECTED",
    "WITHDRAWN",
    "EXPIRED",
}


def rescore_existing(profile: dict, preferences: dict, master: str, fit: dict) -> dict:
    """Re-score existing jobs without rewriting application history.

    Applied/historical outcomes are left untouched. For workflow states such as
    PREPARED/NEEDS_USER_ACTION we update fit metadata but preserve the status.
    Only DISCOVERED/SHORTLISTED are reclassified based on the new fit score.
    """
    jobs = rows(
        "SELECT j.* FROM jobs j "
        "WHERE j.status NOT IN ('APPLIED','APPLIED_CONFIRMED','INTERVIEW','ASSESSMENT','OFFER','REJECTED','WITHDRAWN','EXPIRED') "
        "AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id=j.id AND a.status IN ('APPLIED','APPLIED_CONFIRMED'))"
    )
    changed = 0
    downgraded = 0
    upgraded = 0
    samples = []
    for job in jobs:
        old_score = float(job.get("score") or 0)
        result = score_job(job, profile, preferences, master, fit_profile=fit)
        new_score = float(result["score"])
        status = job.get("status") or "DISCOVERED"
        if status in {"DISCOVERED", "SHORTLISTED"}:
            status = "SHORTLISTED" if new_score >= 70 else "DISCOVERED"
        update_analysis(job["id"], result, status)
        if abs(new_score - old_score) >= 0.1:
            changed += 1
            if new_score < old_score:
                downgraded += 1
            elif new_score > old_score:
                upgraded += 1
            if len(samples) < 12 and abs(new_score - old_score) >= 15:
                samples.append({
                    "id": job["id"],
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "old_score": old_score,
                    "new_score": new_score,
                    "classification": result["classification"],
                    "reason": result.get("rejection_reason") or result.get("fit_reason"),
                })
    return {
        "evaluated": len(jobs),
        "changed": changed,
        "downgraded": downgraded,
        "upgraded": upgraded,
        "samples": samples,
    }
