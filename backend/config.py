from __future__ import annotations
import json,os,shutil
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

DATA_ROOT=Path(os.getenv("APP_DATA_DIR",str(ROOT))).expanduser()
if not DATA_ROOT.is_absolute(): DATA_ROOT=ROOT/DATA_ROOT

def storage_path(*parts:str)->Path:
 path=DATA_ROOT.joinpath(*parts)
 path.parent.mkdir(parents=True,exist_ok=True)
 return path

def _config_path(name:str)->Path:
 # Runtime-edited profile/preferences live on persistent storage when APP_DATA_DIR is set.
 target=storage_path("config",name)
 if target.exists(): return target
 source=ROOT/"config"/name
 target.parent.mkdir(parents=True,exist_ok=True)
 if DATA_ROOT!=ROOT and source.exists(): shutil.copy2(source,target)
 return target if target.exists() else source

def _json(name):
 with _config_path(name).open(encoding="utf-8") as handle:return json.load(handle)
def load_profile():return _json("profile.json")
def load_preferences():return _json("job_preferences.json")
def save_json(name,value):
 path=_config_path(name);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");tmp.replace(path)
def database_path():
 configured=os.getenv("DATABASE_PATH","").strip()
 if configured:
  path=Path(configured);return path if path.is_absolute() else DATA_ROOT/path
 return storage_path("data","job_agent.db")
def env_int(name,default):return int(os.getenv(name,default))
def app_base_url():
 value=os.getenv("APP_BASE_URL","").strip().rstrip("/")
 if value:return value
 render_host=os.getenv("RENDER_EXTERNAL_HOSTNAME","").strip()
 return f"https://{render_host}" if render_host else "http://127.0.0.1:8000"
