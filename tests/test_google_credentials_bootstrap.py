import json

from integrations.google.credentials import CredentialStore


def google_json():
    return {
        "web": {
            "client_id": "123456-example.apps.googleusercontent.com",
            "client_secret": "test-secret",
            "redirect_uris": ["https://example.test/api/google/callback"],
        }
    }


def test_migrate_bootstrap_encrypts_and_removes_plaintext(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    store = CredentialStore()
    values = {store.BOOTSTRAP_KEY: json.dumps(google_json())}
    deleted = []
    saved = []
    cleared = []

    def fake_row(_sql, args):
        value = values.get(args[0])
        return {"value": value} if value is not None else None

    def fake_execute(_sql, args):
        deleted.append(args[0])
        values.pop(args[0], None)

    def fake_save(self, value):
        normalized = self.normalize(value)
        saved.append(normalized)
        values[self.KEY] = "encrypted-placeholder"
        return normalized

    monkeypatch.setattr("backend.database.row", fake_row)
    monkeypatch.setattr("backend.database.execute", fake_execute)
    monkeypatch.setattr(CredentialStore, "save", fake_save)
    monkeypatch.setattr("integrations.google.credentials.TokenStore.clear", lambda self: cleared.append(True))

    migrated = store.migrate_bootstrap()

    assert migrated["client_id"].endswith(".apps.googleusercontent.com")
    assert saved
    assert cleared == [True]
    assert deleted == [store.BOOTSTRAP_KEY]
    assert store.BOOTSTRAP_KEY not in values


def test_migrate_bootstrap_does_nothing_when_encrypted_credentials_exist(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    store = CredentialStore()

    monkeypatch.setattr(
        "backend.database.row",
        lambda _sql, args: {"value": "already-encrypted"} if args[0] == store.KEY else None,
    )

    assert store.migrate_bootstrap() is None
