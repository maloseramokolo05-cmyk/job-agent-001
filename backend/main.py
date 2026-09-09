from __future__ import annotations

import csv
import io
import logging
import os
import platform
import secrets
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.documents import generate_cover_letter, generate_cv
from agents.pipeline import cv_text, run
from applications.email_apply import apply_by_email
from backend.config import ROOT, load_preferences, load_profile, save_json
from backend.database import connect, event, init_db, now, row, rows, schema_version
from backend.security import COOKIE, CSRF_COOKIE, new_session, password_matches, rate_limit, revoke, session_user
from backend.storage import ObjectStorage
from backend.version import __version__
from integrations.google.calendar import create_event
from integrations.google.drive import list_app_files, upload_file
from integrations.google.gmail import create_draft, send_message, sync_messages
from integrations.google.oauth import complete_authorization, disconnect, start_authorization
from integrations.google.token_store import TokenStore
from job_sources.careers24 import Careers24Source
from job_sources.greenhouse import GreenhouseSource
from job_sources.lever import LeverSource
from job_sources.rss import RSSSource

app = FastAPI(title="Tumelo Job Agent", version=__version__)


class Status(BaseModel):
    status: str


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class Setup(BaseModel):
    profile: dict
    preferences: dict


class GmailDraft(BaseModel):
    to: str
    subject: str
    body: str
    thread_id: str | None = None


class ApplyEmail(BaseModel):
    confirmed: bool = False


class CalendarInput(BaseModel):
    event: dict
    confirmed: bool = False


class GoogleStart(BaseModel):
    features: list[str] = Field(default_factory=lambda: ["gmail", "gmail_send", "drive", "calendar"])


ALLOWED = {
    "DISCOVERED", "SHORTLISTED", "PREPARED", "NEEDS_USER_INPUT", "NEEDS_USER_ACTION",
    "READY_TO_APPLY", "MANUAL_APPLICATION", "APPLIED", "APPLIED_CONFIRMED", "INTERVIEW",
    "ASSESSMENT", "REJECTED", "OFFER", "WITHDRAWN", "EXPIRED",
}


def setup_logging():
    root_logger = logging.getLogger()
    if any(getattr(handler, "job_agent_handler", False) for handler in root_logger.handlers):
        return
    if os.getenv("VERCEL"):
        handler = logging.StreamHandler()
    else:
        log_path = ROOT / "logs/job_agent.log"
        log_path.parent.mkdir(exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=4, encoding="utf-8")
    handler.job_agent_handler = True
    handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","severity":"%(levelname)s","component":"%(name)s","message":"%(message)s"}'
    ))
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


@app.on_event("startup")
def startup():
    init_db()
    setup_logging()
    if os.getenv("APP_ENV") == "production":
        if len(os.getenv("SESSION_SECRET", "")) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters")
        if not os.getenv("ADMIN_PASSWORD_HASH"):
            raise RuntimeError("ADMIN_PASSWORD_HASH is required")
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL is required in production")
        ObjectStorage()
    logging.getLogger("startup").info("event=APPLICATION_STARTED version=%s", __version__)


@app.middleware("http")
async def security(request: Request, call_next):
    auth_configured = bool(os.getenv("ADMIN_PASSWORD_HASH"))
    public_paths = {"/", "/api/health", "/api/ready", "/api/auth/login", "/api/cron/search"}
    public = not auth_configured or request.url.path in public_paths or request.url.path.startswith("/assets/")
    if not public and not session_user(request.cookies.get(COOKIE)):
        response = JSONResponse({"error": {"code": "UNAUTHENTICATED", "message": "Authentication required"}}, 401)
    elif (
        not public
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and not secrets.compare_digest(request.cookies.get(CSRF_COOKIE, ""), request.headers.get("X-CSRF-Token", ""))
    ):
        response = JSONResponse({"error": {"code": "CSRF_FAILED", "message": "CSRF validation failed"}}, 403)
    else:
        response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        ),
    })
    return response


@app.exception_handler(HTTPException)
async def http_error(_request, exc):
    return JSONResponse({"error": {"code": "REQUEST_FAILED", "message": str(exc.detail)}}, exc.status_code)


