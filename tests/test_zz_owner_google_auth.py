import json

from fastapi.testclient import TestClient


class GoogleProfileResponse:
    def __init__(self, email, verified=True):
        self.email = email
        self.verified = verified

    def raise_for_status(self):
        return None

    def json(self):
        return {"email": self.email, "email_verified": self.verified}


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


def test_google_bootstrap_accepts_matching_web_client_json(monkeypatch):
    entry = _entry()
    saved = []
    disconnected = []

    class FakeStore:
        @staticmethod
        def normalize(value):
            item = value["web"]
            return {
                "client_id": item["client_id"],
                "client_secret": item["client_secret"],
                "redirect_uris": item["redirect_uris"],
            }

        def configured(self):
            return bool(saved)

        def save(self, value):
            saved.append(value)

    monkeypatch.setattr(entry, "CredentialStore", FakeStore)
    monkeypatch.setattr(entry, "_redirect_uri", lambda: "https://tumelo-job-agent.vercel.app/api/google/callback")
    monkeypatch.setattr(entry, "disconnect", lambda: disconnected.append(True))
    payload = {
        "web": {
            "client_id": "new.apps.googleusercontent.com",
            "client_secret": "secret",
            "redirect_uris": ["https://tumelo-job-agent.vercel.app/api/google/callback"],
        }
    }
    with TestClient(entry.app) as client:
        response = client.post(
            "/api/google/bootstrap",
            files={"file": ("client.json", json.dumps(payload), "application/json")},
        )
    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert saved and disconnected


def test_google_bootstrap_rejects_wrong_redirect(monkeypatch):
    entry = _entry()

    class FakeStore:
        @staticmethod
        def normalize(value):
            item = value["web"]
            return {
                "client_id": item["client_id"],
                "client_secret": item["client_secret"],
                "redirect_uris": item["redirect_uris"],
            }

        def configured(self):
            return False

        def save(self, value):
            raise AssertionError("invalid credentials must not be saved")

    monkeypatch.setattr(entry, "CredentialStore", FakeStore)
    monkeypatch.setattr(entry, "_redirect_uri", lambda: "https://tumelo-job-agent.vercel.app/api/google/callback")
    payload = {
        "web": {
            "client_id": "new.apps.googleusercontent.com",
            "client_secret": "secret",
            "redirect_uris": ["https://wrong.example/callback"],
        }
    }
    with TestClient(entry.app) as client:
        response = client.post(
            "/api/google/bootstrap",
            files={"file": ("client.json", json.dumps(payload), "application/json")},
        )
    assert response.status_code == 400
    assert "redirect URI" in response.json()["error"]["message"]


def test_google_callback_without_params_starts_owner_sign_in(monkeypatch):
    entry = _entry()
    captured = []

    def fake_start(features):
        captured.extend(features)
        return {"authorization_url": "https://accounts.google.test/owner", "state": "state"}

    monkeypatch.setattr(entry, "start_authorization", fake_start)
    with TestClient(entry.app) as client:
        response = client.get("/api/google/callback", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "https://accounts.google.test/owner"
    assert "identity" in captured


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


def test_unverified_google_email_is_rejected(monkeypatch):
    entry = _entry()
    disconnected = []
    monkeypatch.setattr(entry, "load_profile", lambda: {"email": "maloseramokolo05@gmail.com"})
    monkeypatch.setattr(entry, "complete_authorization", lambda code, state: {"connected": True})
    monkeypatch.setattr(entry, "access_token", lambda: "access-token")
    monkeypatch.setattr(
        entry.requests,
        "get",
        lambda *args, **kwargs: GoogleProfileResponse("maloseramokolo05@gmail.com", verified=False),
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
