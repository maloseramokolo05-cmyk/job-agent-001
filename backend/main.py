from __future__ import annotations
import csv,io,json,logging,os
from pathlib import Path
from fastapi import FastAPI,HTTPException,BackgroundTasks,UploadFile,File
from fastapi.responses import FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.config import ROOT,load_profile,load_preferences,save_json
from backend.database import init_db,rows,row,connect,now,event
from agents.pipeline import run,cv_text
from agents.documents import generate_cv,generate_cover_letter
app=FastAPI(title="Tumelo Job Agent",version="1.0.0")
class Status(BaseModel): status:str
class Setup(BaseModel): profile:dict; preferences:dict
ALLOWED={"FOUND","ANALYZED","SHORTLISTED","CV GENERATED","READY TO APPLY","APPLYING","APPLIED","MANUAL REQUIRED","NEEDS USER INPUT","SKIPPED","REJECTED","INTERVIEW","OFFER","ERROR"}
@app.on_event("startup")
def startup():
 init_db(); (ROOT/"logs").mkdir(exist_ok=True); logging.basicConfig(filename=ROOT/"logs/job_agent.log",level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
@app.get("/api/health")
def health(): return {"status":"ok","cv_loaded":bool(cv_text())}
@app.get("/api/config")
def config(): return {"profile":load_profile(),"preferences":load_preferences(),"openai_configured":bool(os.getenv("OPENAI_API_KEY"))}
@app.post("/api/setup")
def setup(value:Setup): save_json("profile.json",value.profile); save_json("job_preferences.json",value.preferences); return {"saved":True}
@app.post("/api/cv")
async def upload_cv(file:UploadFile=File(...)):
 suffix=Path(file.filename or "").suffix.lower()
 if suffix not in {".pdf",".docx"}: raise HTTPException(400,"CV must be PDF or DOCX")
 content=await file.read()
 if len(content)>10_000_000: raise HTTPException(413,"CV exceeds 10 MB")
 path=ROOT/"cv"/("master_cv"+suffix); path.write_bytes(content); return {"saved":str(path.relative_to(ROOT))}
@app.get("/api/jobs")
def jobs(status:str|None=None,min_score:float=0,q:str=""):
 sql="SELECT * FROM jobs WHERE COALESCE(score,0)>=?"; args=[min_score]
 if status: sql+=" AND status=?"; args.append(status)
 if q: sql+=" AND (title LIKE ? OR company LIKE ? OR location LIKE ?)"; args += [f"%{q}%"]*3
 return rows(sql+" ORDER BY discovered_at DESC",args)
@app.get("/api/jobs/{job_id}")
def job(job_id:int):
 value=row("SELECT * FROM jobs WHERE id=?",(job_id,));
 if not value: raise HTTPException(404,"Job not found")
 value["history"]=rows("SELECT * FROM events WHERE job_id=? ORDER BY created_at DESC",(job_id,)); return value
@app.post("/api/jobs/{job_id}/status")
def set_status(job_id:int,value:Status):
 if value.status not in ALLOWED: raise HTTPException(400,"Invalid status")
 with connect() as db:
  if not db.execute("SELECT 1 FROM jobs WHERE id=?",(job_id,)).fetchone(): raise HTTPException(404,"Job not found")
  db.execute("UPDATE jobs SET status=? WHERE id=?",(value.status,job_id))
  if value.status == "APPLIED" and not db.execute("SELECT 1 FROM applications WHERE job_id=? AND status='APPLIED'",(job_id,)).fetchone():
   source=db.execute("SELECT source FROM jobs WHERE id=?",(job_id,)).fetchone()[0]
   db.execute("INSERT INTO applications(job_id,application_date,source,status,created_at) VALUES(?,?,?,?,?)",(job_id,now(),source,"APPLIED",now()))
 event("STATUS_CHANGED",value.status,job_id); return {"status":value.status}
@app.post("/api/jobs/{job_id}/cv")
def make_cv(job_id:int):
 j=row("SELECT * FROM jobs WHERE id=?",(job_id,)); master=cv_text()
 if not j: raise HTTPException(404,"Job not found")
 try: docx,pdf=generate_cv(j,load_profile(),master)
 except ValueError as e: raise HTTPException(400,str(e))
 with connect() as db: db.execute("UPDATE jobs SET cv_path=?,status='CV GENERATED' WHERE id=?",(docx,job_id))
 return {"docx":docx,"pdf":pdf}
@app.post("/api/jobs/{job_id}/cover-letter")
def cover(job_id:int):
 j=row("SELECT * FROM jobs WHERE id=?",(job_id,));
 if not j: raise HTTPException(404,"Job not found")
 try: path=generate_cover_letter(j,load_profile(),cv_text())
 except ValueError as e: raise HTTPException(400,str(e))
 with connect() as db: db.execute("UPDATE jobs SET cover_letter_path=? WHERE id=?",(path,job_id))
 return {"path":path}
@app.post("/api/runs")
def start_run(background:BackgroundTasks,sample:bool=False): background.add_task(run,sample); return {"started":True}
@app.get("/api/runs/latest")
def latest(): return row("SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {"state":"IDLE","progress":0,"message":"Ready","stats":"{}"}
@app.get("/api/overview")
def overview():
 return row("SELECT COUNT(*) jobs_found, SUM(status IN ('ANALYZED','SHORTLISTED','CV GENERATED','READY TO APPLY')) analyzed, SUM(score>=80) strong_matches, SUM(status='APPLIED') submitted, SUM(status IN ('MANUAL REQUIRED','NEEDS USER INPUT')) manual_pending, SUM(status='INTERVIEW') interviews, SUM(status='ERROR') errors FROM jobs")
@app.get("/api/export.csv")
def export_csv():
 data=rows("SELECT company,title vacancy,discovered_at application_date,cv_path cv_version,source,status,salary FROM jobs ORDER BY discovered_at DESC"); out=io.StringIO(); w=csv.DictWriter(out,fieldnames=data[0].keys() if data else ["company","vacancy","status"]); w.writeheader(); w.writerows(data); return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=applications.csv"})
app.mount("/assets",StaticFiles(directory=ROOT/"frontend"),name="assets")
@app.get("/")
def index(): return FileResponse(ROOT/"frontend/index.html")
