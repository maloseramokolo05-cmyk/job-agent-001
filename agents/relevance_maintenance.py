from __future__ import annotations

import hashlib
import json

from agents.repository import update_analysis
from agents.scoring import score_job
from backend.database import connect, row, rows


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

RELEVANCE_ALGORITHM_VERSION = "2026-09-product-audit-1"
STATE_KEY = "relevance_rescore_state"


def _fingerprint(fit: dict, preferences: dict) -> str:
    relevant_preferences = {
        "job_categories": preferences.get("job_categories", []),
        "priority_locations": preferences.get("priority_locations", []),
        "minimum_score": preferences.get("minimum_score"),
        "email_minimum_score": preferences.get("email_minimum_score"),
        "allow_other_sa_locations": preferences.get("allow_other_sa_locations"),
    }
    payload = json.dumps(
        {
            "algorithm": RELEVANCE_ALGORITHM_VERSION,
            "candidate": fit.get("fingerprint"),
            "preferences": relevant_preferences,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rescore_existing(profile: dict, preferences: dict, master: str, fit: dict) -> dict:
    """Re-score existing jobs only when candidate/relevance inputs changed.

    Applied/historical outcomes are never rewritten. This avoids spending most
    of every search run re-scoring an unchanged database.
    """
    fingerprint = _fingerprint(fit, preferences)
    cached = row("SELECT value FROM settings WHERE key=?", (STATE_KEY,))
    if cached:
        try:
            value = json.loads(cached["value"])
            if value.get("fingerprint") == fingerprint:
                return {
                    "evaluated": 0,
                    "changed": 0,
                    "downgraded": 0,
                    "upgraded": 0,
                    "samples": [],
                    "skipped": True,
                    "reason": "candidate profile and scoring algorithm unchanged",
                }
        except (TypeError, json.JSONDecodeError):
            pass

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

    with connect() as db:
        payload = json.dumps({"fingerprint": fingerprint, "algorithm": RELEVANCE_ALGORITHM_VERSION})
        db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (STATE_KEY, payload),
        )

    return {
        "evaluated": len(jobs),
        "changed": changed,
        "downgraded": downgraded,
        "upgraded": upgraded,
        "samples": samples,
        "skipped": False,
    }
