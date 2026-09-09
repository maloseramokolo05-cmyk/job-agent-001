from __future__ import annotations
import json, os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def _json(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as f: return json.load(f)

def load_profile() -> dict: return _json("profile.json")
def load_preferences() -> dict: return _json("job_preferences.json")
def save_json(name: str, value: dict) -> None:
    path=ROOT/"config"/name; tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n", encoding="utf-8"); tmp.replace(path)
def database_path() -> Path:
    p=Path(os.getenv("DATABASE_PATH", "data/job_agent.db")); return p if p.is_absolute() else ROOT/p
def env_int(name: str, default: int) -> int: return int(os.getenv(name, default))
