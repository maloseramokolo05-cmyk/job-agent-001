import os

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from backend.main import app
from backend.security import password_matches


def test_argon2_password_verification(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", PasswordHasher().hash("correct horse"))
    assert password_matches("correct horse")
    assert not password_matches("wrong")


def test_login_session_csrf_and_logout(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", PasswordHasher().hash("valid password"))
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    with TestClient(app) as client:
        assert client.get("/api/jobs").status_code == 401
        login = client.post("/api/auth/login", json={"username": "owner", "password": "valid password"})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert client.get("/api/jobs").status_code == 200
        assert client.post("/api/runs").status_code == 403
        csrf = login.json()["csrf_token"]
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/api/jobs").status_code == 401


def test_health_has_security_headers():
    os.environ.pop("ADMIN_PASSWORD_HASH", None)
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
