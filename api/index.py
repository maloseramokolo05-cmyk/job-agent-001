from __future__ import annotations

import os

import requests
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from backend import main as backend_main
from backend.config import load_profile
from backend.security import COOKIE, CSRF_COOKIE, csrf_token, new_session
from integrations.google.oauth import access_token, complete_authorization, disconnect, start_authorization

app = backend_main.app

# The owner does not use an app-level password. Authentication is completed with
# the Google account whose email matches the candidate profile. Keep the
# existing backend security middleware so all private API routes still require
# a signed session and CSRF protection.
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) not in {"/api/auth/login", "/api/google/callback"}
]
app.middleware_stack = None

_GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


def _owner_email() -> str:
    return str(load_profile().get("email", "")).strip().lower()


@app.get("/api/google/callback")
def owner_google_auth(request: Request, code: str | None = None, state: str | None = None):
    # /api/google/callback is already an explicit public path in the backend
    # middleware. Opening it without OAuth parameters starts owner sign-in.
    if not code and not state:
        try:
            started = start_authorization(["gmail", "drive", "calendar"])
        except ValueError as exc:
            raise HTTPException(503, "Google OAuth is not configured for this deployment") from exc
        return RedirectResponse(started["authorization_url"])

    if not code or not state:
        raise HTTPException(400, "Google authorization parameters are incomplete")

    expected_email = _owner_email()
    if not expected_email:
        raise HTTPException(503, "Owner email is not configured")

    try:
        complete_authorization(code, state)
        token = access_token()
        google_response = requests.get(
            _GMAIL_PROFILE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        google_response.raise_for_status()
        connected_email = str(google_response.json().get("emailAddress", "")).strip().lower()
        if connected_email != expected_email:
            disconnect()
            raise PermissionError("This Google account is not authorized for the Job Agent")
    except PermissionError as exc:
        disconnect()
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        disconnect()
        raise HTTPException(400, "Google authorization failed. Reconnect and try again.") from exc

    session = new_session(expected_email)
    csrf = csrf_token()
    secure = os.getenv("APP_ENV") == "production"
    response = RedirectResponse("/#dashboard", status_code=302)
    response.set_cookie(
        COOKIE,
        session,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    return response