@app.post("/api/auth/login")
def login(value: Login, request: Request):
    rate_limit(request.client.host if request.client else "unknown")
    if value.username != os.getenv("ADMIN_USERNAME", "admin") or not password_matches(value.password):
        raise HTTPException(401, "Invalid username or password")
    token = new_session(value.username)
    csrf = secrets.token_urlsafe(32)
    secure = os.getenv("APP_ENV") == "production"
    response = JSONResponse({"authenticated": True, "csrf_token": csrf})
    response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite="strict", max_age=43200, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="strict", max_age=43200, path="/")
    return response


@app.post("/api/auth/logout")
def logout(request: Request):
    revoke(request.cookies.get(COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@app.get("/api/auth/session")
def auth_session(request: Request):
    return {"authenticated": True, "username": session_user(request.cookies.get(COOKIE))}


@app.get("/api/health")
def health():
    google = TokenStore().summary()
    return {
        "status": "ok",
        "version": __version__,
        "platform": platform.system().lower(),
        "database": {"ready": schema_version() == 3, "schema_version": schema_version()},
        "scheduler": "vercel_cron" if os.getenv("VERCEL") else "external_process",
        "google": {"connected": google["connected"]},
        "job_connector_count": 4,
    }


@app.get("/api/ready")
def ready():
    storage = ObjectStorage().healthy()
    database = schema_version() == 3
    production = os.getenv("APP_ENV") == "production"
    cron = bool(os.getenv("CRON_SECRET"))
    google_configured = bool(os.getenv("GOOGLE_CLIENT_ID"))
    body = {
        "status": "ready" if storage and database and (not production or cron) else "not_ready",
        "database": database,
        "storage": storage,
        "scheduler_configured": cron,
        "google_configured": google_configured,
        "connectors": ["careers24", "greenhouse", "lever", "rss"],
    }
    return JSONResponse(body, 200 if body["status"] == "ready" else 503)


@app.get("/api/config")
def config():
    return {
        "profile": load_profile(),
        "preferences": load_preferences(),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


@app.get("/api/profile")
def profile():
    return load_profile()


@app.put("/api/profile")
def save_profile(value: dict):
    save_json("profile.json", value)
    return {"saved": True}


@app.get("/api/settings")
def settings():
    return load_preferences()


@app.put("/api/settings")
def save_settings(value: dict):
    save_json("job_preferences.json", value)
    return {"saved": True}


@app.post("/api/setup")
def setup(value: Setup):
    save_json("profile.json", value.profile)
    save_json("job_preferences.json", value.preferences)
    return {"saved": True}


@app.post("/api/cv")
async def upload_cv(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(400, "CV must be PDF or DOCX")
    content = await file.read()
    if not content or len(content) > 10_000_000:
        raise HTTPException(413, "CV must be between 1 byte and 10 MB")
    signatures = {".pdf": b"%PDF-", ".docx": b"PK"}
    if not content.startswith(signatures[suffix]):
        raise HTTPException(400, "File content does not match its extension")
    metadata = ObjectStorage().put(
        f"master-cvs/{secrets.token_hex(12)}{suffix}", content, file.content_type or "application/octet-stream"
    )
    if os.getenv("APP_ENV") != "production":
        path = ROOT / "cv" / ("master_cv" + suffix)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    from agents.cv_parser import parse_cv
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        extracted = parse_cv(tmp.name)
    with connect() as db:
        username = os.getenv("ADMIN_USERNAME", "admin")
        version = db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM master_cvs WHERE username=?", (username,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO master_cvs(username,version,storage_key,sha256,content_type,original_name,extracted_text,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                username, version, metadata["storage_key"], metadata["sha256"], metadata["content_type"],
                Path(file.filename or "cv").name, extracted, now(),
            ),
        )
    return {
        "saved": True,
        "version": version,
        "sha256": metadata["sha256"],
        "extracted_text": extracted[:10000],
        "requires_verification": True,
    }


@app.get("/api/jobs")
def jobs(status: str | None = None, min_score: float = 0, q: str = ""):
    sql = "SELECT * FROM jobs WHERE COALESCE(score,0)>=?"
    args = [min_score]
    if status:
        sql += " AND status=?"
        args.append(status)
    if q:
        sql += " AND (LOWER(title) LIKE LOWER(?) OR LOWER(company) LIKE LOWER(?) OR LOWER(location) LIKE LOWER(?))"
        args += [f"%{q}%"] * 3
    return rows(sql + " ORDER BY priority DESC,score DESC,discovered_at DESC", args)


@app.get("/api/jobs/{job_id}")
def job(job_id: int):
    value = row("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not value:
        raise HTTPException(404, "Job not found")
    value["history"] = rows("SELECT * FROM events WHERE job_id=? ORDER BY created_at DESC", (job_id,))
    return value


@app.post("/api/jobs/{job_id}/status")
def set_status(job_id: int, value: Status):
    if value.status not in ALLOWED:
        raise HTTPException(400, "Invalid status")
    with connect() as db:
        jobrow = db.execute("SELECT source FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not jobrow:
            raise HTTPException(404, "Job not found")
        db.execute("UPDATE jobs SET status=? WHERE id=?", (value.status, job_id))
        existing = db.execute(
            "SELECT 1 FROM applications WHERE job_id=? AND status IN ('APPLIED','APPLIED_CONFIRMED')", (job_id,)
        ).fetchone()
        if value.status == "APPLIED" and not existing:
            db.execute(
                "INSERT INTO applications(job_id,application_date,source,status,created_at) VALUES(?,?,?,?,?)",
                (job_id, now(), jobrow[0], "APPLIED", now()),
            )
    event("STATUS_CHANGED", value.status, job_id)
    return {"status": value.status}


@app.post("/api/jobs/{job_id}/cv")
def make_cv(job_id: int):
    job_value = row("SELECT * FROM jobs WHERE id=?", (job_id,))
    master = cv_text()
    if not job_value:
        raise HTTPException(404, "Job not found")
    try:
        docx, pdf = generate_cv(job_value, load_profile(), master, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with connect() as db:
        db.execute("UPDATE jobs SET cv_path=?,status='PREPARED' WHERE id=?", (pdf or docx, job_id))
    return {"docx": docx, "pdf": pdf}


@app.post("/api/jobs/{job_id}/cover-letter")
def cover(job_id: int):
    job_value = row("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job_value:
        raise HTTPException(404, "Job not found")
    try:
        path = generate_cover_letter(job_value, load_profile(), cv_text(), job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with connect() as db:
        db.execute("UPDATE jobs SET cover_letter_path=? WHERE id=?", (path, job_id))
    return {"path": path}


@app.post("/api/jobs/{job_id}/apply-email")
def email_apply(job_id: int, value: ApplyEmail):
    if not value.confirmed:
        raise HTTPException(400, "Confirm this application before sending")
    try:
        return apply_by_email(job_id, cv_text(), explicit_authorization=True)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/applications")
def applications():
    return rows(
        "SELECT a.*,j.title,j.company,j.application_email FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.created_at DESC"
    )


@app.get("/api/documents")
def documents():
    return rows("SELECT * FROM documents ORDER BY created_at DESC")


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: int):
    document = row("SELECT * FROM documents WHERE id=?", (document_id,))
    if not document:
        raise HTTPException(404, "Document not found")
    storage_key = document.get("storage_key") or ""
    if storage_key:
        stream, content_type = ObjectStorage().get(storage_key)
        filename = storage_key.rsplit("/", 1)[-1]
        return StreamingResponse(
            iter([stream.getvalue()]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    legacy = ROOT / document["local_path"]
    if not legacy.exists():
        raise HTTPException(404, "Document file is unavailable")
    return FileResponse(legacy)


@app.post("/api/runs")
def start_run(sample: bool = False):
    if sample and os.getenv("APP_ENV") == "production":
        raise HTTPException(400, "Sample mode is disabled in production")
    return {"started": True, **run(sample)}


@app.get("/api/runs/latest")
def latest():
    return row("SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {
        "state": "IDLE", "progress": 0, "message": "Ready", "stats": "{}"
    }


@app.post("/api/runs/{run_id}/discard")
def discard(run_id: int):
    with connect() as db:
        db.execute(
            "UPDATE runs SET state='DISCARDED',finished_at=? WHERE id=? AND state='INTERRUPTED'", (now(), run_id)
        )
    return {"discarded": True}


@app.get("/api/cron/search")
def cron_search(request: Request):
    secret = os.getenv("CRON_SECRET", "")
    if not secret or not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {secret}"):
        raise HTTPException(401, "Invalid cron authorization")
    return run(False)


@app.get("/api/sources")
def sources():
    known = rows("SELECT * FROM source_status ORDER BY source_name")
    if known:
        return known
    return [
        Careers24Source().capability(), GreenhouseSource().capability(), LeverSource().capability(), RSSSource().capability()
    ]


@app.get("/api/overview")
def overview():
    result = row(
        "SELECT COUNT(*) AS jobs_found,"
        "SUM(CASE WHEN score>=80 THEN 1 ELSE 0 END) AS high_match,"
        "SUM(CASE WHEN status='PREPARED' THEN 1 ELSE 0 END) AS prepared,"
        "SUM(CASE WHEN status IN ('APPLIED','APPLIED_CONFIRMED') THEN 1 ELSE 0 END) AS submitted,"
        "SUM(CASE WHEN status IN ('NEEDS_USER_INPUT','NEEDS_USER_ACTION') THEN 1 ELSE 0 END) AS needs_input,"
        "SUM(CASE WHEN status='INTERVIEW' THEN 1 ELSE 0 END) AS interviews,"
        "SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) AS rejected,"
        "SUM(CASE WHEN status IN ('APPLIED','APPLIED_CONFIRMED') THEN 1 ELSE 0 END) AS awaiting_response "
        "FROM jobs"
    ) or {}
    today = datetime.now(timezone.utc).date().isoformat()
    run_info = row("SELECT COUNT(*) AS runs_today,MAX(started_at) AS last_run FROM runs WHERE started_at LIKE ?", (f"{today}%",)) or {}
    result.update(run_info)
    return result


@app.get("/api/google/status")
def google_status():
    return TokenStore().summary()


@app.post("/api/google/connect")
def google_connect(value: GoogleStart):
    try:
        return start_authorization(value.features)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/google/callback")
def google_callback(code: str, state: str):
    try:
        complete_authorization(code, state)
    except Exception as exc:
        raise HTTPException(400, "Google authorization failed. Reconnect and try again.") from exc
    return RedirectResponse("/?google=connected")


@app.delete("/api/google")
def google_disconnect():
    disconnect()
    return {"connected": False}


@app.post("/api/gmail/sync")
def gmail_sync():
    try:
        return {"messages_saved": sync_messages()}
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.get("/api/gmail/messages")
def gmail_messages():
    return rows("SELECT * FROM emails ORDER BY received_at DESC LIMIT 100")


@app.post("/api/gmail/drafts")
def gmail_draft(value: GmailDraft):
    return create_draft(value.to, value.subject, value.body, value.thread_id)


@app.post("/api/gmail/send")
def gmail_send(value: GmailDraft, confirm: bool = False):
    return send_message(value.to, value.subject, value.body, confirm)


@app.get("/api/drive/files")
def drive_files():
    return list_app_files()


@app.post("/api/documents/{document_id}/drive")
def drive_upload(document_id: int):
    document = row("SELECT * FROM documents WHERE id=?", (document_id,))
    if not document:
        raise HTTPException(404, "Document not found")
    if document.get("storage_key"):
        stream, _content_type = ObjectStorage().get(document["storage_key"])
        import tempfile
        suffix = Path(document["storage_key"]).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(stream.getvalue())
            tmp.flush()
            result = upload_file(Path(tmp.name), existing_id=document.get("drive_file_id"))
    else:
        result = upload_file(ROOT / document["local_path"], existing_id=document.get("drive_file_id"))
    with connect() as db:
        db.execute("UPDATE documents SET drive_file_id=? WHERE id=?", (result["id"], document_id))
    return result


@app.post("/api/calendar/events")
def calendar_event(value: CalendarInput):
    return create_event(value.event, value.confirmed)


@app.get("/api/calendar/events")
def calendar_events():
    return rows("SELECT * FROM calendar_events ORDER BY starts_at")


@app.get("/api/logs")
def logs():
    if os.getenv("VERCEL"):
        return {"lines": ["Production logs are available in the Vercel runtime log stream."]}
    path = ROOT / "logs/job_agent.log"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:] if path.exists() else []
    return {"lines": lines}


@app.get("/api/export.csv")
def export_csv():
    data = rows(
        "SELECT company,title AS vacancy,discovered_at AS application_date,cv_path AS cv_version,source,status,salary "
        "FROM jobs ORDER BY discovered_at DESC"
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys() if data else ["company", "vacancy", "status"])
    writer.writeheader()
    writer.writerows(data)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend/index.html")
