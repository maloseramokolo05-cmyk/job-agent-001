from fastapi.testclient import TestClient

from api.index import app


def test_workspace_no_longer_requires_private_sign_in(monkeypatch):
    # Legacy auth environment values may still exist in Vercel, but the production
    # entrypoint intentionally ignores/removes the private sign-in layer.
    monkeypatch.setenv("ADMIN_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "legacy-disabled")
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    with TestClient(app) as client:
        assert client.get("/api/jobs").status_code == 200
        assert client.post("/api/auth/login", json={"username": "owner", "password": "anything"}).status_code == 404
        assert client.post("/api/auth/logout").status_code == 404
        assert client.get("/api/auth/session").status_code == 404


def test_google_routes_remain_available_without_private_sign_in(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "legacy-disabled")
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    with TestClient(app) as client:
        # Missing OAuth params should still reach FastAPI validation.
        assert client.get("/api/google/callback").status_code == 422
        assert client.get("/api/google/status").status_code == 200


def test_health_has_security_headers():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
