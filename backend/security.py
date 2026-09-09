from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request

COOKIE = "job_agent_session"
CSRF_COOKIE = "job_agent_csrf"
SESSION_TTL = 60 * 60 * 12
_attempts: dict[str, deque[float]] = defaultdict(deque)
_hasher = PasswordHasher()


def password_matches(password: str) -> bool:
    encoded = os.getenv("ADMIN_PASSWORD_HASH", "")
    if not encoded:
        return False
    try:
        return _hasher.verify(encoded, password)
    except Exception:
        return False


def rate_limit(key: str) -> None:
    now = time.time()
    attempts = _attempts[key]
    while attempts and attempts[0] < now - 900:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many login attempts. Try again later.")
    attempts.append(now)


def _signature(value: str) -> str:
    secret = os.environ.get("SESSION_SECRET", "development-only-change-me").encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def new_session(username: str) -> str:
    value = f"{username}.{int(time.time()) + SESSION_TTL}.{secrets.token_urlsafe(24)}"
    token = f"{value}.{_signature(value)}"
    from backend.database import execute, now
    execute("INSERT INTO sessions(token_hash,username,expires_at,created_at) VALUES(?,?,?,?)", (
        hashlib.sha256(token.encode()).hexdigest(), username,
        str(int(time.time()) + SESSION_TTL), now(),
    ))
    return token


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    try:
        value, signature = token.rsplit(".", 1)
        username, expires, _ = value.split(".", 2)
        if not hmac.compare_digest(signature, _signature(value)) or int(expires) < time.time():
            return None
        from backend.database import row
        active = row("SELECT username FROM sessions WHERE token_hash=? AND revoked_at IS NULL AND CAST(expires_at AS INTEGER)>?", (
            hashlib.sha256(token.encode()).hexdigest(), int(time.time()),
        ))
        return username if active else None
    except (ValueError, TypeError):
        return None


def require_user(request: Request) -> str:
    user = session_user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def require_csrf(request: Request, _user: str = Depends(require_user)) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get("X-CSRF-Token", "")
        if not cookie or not hmac.compare_digest(cookie, header):
            raise HTTPException(403, "CSRF validation failed")


def csrf_token() -> str:
    return secrets.token_urlsafe(32)


def revoke(token: str | None) -> None:
    if token:
        from backend.database import execute, now
        execute("UPDATE sessions SET revoked_at=? WHERE token_hash=?", (now(), hashlib.sha256(token.encode()).hexdigest()))
