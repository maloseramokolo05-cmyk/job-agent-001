from __future__ import annotations
import json,logging,os,threading,uuid
from datetime import datetime,timedelta,timezone
from backend.config import private_path,load_profile,load_preferences,env_int
from backend.database import connect,now,event
from agents.cv_parser import find_master,parse_cv
from agents.repository import ingest,update_analysis
from agents.scoring import score_job
from agents.documents import generate_cv
from agents.verification import verify_job
from job_sources.registry import production_sources
from job_sources.sample import SampleSource
log=logging.getLogger("job_agent.pipeline");_lock=threading.Lock()
def cv_text():
 path=find_master(private_path("cv"));return parse_cv(path) if path else ""
def _claim_lock(owner):
 expires=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
 with connect() as db:
  db.execute("DELETE FROM run_locks WHERE expires_at<?",(now(),))
  try:db.execute("INSERT INTO run_locks VALUES('job-search',?,?)",(owner,expires));return True
  except Exception:return False
def run(include_sample=False):
 owner=str(uuid.uuid4())
 if not _lock.acquire(False):raise RuntimeError("A job search is already running")
 if not _claim_lock(owner):
  _lock.release();raise RuntimeError("A job search is already running")
 run_id=None
 try:
  with connect() as db:run_id=db.execute("INSERT INTO runs(started_at,state,message) VALUES(?,?,?)",(now(),"RUNNING","Starting verified source search")).lastrowid
  profile,prefs=load_profile(),load_preferences();master=cv_text();sources=production_sources()+([SampleSource()] if include_sample and os.getenv("ALLOW_SAMPLE_SOURCE","false").lower()=="true" else []);stats={"discovered":0,"duplicates":0,"verified":0,"analyzed":0,"strong_matches":0,"documents_prepared":0,"manual_required":0,"errors":0};maximum=env_int("MAX_JOBS_PER_RUN",100);threshold=float(prefs.get("minimum_score",75))
  for source in sources:
   count=0
   try:
    with connect() as db:db.execute("UPDATE runs SET message=?,checkpoint=?,progress=? WHERE id=?",(f"Searching {source.name}...",json.dumps({"source":source.name,"stats":stats}),min(95,int(100*stats["discovered"]/maximum)),run_id))
    discovered=source.search(profile,prefs)[:max(0,maximum-stats["discovered"])]
    for job in discovered:
     count+=1;stats["discovered"]+=1;verification=verify_job(job);job_id,duplicate=ingest(job,verification)
     if duplicate:stats["duplicates"]+=1;continue
     if not verification["active"]:
      with connect() as db:db.execute("UPDATE jobs SET status='EXPIRED' WHERE id=?",(job_id,))
      continue
     stats["verified"]+=1;result=score_job(job.dict(),profile,prefs,master);selected=result["score"]>=threshold and result["must_have"]["passed"];update_analysis(job_id,result,"SHORTLISTED" if selected else "DISCOVERED");stats["analyzed"]+=1
     if selected:
      stats["strong_matches"]+=1;mode=prefs.get("application_mode","PREPARE")
      if mode!="DISCOVER_ONLY" and master:
       docx,_=generate_cv(job.dict(),profile,master,job_id);status="PREPARED" if source.application_supported else "NEEDS_USER_ACTION"
       with connect() as db:db.execute("UPDATE jobs SET cv_path=?,status=? WHERE id=?",(docx,status,job_id))
       stats["documents_prepared"]+=1
      if not source.application_supported:stats["manual_required"]+=1
    with connect() as db:db.execute("INSERT OR REPLACE INTO source_status(source_name,supported,authenticated,search_supported,application_supported,status,last_success,last_error,jobs_found) VALUES(?,?,?,?,?,'CONNECTED',?,NULL,?)",(source.name,int(source.supported),int(source.authenticated),int(source.search_supported),int(source.application_supported),now(),count))
   except Exception as exc:
    log.exception("source=%s run_id=%s event=SOURCE_ERROR",source.name,run_id);stats["errors"]+=1;event("SOURCE_ERROR",f"{source.name}: {exc}",run_id=run_id)
    with connect() as db:db.execute("INSERT OR REPLACE INTO source_status(source_name,supported,authenticated,search_supported,application_supported,status,last_error,jobs_found) VALUES(?,?,?,?,?,'TEMPORARY_ERROR',?,0)",(source.name,int(source.supported),int(source.authenticated),int(source.search_supported),int(source.application_supported),str(exc)[:500]))
  with connect() as db:db.execute("UPDATE runs SET finished_at=?,state='COMPLETED',progress=100,message='Run complete',stats=? WHERE id=?",(now(),json.dumps(stats),run_id));return {"run_id":run_id,**stats}
 except Exception as exc:
  if run_id:
   with connect() as db:db.execute("UPDATE runs SET finished_at=?,state='ERROR',message=? WHERE id=?",(now(),str(exc),run_id))
  raise
 finally:
  with connect() as db:db.execute("DELETE FROM run_locks WHERE owner=?",(owner,))
  _lock.release()
