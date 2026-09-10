from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter

from agents.pipeline import cv_text
from backend.config import load_preferences
from backend.database import LATEST_SCHEMA_VERSION, row, rows, schema_version
from backend.storage import ObjectStorage
from integrations.google.token_store import TokenStore

router = APIRouter()


def _json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _human_status(value: str | None) -> str:
    return {
        "DISCOVERED": "Discovered",
        "SHORTLISTED": "Shortlisted",
        "PREPARED": "CV ready",
        "READY_TO_APPLY": "Ready to apply",
        "NEEDS_USER_INPUT": "Action needed",
        "NEEDS_USER_ACTION": "Action needed",
        "MANUAL_APPLICATION": "Manual application",
        "APPLIED": "Applied",
        "APPLIED_CONFIRMED": "Application confirmed",
        "INTERVIEW": "Interview",
        "ASSESSMENT": "Assessment",
        "REJECTED": "Rejected",
        "OFFER": "Offer",
        "WITHDRAWN": "Withdrawn",
        "EXPIRED": "Expired",
    }.get(str(value or ""), str(value or "Unknown").replace("_", " ").title())


def _job_action(job: dict) -> dict:
    status = str(job.get("status") or "")
    if status in {"READY_TO_APPLY"} and job.get("email_verified"):
        action = "Review email application"
        action_type = "email_review"
    elif status in {"NEEDS_USER_ACTION", "NEEDS_USER_INPUT", "MANUAL_APPLICATION"}:
        action = "Complete employer application"
        action_type = "open_application"
    elif status == "PREPARED":
        action = "Review prepared CV"
        action_type = "review_job"
    else:
        action = "Review match"
        action_type = "review_job"
    return {
        "id": f"job-{job['id']}",
        "job_id": job["id"],
        "type": action_type,
        "title": action,
        "job_title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "score": float(job.get("score") or 0),
        "status": status,
        "status_label": _human_status(status),
        "application_url": job.get("application_url") or job.get("vacancy_url"),
        "email_verified": bool(job.get("email_verified")),
    }


def effective_email_threshold() -> float:
    preferences = load_preferences()
    return max(80.0, float(preferences.get("email_minimum_score", 80) or 80))


@router.get("/api/dashboard")
def dashboard():
    counts = row(
        "SELECT "
        "COUNT(*) AS total_discovered, "
        "SUM(CASE WHEN COALESCE(score,0)>=65 THEN 1 ELSE 0 END) AS relevant_jobs, "
        "SUM(CASE WHEN COALESCE(score,0)>=80 THEN 1 ELSE 0 END) AS high_matches, "
        "SUM(CASE WHEN status IN ('NEEDS_USER_ACTION','NEEDS_USER_INPUT','READY_TO_APPLY','MANUAL_APPLICATION') THEN 1 ELSE 0 END) AS action_needed, "
        "SUM(CASE WHEN status IN ('APPLIED','APPLIED_CONFIRMED') THEN 1 ELSE 0 END) AS submitted, "
        "SUM(CASE WHEN status='INTERVIEW' THEN 1 ELSE 0 END) AS interviews "
        "FROM jobs"
    ) or {}
    docs = row("SELECT COUNT(DISTINCT job_id) AS documents_ready FROM documents WHERE job_id IS NOT NULL") or {}
    applications = row("SELECT COUNT(*) AS application_records FROM applications") or {}
    replies = row("SELECT COUNT(*) AS employer_replies FROM emails") or {}
    last_run = row("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    google = TokenStore().summary()
    interview = row(
        "SELECT * FROM calendar_events WHERE starts_at>=? ORDER BY starts_at LIMIT 1",
        (datetime.now(timezone.utc).isoformat(),),
    )
    return {
        **counts,
        **docs,
        **applications,
        **replies,
        "last_run": last_run,
        "google": google,
        "next_interview": interview,
    }


@router.get("/api/actions")
def actions(limit: int = 20):
    result: list[dict] = []
    interrupted = row("SELECT * FROM runs WHERE state='INTERRUPTED' ORDER BY id DESC LIMIT 1")
    if interrupted:
        result.append({
            "id": f"run-{interrupted['id']}",
            "type": "interrupted_run",
            "run_id": interrupted["id"],
            "title": "Previous search was interrupted",
            "detail": interrupted.get("message") or "Clear it before starting another search.",
        })
    if not TokenStore().summary().get("connected"):
        result.append({
            "id": "google-reconnect",
            "type": "google_reconnect",
            "title": "Connect Google",
            "detail": "Gmail, Drive and Calendar need a Google connection.",
        })
    actionable = rows(
        "SELECT * FROM jobs WHERE COALESCE(score,0)>=65 "
        "AND status IN ('NEEDS_USER_ACTION','NEEDS_USER_INPUT','READY_TO_APPLY','MANUAL_APPLICATION','PREPARED') "
        "ORDER BY score DESC,discovered_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    )
    result.extend(_job_action(job) for job in actionable)
    return result[: max(1, min(limit, 100))]


@router.get("/api/activity")
def activity(limit: int = 30):
    data = rows(
        "SELECT e.id,e.event_type,e.detail,e.created_at,e.job_id,j.title,j.company "
        "FROM events e LEFT JOIN jobs j ON j.id=e.job_id "
        "ORDER BY e.created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    )
    for item in data:
        item["event_label"] = str(item.get("event_type") or "Activity").replace("_", " ").title()
    return data


@router.get("/api/inbox")
def inbox(limit: int = 50):
    return rows("SELECT * FROM emails ORDER BY received_at DESC LIMIT ?", (max(1, min(limit, 100)),))


@router.get("/api/document-groups")
def document_groups():
    docs = rows(
        "SELECT d.*,j.title,j.company,j.score FROM documents d "
        "LEFT JOIN jobs j ON j.id=d.job_id ORDER BY d.created_at DESC"
    )
    grouped: dict[str, dict] = {}
    for doc in docs:
        key = str(doc.get("job_id") or "unlinked")
        group = grouped.setdefault(key, {
            "job_id": doc.get("job_id"),
            "title": doc.get("title") or "Unlinked document",
            "company": doc.get("company") or "",
            "score": doc.get("score"),
            "documents": [],
        })
        group["documents"].append(doc)
    return list(grouped.values())


@router.get("/api/diagnostics")
def diagnostics():
    latest_run = row("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    sources = rows("SELECT * FROM source_status ORDER BY source_name")
    cv = row("SELECT version,original_name,created_at FROM master_cvs ORDER BY version DESC LIMIT 1")
    google = TokenStore().summary()
    storage_ok = False
    try:
        storage_ok = bool(ObjectStorage().healthy())
    except Exception:
        storage_ok = False
    return {
        "database": {"ready": schema_version() == LATEST_SCHEMA_VERSION, "schema_version": schema_version()},
        "storage": {"ready": storage_ok},
        "scheduler": {"configured": bool(os.getenv("CRON_SECRET"))},
        "google": {"connected": bool(google.get("connected")), "expires_at": google.get("expires_at")},
        "master_cv": cv,
        "latest_run": latest_run,
        "sources": sources,
        "email_threshold": effective_email_threshold(),
        "cv_text_available": bool(cv_text().strip()),
    }
