from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.config import ROOT, env_int, load_preferences, load_profile
from backend.database import connect, event, now, row
from agents.candidate_fit import get_candidate_fit_profile, targeted_preferences
from agents.cv_parser import find_master, parse_cv
from agents.documents import generate_cv
from agents.repository import ingest, update_analysis
from agents.scoring import score_job
from applications.email_apply import apply_by_email
from job_sources.careers24 import Careers24Source
from job_sources.greenhouse import GreenhouseSource
from job_sources.lever import LeverSource
from job_sources.rss import RSSSource
from job_sources.sample import SampleSource

log = logging.getLogger("job_agent")
_lock = threading.Lock()


def cv_text():
    latest = row("SELECT extracted_text FROM master_cvs ORDER BY id DESC LIMIT 1")
    if latest and latest.get("extracted_text"):
        return latest["extracted_text"]
    path = find_master(ROOT / "cv")
    return parse_cv(path) if path else ""


def _source_status(source, status, *, error=None):
    with connect() as db:
        db.execute(
            "INSERT INTO source_status(source_name,supported,authenticated,search_supported,application_supported,status,last_success,last_error) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET "
            "supported=excluded.supported,authenticated=excluded.authenticated,search_supported=excluded.search_supported,"
            "application_supported=excluded.application_supported,status=excluded.status,last_success=excluded.last_success,last_error=excluded.last_error",
            (
                source.name,
                int(source.supported),
                int(source.authenticated),
                int(source.search_supported),
                int(source.application_supported),
                status,
                now() if not error else None,
                error[:500] if error else None,
            ),
        )


def _set_job_status(job_id, status, cv_ref=None, reason=None):
    with connect() as db:
        if cv_ref:
            db.execute("UPDATE jobs SET cv_path=?,status=? WHERE id=?", (cv_ref, status, job_id))
        else:
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    if reason:
        event("APPLICATION_HANDOFF", reason, job_id)


