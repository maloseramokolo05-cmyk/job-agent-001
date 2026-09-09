from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env()


def _file_json(name):
    with (ROOT / "config" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _db_config(name):
    if not os.getenv("DATABASE_URL"):
        return None
    try:
        from backend.database import row

        item = row("SELECT value FROM settings WHERE key=?", (f"config:{name}",))
        return json.loads(item["value"]) if item else None
    except Exception:
        return None


def load_profile():
    return _db_config("profile.json") or _file_json("profile.json")


def load_preferences():
    return _db_config("job_preferences.json") or _file_json("job_preferences.json")


def save_json(name, value):
    if os.getenv("DATABASE_URL"):
        from backend.database import connect

        payload = json.dumps(value, ensure_ascii=False)
        with connect() as db:
            if os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
                db.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                    (f"config:{name}", payload),
                )
            else:
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"config:{name}", payload))
        return
    path = ROOT / "config" / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def database_path():
    path = Path(os.getenv("DATABASE_PATH", "data/job_agent.db"))
    return path if path.is_absolute() else ROOT / path


def app_base_url():
    explicit = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    render = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render:
        return f"https://{render}"
    vercel = os.getenv("VERCEL_PROJECT_PRODUCTION_URL") or os.getenv("VERCEL_URL")
    if vercel:
        return f"https://{vercel.strip().rstrip('/')}"
    return "http://127.0.0.1:8000"


def env_int(name, default):
    return int(os.getenv(name, default))
