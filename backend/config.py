from __future__ import annotations
import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load_env(path=ROOT/".env"):
 if not path.exists():return
 for raw in path.read_text(encoding="utf-8").splitlines():
  line=raw.strip()
  if not line or line.startswith("#") or "=" not in line:continue
  key,value=line.split("=",1);os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))
load_env()
DATA_ROOT=Path(os.getenv("APP_DATA_DIR",ROOT)).expanduser().resolve()
def private_path(*parts):return DATA_ROOT.joinpath(*parts)
def config_path(name):
 hosted=private_path("config",name); bundled=ROOT/"config"/name
 if not hosted.exists():
  hosted.parent.mkdir(parents=True,exist_ok=True); hosted.write_text(bundled.read_text(encoding="utf-8"),encoding="utf-8")
 return hosted
def _json(name):return json.loads(config_path(name).read_text(encoding="utf-8"))
def load_profile():return _json("profile.json")
def load_preferences():return _json("job_preferences.json")
def save_json(name,value):
 path=config_path(name);tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");tmp.replace(path)
def database_path():
 path=Path(os.getenv("DATABASE_PATH","data/job_agent.db"));return path if path.is_absolute() else private_path(path)
def env_int(name,default):return int(os.getenv(name,default))