def run(include_sample=False):
    if not _lock.acquire(False):
        raise RuntimeError("A job run is already active")
    run_id = None
    try:
        stale_before = (datetime.now(timezone.utc) - timedelta(
            seconds=env_int("RUN_STALE_AFTER_SECONDS", 900)
        )).isoformat()
        with connect() as db:
            db.execute(
                "UPDATE runs SET state='INTERRUPTED',finished_at=?,message='Previous worker stopped before completing' "
                "WHERE state='RUNNING' AND started_at<?",
                (now(), stale_before),
            )
            active = db.execute("SELECT id FROM runs WHERE state='RUNNING' ORDER BY id DESC LIMIT 1").fetchone()
            if active:
                raise RuntimeError(f"Job run {active[0]} is already active")
            run_id = db.execute(
                "INSERT INTO runs(started_at,state,message) VALUES(?,?,?)",
                (now(), "RUNNING", "Starting South Africa job search"),
            ).lastrowid
        deadline = time.monotonic() + env_int("RUN_TIME_BUDGET_SECONDS", 240)
        profile = load_profile()
        preferences = load_preferences()
        master = cv_text()
        fit = get_candidate_fit_profile(profile, master)
        search_preferences = targeted_preferences(preferences, fit)
        # Explicit sample mode is a deterministic developer/test path. Production rejects it at the API.
        sources = [SampleSource()] if include_sample else [Careers24Source(), GreenhouseSource(), LeverSource(), RSSSource()]
        stats = {
            "discovered": 0,
            "duplicates": 0,
            "analyzed": 0,
            "strong_matches": 0,
            "low_relevance_filtered": 0,
            "documents_prepared": 0,
            "email_applications_sent": 0,
            "email_duplicates_prevented": 0,
            "needs_user_action": 0,
            "errors": 0,
            "budget_exhausted": False,
        }
        maximum = env_int("MAX_JOBS_PER_RUN", 120)
        # 70 is the minimum preparation threshold. Lower-scoring jobs can stay
        # in the database for audit/history but must not enter the preparation
        # workflow automatically.
        threshold = max(70.0, float(preferences.get("minimum_score", 68)))
        email_threshold = max(80.0, float(preferences.get("email_minimum_score", 72)))
        for source in sources:
            if stats["discovered"] >= maximum or time.monotonic() >= deadline - 10:
                stats["budget_exhausted"] = time.monotonic() >= deadline - 10
                break
            try:
                with connect() as db:
                    db.execute(
                        "UPDATE runs SET message=?,checkpoint=? WHERE id=?",
                        (
                            f"Searching {source.name}...",
                            json.dumps({"source": source.name, "stats": stats}),
                            run_id,
                        ),
                    )
                discovered = source.search(profile, search_preferences)
                _source_status(source, "CONNECTED")
                for job in discovered[: max(0, maximum - stats["discovered"])]:
                    if time.monotonic() >= deadline - 10:
                        stats["budget_exhausted"] = True
                        break
                    stats["discovered"] += 1
                    job_id, duplicate = ingest(job)
                    if duplicate:
                        stats["duplicates"] += 1
                        continue
                    result = score_job(job.dict(), profile, preferences, master, fit_profile=fit)
                    selected = result["score"] >= threshold
                    status = "SHORTLISTED" if selected else "DISCOVERED"
                    update_analysis(job_id, result, status)
                    stats["analyzed"] += 1
                    if not selected:
                        stats["low_relevance_filtered"] += 1
                        continue
                    stats["strong_matches"] += 1

                    # Only the strongest verified-fit vacancies may enter the
                    # email route automatically. Existing first-send/duplicate
                    # safeguards inside apply_by_email remain unchanged.
                    if result["score"] >= email_threshold and job.email_verified and job.application_email and master:
                        try:
                            outcome = apply_by_email(job_id, master)
                            if outcome.get("sent"):
                                stats["email_applications_sent"] += 1
                                stats["documents_prepared"] += 1
                            elif outcome.get("duplicate"):
                                stats["email_duplicates_prevented"] += 1
                            continue
                        except PermissionError as exc:
                            log.info("Email application requires user/setup action for job %s: %s", job_id, exc)
                            reason = str(exc)
                        except Exception as exc:
                            log.exception("Email application failed for job %s", job_id)
                            event("EMAIL_APPLICATION_ERROR", str(exc)[:500], job_id, run_id)
                            reason = f"Email application could not be completed: {exc}"
                            stats["errors"] += 1
                    else:
                        reason = (
                            "This vacancy passed the CV-fit threshold but requires review or a web application route. "
                            "Open the original application page and complete any login/human-verification step manually."
                        )

                    cv_ref = None
                    if master:
                        try:
                            _docx, cv_ref = generate_cv(job.dict(), profile, master, job_id)
                            stats["documents_prepared"] += 1
                        except Exception as exc:
                            log.exception("Document generation failed for job %s", job_id)
                            event("DOCUMENT_ERROR", str(exc)[:500], job_id, run_id)
                            stats["errors"] += 1
                    _set_job_status(job_id, "NEEDS_USER_ACTION", cv_ref, reason)
                    stats["needs_user_action"] += 1
            except Exception as exc:
                log.exception("Source %s failed", source.name)
                stats["errors"] += 1
                event("SOURCE_ERROR", f"{source.name}: {exc}", run_id=run_id)
                _source_status(source, "TEMPORARY_ERROR", error=str(exc))
            if stats["budget_exhausted"]:
                break
        message = "Run paused safely at the execution time budget" if stats["budget_exhausted"] else "Run complete"
        with connect() as db:
            db.execute(
                "UPDATE runs SET finished_at=?,state='COMPLETED',progress=100,message=?,stats=?,checkpoint=? WHERE id=?",
                (now(), message, json.dumps(stats), json.dumps({"completed": True, "stats": stats}), run_id),
            )
        return {"run_id": run_id, **stats}
    except Exception as exc:
        if run_id:
            with connect() as db:
                db.execute(
                    "UPDATE runs SET finished_at=?,state='ERROR',message=? WHERE id=?",
                    (now(), str(exc), run_id),
                )
        raise
    finally:
        _lock.release()
