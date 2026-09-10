from __future__ import annotations

import json
import os
from pathlib import Path

from backend.config import ROOT
from integrations.google.token_store import TokenStore


class CredentialStore:
    """Encrypted Google OAuth client credentials stored outside source control."""

    KEY = "secret:google_client"

    def __init__(self, path=None):
        self.path = Path(path or ROOT / "data/secrets/google_client.json")

    def _database_mode(self):
        return bool(os.getenv("DATABASE_URL"))

    @staticmethod
    def normalize(value):
        if not isinstance(value, dict):
            raise ValueError("Google credentials must be a JSON object")
        item = value.get("web") or value.get("installed") or value
        if not isinstance(item, dict):
            raise ValueError("Google credentials JSON is invalid")
        client_id = str(item.get("client_id", "")).strip()
        client_secret = str(item.get("client_secret", "")).strip()
        if not client_id or not client_id.endswith(".apps.googleusercontent.com"):
            raise ValueError("Google OAuth client_id is missing or invalid")
        if not client_secret:
            raise ValueError("Google OAuth client_secret is missing")
        redirects = item.get("redirect_uris") or []
        if not isinstance(redirects, list):
            redirects = []
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [str(x).strip() for x in redirects if str(x).strip()],
        }

    def save(self, value):
        normalized = self.normalize(value)
        if self._database_mode():
            from backend.database import connect, using_postgres

            encrypted = TokenStore._fernet().encrypt(json.dumps(normalized).encode()).decode()
            with connect() as db:
                if using_postgres():
                    db.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                        (self.KEY, encrypted),
                    )
                else:
                    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (self.KEY, encrypted))
            return normalized
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(normalized), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return normalized

    def load(self):
        if self._database_mode():
            from backend.database import row

            item = row("SELECT value FROM settings WHERE key=?", (self.KEY,))
            if not item:
                return None
            try:
                raw = TokenStore._fernet().decrypt(item["value"].encode()).decode()
                return json.loads(raw)
            except Exception:
                return None
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def configured(self):
        item = self.load() or {}
        return bool(item.get("client_id") and item.get("client_secret"))

    def clear(self):
        if self._database_mode():
            from backend.database import execute

            execute("DELETE FROM settings WHERE key=?", (self.KEY,))
            return
        if self.path.exists():
            self.path.unlink()
