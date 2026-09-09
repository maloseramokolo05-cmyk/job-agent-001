from __future__ import annotations
import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load_env(path=ROOT/".env"):
 if not path.exists():return
 for raw in path.read_text(encoding="utf-8").splitlines():
  line=raw.strip()
  if not line or line.startswith("#") or "=" not in line:continue
  key,value=line.split("=",1);key=key.strip();value=value.strip().strip('"').strip("'")
  if key and key not in os.environ:os.environ[key]=value
load_env()
def _json(name):
 with (ROOT/"config"/name).open(encoding="utf-8") as handle:return json.load(handle)
def load_profile():return _json("profile.json")
def load_preferences():return _json("job_preferences.json")
def save_json(name,value):
 path=ROOT/"config"/name;tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");tmp.replace(path)
def database_path():
 path=Path(os.getenv("DATABASE_PATH","data/job_agent.db"));return path if path.is_absolute() else ROOT/path
def env_int(name,default):return int(os.getenv(name,default))
