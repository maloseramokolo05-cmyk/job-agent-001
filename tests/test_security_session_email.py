import hashlib
import time

from backend import database
from backend.security import _signature, session_user


def test_session_user_accepts_dotted_email_username(monkeypatch):
    username = "maloseramokolo05@gmail.com"
    value = f"{username}.{int(time.time()) + 3600}.random-session-part"
    token = f"{value}.{_signature(value)}"
    expected_hash = hashlib.sha256(token.encode()).hexdigest()

    def fake_row(sql, params):
        assert params[0] == expected_hash
        return {"username": username}

    monkeypatch.setattr(database, "row", fake_row)

    assert session_user(token) == username
