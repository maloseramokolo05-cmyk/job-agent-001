import os,subprocess
from pathlib import Path
from backend.config import ROOT
from backend.database import init_db,schema_version,connect

def test_migration_and_interrupted_recovery():
 init_db()
 with connect() as db: db.execute("INSERT INTO runs(started_at,state) VALUES('2026-01-01','RUNNING')")
 init_db()
 with connect() as db: assert db.execute("SELECT state FROM runs ORDER BY id DESC LIMIT 1").fetchone()[0]=="INTERRUPTED"
 assert schema_version()==2

def test_android_scripts_are_safe_and_valid():
 for name in ["INSTALL_ANDROID.sh","START_ANDROID.sh","STOP_ANDROID.sh","UPDATE_ANDROID.sh","scripts/status_android.sh"]:
  path=ROOT/name; assert path.exists() and os.access(path,os.X_OK);subprocess.run(["bash","-n",str(path)],check=True)
 stop=(ROOT/"STOP_ANDROID.sh").read_text();assert "killall" not in stop and "pkill" not in stop and ".pid" in stop

def test_private_paths():
 assert not str(ROOT/"cv").startswith(str(ROOT/"frontend"));assert "data/tokens/" in (ROOT/".gitignore").read_text()
