from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from backend.config import ROOT


class TokenStore:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / "data/tokens/google_token.json")

    @staticmethod
    def _fernet():
        secret = os.getenv("TOKEN_ENCRYPTION_KEY") or os.getenv("SESSION_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY or SESSION_SECRET must be at least 32 characters")
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)

    def _database_mode(self):
        return bool(os.getenv("DATABASE_URL"))

    def save(self, value):
        if self._database_mode():
            from backend.database import connect, using_postgres

            encrypted = self._fernet().encrypt(json.dumps(value).encode()).decode()
            with connect() as db:
                if using_postgres():
                    db.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                        ("secret:google_token", encrypted),
                    )
                else:
                    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", ("secret:google_token", encrypted))
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def load(self):
        if self._database_mode():
            from backend.database import row

            item = row("SELECT value FROM settings WHERE key=?", ("secret:google_token",))
            if not item:
                return None
            try:
                return json.loads(self._fernet().decrypt(item["value"].encode()).decode())
            except Exception:
                return None
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def clear(self):
        if self._database_mode():
            from backend.database import execute

            execute("DELETE FROM settings WHERE key=?", ("secret:google_token",))
            return
        if self.path.exists():
            self.path.unlink()

    def summary(self):
        token = self.load() or {}
        return {
            "connected": bool(token.get("access_token") or token.get("refresh_token")),
            "scopes": token.get("scope", "").split(),
            "expires_at": token.get("expires_at"),
        }
