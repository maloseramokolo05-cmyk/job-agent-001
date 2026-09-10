from __future__ import annotations

import json
import os
import secrets

os.environ.setdefault("ADMIN_PASSWORD_HASH", "google-owner-auth-enabled")

import requests
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend import main as backend_main
from backend.config import load_profile
from backend.database import LATEST_SCHEMA_VERSION, schema_version
from backend.product_api import router as product_router
from backend.security import COOKIE, CSRF_COOKIE, csrf_token, new_session, rate_limit, session_user
from backend.storage import ObjectStorage
from integrations.google.credentials import CredentialStore
from integrations.google.oauth import (
    _redirect_uri,
    access_token,
    complete_authorization,
    disconnect,
    start_authorization,
)

app = backend_main.app
app.include_router(product_router)

# Google-only owner authentication replaces the legacy password login and the
# generic backend callback. Readiness is also replaced so it understands the
# encrypted CredentialStore used by the current deployment.
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) not in {"/api/auth/login", "/api/google/callback", "/api/ready"}
]
app.middleware_stack = None

_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_PUBLIC_PATHS = {
    "/",
    "/api/health",
    "/api/ready",
    "/api/cron/search",
    "/api/google/callback",
    "/api/google/bootstrap",
}


@app.on_event("startup")
def migrate_google_bootstrap_credentials():
    store = CredentialStore()
    migrate = getattr(store, "migrate_bootstrap", None)
    if migrate:
        migrate()


def _owner_email() -> str:
    return str(load_profile().get("email", "")).strip().lower()


def _bootstrap_status():
    return {
        "stored_credentials": CredentialStore().configured(),
        "redirect_uri": _redirect_uri(),
        "ready_for_upload": True,
    }


async def _handle_google_bootstrap(request: Request):
    if request.method == "GET":
        return JSONResponse(_bootstrap_status())
    if request.method != "POST":
        return JSONResponse({"error": {"message": "Method not allowed"}}, status_code=405)

    configured = CredentialStore().configured()
    if configured:
        if not session_user(request.cookies.get(COOKIE)):
            return JSONResponse(
                {"error": {"code": "UNAUTHENTICATED", "message": "Owner authentication required"}},
                status_code=401,
            )
        if not secrets.compare_digest(
            request.cookies.get(CSRF_COOKIE, ""), request.headers.get("X-CSRF-Token", "")
        ):
            return JSONResponse(
                {"error": {"code": "CSRF_FAILED", "message": "CSRF validation failed"}},
                status_code=403,
            )

    rate_limit(f"google-bootstrap:{request.client.host if request.client else 'unknown'}")
    try:
        form = await request.form()
        uploaded = form.get("file")
        if uploaded is None or not hasattr(uploaded, "read"):
            raise HTTPException(400, "Choose the Google OAuth JSON file first")
        content = await uploaded.read()
        if not content or len(content) > 64_000:
            raise HTTPException(400, "Google OAuth JSON must be smaller than 64 KB")
        raw = json.loads(content.decode("utf-8"))
        normalized = CredentialStore.normalize(raw)
        expected_redirect = _redirect_uri()
        if expected_redirect not in normalized.get("redirect_uris", []):
            raise HTTPException(400, f"This Google client must include the redirect URI {expected_redirect}")
        CredentialStore().save(raw)
        disconnect()
        return JSONResponse({"saved": True, "redirect_uri": expected_redirect})
    except HTTPException as exc:
        return JSONResponse({"error": {"message": str(exc.detail)}}, status_code=exc.status_code)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"error": {"message": str(exc)}}, status_code=400)


@app.middleware("http")
async def google_owner_guard(request: Request, call_next):
    path = request.url.path
    if path == "/api/google/bootstrap":
        return await _handle_google_bootstrap(request)

    public = path in _PUBLIC_PATHS or path.startswith("/assets/")
    user = session_user(request.cookies.get(COOKIE))
    if not public and not user:
        response = JSONResponse(
            {"error": {"code": "UNAUTHENTICATED", "message": "Owner authentication required"}}, status_code=401
        )
    elif (
        not public
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and not secrets.compare_digest(
            request.cookies.get(CSRF_COOKIE, ""), request.headers.get("X-CSRF-Token", "")
        )
    ):
        response = JSONResponse(
            {"error": {"code": "CSRF_FAILED", "message": "CSRF validation failed"}}, status_code=403
        )
    else:
        response = await call_next(request)
    return response


@app.get("/api/ready")
def ready():
    try:
        storage = ObjectStorage().healthy()
    except Exception:
        storage = False
    database = schema_version() == LATEST_SCHEMA_VERSION
    production = os.getenv("APP_ENV") == "production"
    cron = bool(os.getenv("CRON_SECRET"))
    google_configured = CredentialStore().configured()
    body = {
        "status": "ready" if storage and database and (not production or cron) and google_configured else "not_ready",
        "database": database,
        "storage": storage,
        "scheduler_configured": cron,
        "google_configured": google_configured,
        "connectors": ["careers24", "greenhouse", "lever", "rss"],
    }
    return JSONResponse(body, 200 if body["status"] == "ready" else 503)


@app.get("/api/google/callback")
def owner_google_auth(request: Request, code: str | None = None, state: str | None = None):
    if not code and not state:
        try:
            started = start_authorization(["identity", "gmail", "drive", "calendar"])
        except ValueError as exc:
            raise HTTPException(503, "Google OAuth is not configured. Upload the OAuth JSON on the sign-in screen.") from exc
        return RedirectResponse(started["authorization_url"])

    if not code or not state:
        raise HTTPException(400, "Google authorization parameters are incomplete")

    expected_email = _owner_email()
    if not expected_email:
        raise HTTPException(503, "Owner email is not configured")

    try:
        complete_authorization(code, state)
    except Exception as exc:
        disconnect()
        raise HTTPException(400, "Google token exchange failed. Reconnect using the current OAuth client and try again.") from exc

    try:
        token = access_token()
        google_response = requests.get(
            _GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token}"}, timeout=20
        )
        google_response.raise_for_status()
        payload = google_response.json()
        connected_email = str(payload.get("email", "")).strip().lower()
        email_verified = payload.get("email_verified", True)
        if not connected_email or not email_verified:
            raise PermissionError("Google did not return a verified account email")
        if connected_email != expected_email:
            raise PermissionError("This Google account is not authorized for the Job Agent")
    except PermissionError as exc:
        disconnect()
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        disconnect()
        raise HTTPException(400, "Google sign-in succeeded, but owner identity verification failed. Reconnect and try again.") from exc

    session = new_session(expected_email)
    csrf = csrf_token()
    secure = os.getenv("APP_ENV") == "production"
    response = RedirectResponse("/#dashboard", status_code=302)
    response.set_cookie(COOKIE, session, httponly=True, secure=secure, samesite="strict", max_age=43200, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="strict", max_age=43200, path="/")
    return response
