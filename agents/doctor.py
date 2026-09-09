from __future__ import annotations
import os,platform,sys
from backend.config import database_path,load_profile,load_preferences,storage_path,app_base_url
from backend.database import init_db,schema_version
from agents.cv_parser import find_master
from integrations.google.oauth import client_config
from integrations.google.token_store import TokenStore
def run_doctor():
 checks=[]
 def add(name,status,detail):checks.append((name,status,detail))
 add("Python","PASS" if sys.version_info>=(3,12) else "FAIL",platform.python_version())
 try:init_db();add("Database","PASS",f"schema {schema_version()} at {database_path()}")
 except Exception as exc:add("Database","FAIL",str(exc))
 for folder in ("cv","data","logs","generated_cvs","cover_letters","runtime","config"):
  path=storage_path(folder);path.mkdir(parents=True,exist_ok=True);add(f"Folder {folder}","PASS" if os.access(path,os.W_OK) else "FAIL","writable" if os.access(path,os.W_OK) else "not writable")
 try:load_profile();load_preferences();add("Configuration","PASS","JSON loaded")
 except Exception as exc:add("Configuration","FAIL",str(exc))
 master=find_master(storage_path("cv"));add("Master CV","PASS" if master else "WARN","loaded" if master else "upload PDF/DOCX in dashboard")
 cid,_=client_config();add("Google credentials","PASS" if cid else "WARN","configured" if cid else "not configured")
 add("Google token","PASS" if TokenStore().summary()["connected"] else "WARN","connected" if TokenStore().summary()["connected"] else "not connected")
 add("Website URL","PASS",app_base_url())
 auth_enabled=os.getenv("APP_AUTH_ENABLED","false").lower() in {"1","true","yes","on"}
 auth_ready=bool(os.getenv("APP_USERNAME") and os.getenv("APP_PASSWORD"))
 add("Hosted authentication","PASS" if not auth_enabled or auth_ready else "FAIL","enabled" if auth_enabled and auth_ready else "disabled" if not auth_enabled else "credentials missing")
 add("Scheduler","PASS","APScheduler configuration available")
 add("Sources","PASS",f"{len(load_preferences().get('search_feeds',[]))} configured feed(s)")
 return checks
def print_doctor():
 checks=run_doctor()
 for name,status,detail in checks:print(f"{status:4} {name}: {detail}")
 return 1 if any(s=="FAIL" for _,s,_ in checks) else 0
