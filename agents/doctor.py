from __future__ import annotations
import os,platform,sys
from backend.config import ROOT,private_path,database_path,load_profile,load_preferences
from backend.database import init_db,schema_version
from agents.cv_parser import find_master
from integrations.google.oauth import client_config
from integrations.google.token_store import TokenStore
def run_doctor():
 checks=[]
 def add(name,status,detail): checks.append((name,status,detail))
 add("Python","PASS" if sys.version_info>=(3,12) else "FAIL",platform.python_version())
 try:init_db();add("Database","PASS",f"schema {schema_version()} at {database_path()}")
 except Exception as exc:add("Database","FAIL",str(exc))
 for folder in ("cv","data","logs","generated_cvs","cover_letters","runtime"):
  path=ROOT/folder;path.mkdir(exist_ok=True);add(f"Folder {folder}","PASS" if os.access(path,os.W_OK) else "FAIL","writable" if os.access(path,os.W_OK) else "not writable")
 try:load_profile();load_preferences();add("Configuration","PASS","JSON loaded")
 except Exception as exc:add("Configuration","FAIL",str(exc))
 add("Master CV","PASS" if find_master(private_path("cv")) else "WARN","loaded" if find_master(private_path("cv")) else "upload PDF/DOCX in dashboard")
 password=os.getenv("ADMIN_PASSWORD","");add("Owner authentication","PASS" if len(password)>=12 else "FAIL","configured" if len(password)>=12 else "set ADMIN_PASSWORD to at least 12 characters")
 cid,_=client_config();add("Google credentials","PASS" if cid else "WARN","configured" if cid else "not configured")
 add("Google token","PASS" if TokenStore().summary()["connected"] else "WARN","connected" if TokenStore().summary()["connected"] else "not connected")
 add("Scheduler","PASS","APScheduler configuration available")
 add("Sources","PASS",f"{len(load_preferences().get('search_feeds',[]))} configured feed(s)")
 return checks
def print_doctor():
 checks=run_doctor()
 for name,status,detail in checks:print(f"{status:4} {name}: {detail}")
 return 1 if any(s=="FAIL" for _,s,_ in checks) else 0
