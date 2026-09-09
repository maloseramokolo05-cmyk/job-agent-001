from __future__ import annotations
import json,logging,threading
from backend.config import ROOT,load_profile,load_preferences,env_int
from backend.database import connect,now,event
from agents.cv_parser import find_master,parse_cv
from agents.repository import ingest,update_analysis
from agents.scoring import score_job
from agents.documents import generate_cv
from job_sources.sample import SampleSource
from job_sources.rss import RSSSource
log=logging.getLogger("job_agent")
_lock=threading.Lock()
def cv_text():
 path=find_master(ROOT/"cv"); return parse_cv(path) if path else ""
def run(include_sample=False):
 if not _lock.acquire(False): raise RuntimeError("A job run is already active")
 run_id=None
 try:
  with connect() as db: run_id=db.execute("INSERT INTO runs(started_at,state,message) VALUES(?,?,?)",(now(),"RUNNING","Starting search")).lastrowid
  profile,prefs=load_profile(),load_preferences(); master=cv_text(); sources=[RSSSource()]+([SampleSource()] if include_sample else [])
  stats={"discovered":0,"duplicates":0,"analyzed":0,"strong_matches":0,"documents_prepared":0,"manual_required":0,"errors":0}
  maximum=env_int("MAX_JOBS_PER_RUN",100); threshold=float(prefs.get("minimum_score",75))
  for source in sources:
   try:
    with connect() as db: db.execute("UPDATE runs SET message=? WHERE id=?",(f"Searching {source.name}...",run_id))
    for job in source.search(profile,prefs)[:maximum-stats["discovered"]]:
     stats["discovered"]+=1; job_id,duplicate=ingest(job)
     if duplicate: stats["duplicates"]+=1; continue
     result=score_job(job.dict(),profile,prefs,master); selected=result["score"]>=threshold
     status="SHORTLISTED" if selected else "ANALYZED"; update_analysis(job_id,result,status); stats["analyzed"]+=1
     if selected:
      stats["strong_matches"]+=1
      mode=prefs.get("application_mode","PREPARE")
      if mode in {"DOCUMENTS","PREPARE","AUTO_APPLY"} and master:
       docx,pdf=generate_cv(job.dict(),profile,master)
       with connect() as db: db.execute("UPDATE jobs SET cv_path=?,status=? WHERE id=?",(docx,"READY TO APPLY" if mode in {"PREPARE","AUTO_APPLY"} else "CV GENERATED",job_id))
       stats["documents_prepared"]+=1
     # Generic sources are deliberately manual unless a dedicated permitted adapter exists.
     if selected and source.name!="sample":
      with connect() as db: db.execute("UPDATE jobs SET status='MANUAL REQUIRED' WHERE id=?",(job_id,)); stats["manual_required"]+=1
   except Exception as exc: log.exception("Source %s failed",source.name); stats["errors"]+=1; event("SOURCE_ERROR",f"{source.name}: {exc}")
  with connect() as db: db.execute("UPDATE runs SET finished_at=?,state='COMPLETED',progress=100,message='Run complete',stats=? WHERE id=?",(now(),json.dumps(stats),run_id))
  return {"run_id":run_id,**stats}
 except Exception as exc:
  if run_id:
   with connect() as db: db.execute("UPDATE runs SET finished_at=?,state='ERROR',message=? WHERE id=?",(now(),str(exc),run_id))
  raise
 finally: _lock.release()
