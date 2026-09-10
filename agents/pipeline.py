from __future__ import annotations

import hashlib
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
from agents.relevance_maintenance import rescore_existing
from agents.repository import ingest, update_analysis
from agents.scoring import score_job
from applications.email_apply import apply_by_email
from applications.thresholds import effective_auto_prepare_threshold, effective_email_threshold
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


def _existing_cv_ref(job_id: int, master: str) -> str | None:
    if not master.strip():
        return None
    master_hash = hashlib.sha256(master.encode()).hexdigest()
    existing = row(
        "SELECT storage_key FROM documents WHERE job_id=? AND document_type='CV_PDF' "
        "AND master_cv_hash=? ORDER BY id DESC LIMIT 1",
        (job_id, master_hash),
    )
    if existing and existing.get("storage_key"):
        return f"storage:{existing['storage_key']}"
    return None


def _checkpoint(run_id: int, source_name: str, stats: dict, message: str | None = None):
    with connect() as db:
        db.execute(
            "UPDATE runs SET message=?,checkpoint=?,progress=? WHERE id=?",
            (
                message or f"Searching {source_name}...",
                json.dumps({"source": source_name, "stats": stats}),
                min(95, max(1, int(stats.get("discovered", 0) / max(1, env_int("MAX_JOBS_PER_RUN", 120)) * 100))),
                run_id,
            ),
        )


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
                "INSERT INTO runs(started_at,state,progress,message) VALUES(?,?,?,?)",
                (now(), "RUNNING", 1, "Starting South Africa job search"),
            ).lastrowid

        deadline = time.monotonic() + env_int("RUN_TIME_BUDGET_SECONDS", 240)
        profile = load_profile()
        preferences = load_preferences()
        master = cv_text()
        fit = get_candidate_fit_profile(profile, master)
        search_preferences = targeted_preferences(preferences, fit)
        existing_rescore = rescore_existing(profile, preferences, master, fit)
        sources = [SampleSource()] if include_sample else [Careers24Source(), GreenhouseSource(), LeverSource(), RSSSource()]

        stats = {
            "discovered": 0,
            "duplicates": 0,
            "analyzed": 0,
            "shortlisted": 0,
            "strong_matches": 0,
            "low_relevance_filtered": 0,
            "existing_jobs_rescored": existing_rescore["evaluated"],
            "existing_jobs_downgraded": existing_rescore["downgraded"],
            "existing_jobs_upgraded": existing_rescore["upgraded"],
            "existing_rescore_skipped": bool(existing_rescore.get("skipped")),
            "documents_prepared": 0,
            "documents_reused": 0,
            "ready_to_apply": 0,
            "email_applications_sent": 0,
            "email_duplicates_prevented": 0,
            "needs_user_action": 0,
            "errors": 0,
            "budget_exhausted": False,
        }

        maximum = env_int("MAX_JOBS_PER_RUN", 120)
        threshold = max(70.0, float(preferences.get("minimum_score", 68)))
        prepare_threshold = max(threshold, effective_auto_prepare_threshold(preferences))
        email_threshold = effective_email_threshold(preferences)

        for source in sources:
            if stats["discovered"] >= maximum or time.monotonic() >= deadline - 10:
                stats["budget_exhausted"] = time.monotonic() >= deadline - 10
                break
            try:
                _checkpoint(run_id, source.name, stats)
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
                        if stats["discovered"] % 10 == 0:
                            _checkpoint(run_id, source.name, stats)
                        continue

                    result = score_job(job.dict(), profile, preferences, master, fit_profile=fit)
                    selected = result["score"] >= threshold
                    status = "SHORTLISTED" if selected else "DISCOVERED"
                    update_analysis(job_id, result, status)
                    stats["analyzed"] += 1

                    if not selected:
                        stats["low_relevance_filtered"] += 1
                        if stats["analyzed"] % 5 == 0:
                            _checkpoint(run_id, source.name, stats)
                        continue

                    stats["shortlisted"] += 1
                    if result["score"] >= 80:
                        stats["strong_matches"] += 1

                    # Medium-good matches remain shortlisted. Do not create two
                    # documents for every marginal match and then flood the user
                    # with NEEDS_USER_ACTION records.
                    if result["score"] < prepare_threshold or not master:
                        if stats["analyzed"] % 5 == 0:
                            _checkpoint(run_id, source.name, stats)
                        continue

                    cv_ref = _existing_cv_ref(job_id, master)
                    if cv_ref:
                        stats["documents_reused"] += 1
                    else:
                        try:
                            _docx, cv_ref = generate_cv(job.dict(), profile, master, job_id)
                            stats["documents_prepared"] += 1
                        except Exception as exc:
                            log.exception("Document generation failed for job %s", job_id)
                            event("DOCUMENT_ERROR", str(exc)[:500], job_id, run_id)
                            stats["errors"] += 1
                            cv_ref = None

                    if result["score"] >= email_threshold and job.email_verified and job.application_email:
                        try:
                            outcome = apply_by_email(job_id, master)
                            if outcome.get("sent"):
                                stats["email_applications_sent"] += 1
                                continue
                            if outcome.get("duplicate"):
                                stats["email_duplicates_prevented"] += 1
                                continue
                        except PermissionError as exc:
                            log.info("Email application awaits owner review for job %s: %s", job_id, exc)
                        except Exception as exc:
                            log.exception("Email application failed for job %s", job_id)
                            event("EMAIL_APPLICATION_ERROR", str(exc)[:500], job_id, run_id)
                            stats["errors"] += 1
                        _set_job_status(
                            job_id,
                            "READY_TO_APPLY",
                            cv_ref,
                            "A verified email application route is available. Review the email and confirm before sending.",
                        )
                        stats["ready_to_apply"] += 1
                    else:
                        _set_job_status(
                            job_id,
                            "NEEDS_USER_ACTION",
                            cv_ref,
                            "A tailored CV is ready. Open the employer application page and complete any login or human-verification step manually.",
                        )
                        stats["needs_user_action"] += 1

                    if stats["analyzed"] % 5 == 0:
                        _checkpoint(run_id, source.name, stats)

            except Exception as exc:
                log.exception("Source %s failed", source.name)
                stats["errors"] += 1
                event("SOURCE_ERROR", f"{source.name}: {exc}", run_id=run_id)
                _source_status(source, "TEMPORARY_ERROR", error=str(exc))
            if stats["budget_exhausted"]:
                break

        if stats["analyzed"] == 0 and stats["duplicates"] > 0:
            message = "Search complete — known vacancies were skipped; no new matching jobs were found"
        elif stats["budget_exhausted"]:
            message = "Search paused safely at the execution time budget"
        else:
            message = "Search complete"

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
                    "UPDATE runs SET finished_at=?,state='ERROR',progress=100,message=? WHERE id=?",
                    (now(), str(exc), run_id),
                )
        raise
    finally:
        _lock.release()
