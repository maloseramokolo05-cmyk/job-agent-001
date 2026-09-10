from integrations.google.credentials import CredentialStore
from integrations.google import oauth


def test_credential_store_round_trip(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = CredentialStore(tmp_path / "google.json")
    saved = store.save({"web": {"client_id": "new.apps.googleusercontent.com", "client_secret": "secret", "redirect_uris": ["https://example.test/callback"]}})
    assert saved["client_id"] == "new.apps.googleusercontent.com"
    assert store.load()["client_secret"] == "secret"
    assert store.configured()


def test_client_config_prefers_stored_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "old.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "old-secret")
    monkeypatch.setattr(oauth, "CredentialStore", lambda: CredentialStore(tmp_path / "google.json"))
    CredentialStore(tmp_path / "google.json").save({"web": {"client_id": "new.apps.googleusercontent.com", "client_secret": "new-secret"}})
    assert oauth.client_config() == ("new.apps.googleusercontent.com", "new-secret")
