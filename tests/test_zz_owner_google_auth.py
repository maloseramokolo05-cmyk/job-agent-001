from fastapi.testclient import TestClient


class GoogleProfileResponse:
    def __init__(self, email):
        self.email = email

    def raise_for_status(self):
        return None

    def json(self):
        return {"emailAddress": self.email}


def _entry():
    # Import the production entrypoint only when these final tests execute.
    # Importing it during pytest collection mutates backend.main.app globally
    # and breaks the backend-unit tests that intentionally exercise that app.
    import api.index as entry

    return entry


def test_private_api_requires_owner_session_without_password_config(monkeypatch):
    entry = _entry()
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    paths = {getattr(route, "path", None) for route in entry.app.router.routes}
    assert "/api/auth/login" not in paths
    assert "/api/google/callback" in paths
    with TestClient(entry.app) as client:
        assert client.get("/api/jobs").status_code == 401
        assert client.get("/api/health").status_code == 200


def test_google_callback_without_params_starts_owner_sign_in(monkeypatch):
    entry = _entry()
    monkeypatch.setattr(
        entry,
        "start_authorization",
        lambda features: {"authorization_url": "https://accounts.google.test/owner", "state": "state"},
    )
    with TestClient(entry.app) as client:
        response = client.get("/api/google/callback", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "https://accounts.google.test/owner"


def test_wrong_google_account_is_rejected(monkeypatch):
    entry = _entry()
    disconnected = []
    monkeypatch.setattr(entry, "load_profile", lambda: {"email": "maloseramokolo05@gmail.com"})
    monkeypatch.setattr(entry, "complete_authorization", lambda code, state: {"connected": True})
    monkeypatch.setattr(entry, "access_token", lambda: "access-token")
    monkeypatch.setattr(
        entry.requests,
        "get",
        lambda *args, **kwargs: GoogleProfileResponse("someone-else@example.com"),
    )
    monkeypatch.setattr(entry, "disconnect", lambda: disconnected.append(True))
    with TestClient(entry.app) as client:
        response = client.get("/api/google/callback?code=code&state=state", follow_redirects=False)
    assert response.status_code == 403
    assert disconnected


def test_matching_google_account_creates_owner_session(monkeypatch):
    entry = _entry()
    monkeypatch.setattr(entry, "load_profile", lambda: {"email": "maloseramokolo05@gmail.com"})
    monkeypatch.setattr(entry, "complete_authorization", lambda code, state: {"connected": True})
    monkeypatch.setattr(entry, "access_token", lambda: "access-token")
    monkeypatch.setattr(
        entry.requests,
        "get",
        lambda *args, **kwargs: GoogleProfileResponse("maloseramokolo05@gmail.com"),
    )
    monkeypatch.setattr(entry, "new_session", lambda username: "signed-owner-session")
    monkeypatch.setattr(entry, "csrf_token", lambda: "owner-csrf")
    with TestClient(entry.app) as client:
        response = client.get("/api/google/callback?code=code&state=state", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/#dashboard"
    cookies = response.headers.get("set-cookie", "")
    assert "job_agent_session=signed-owner-session" in cookies
    assert "job_agent_csrf=owner-csrf" in cookies
