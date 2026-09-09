from __future__ import annotations
import csv,io,json,logging,os,platform,secrets
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import FastAPI,HTTPException,BackgroundTasks,UploadFile,File,Query,Request
from fastapi.responses import FileResponse,RedirectResponse,StreamingResponse,PlainTextResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from backend.version import __version__
from backend.config import ROOT,load_profile,load_preferences,save_json,database_path
from backend.database import init_db,schema_version,rows,row,connect,now,event
from agents.pipeline import run,cv_text
from agents.documents import generate_cv,generate_cover_letter
from job_sources.rss import RSSSource
from integrations.google.oauth import start_authorization,complete_authorization,disconnect
from integrations.google.token_store import TokenStore
from integrations.google.gmail import sync_messages,create_draft,send_message
from integrations.google.drive import list_app_files,upload_file
from integrations.google.calendar import create_event
from backend.security import COOKIE,CSRF_COOKIE,password_matches,rate_limit,new_session,session_user,require_csrf,revoke
from backend.storage import ObjectStorage
app=FastAPI(title="Tumelo Job Agent",version=__version__)
class Status(BaseModel): status:str
class Login(BaseModel): username:str=Field(min_length=1,max_length=100); password:str=Field(min_length=1,max_length=500)
class Setup(BaseModel): profile:dict; preferences:dict
class GmailDraft(BaseModel): to:str; subject:str; body:str; thread_id:str|None=None
class CalendarInput(BaseModel): event:dict; confirmed:bool=False
class GoogleStart(BaseModel): features:list[str]=Field(default_factory=lambda:["gmail","drive","calendar"])
ALLOWED={"DISCOVERED","SHORTLISTED","PREPARED","NEEDS_USER_INPUT","READY_TO_APPLY","MANUAL_APPLICATION","APPLIED","APPLIED_CONFIRMED","INTERVIEW","ASSESSMENT","REJECTED","OFFER","WITHDRAWN","EXPIRED"}
def setup_logging():
 log=ROOT/"logs/job_agent.log"; log.parent.mkdir(exist_ok=True); handler=RotatingFileHandler(log,maxBytes=2_000_000,backupCount=4,encoding="utf-8"); handler.setFormatter(logging.Formatter('{"time":"%(asctime)s","severity":"%(levelname)s","component":"%(name)s","message":"%(message)s"}')); logging.getLogger().setLevel(logging.INFO); logging.getLogger().addHandler(handler)
@app.on_event("startup")
def startup():
 init_db(); setup_logging()
 if os.getenv("APP_ENV")=="production":
  if len(os.getenv("SESSION_SECRET",""))<32: raise RuntimeError("SESSION_SECRET must be at least 32 characters")
  if not os.getenv("ADMIN_PASSWORD_HASH"): raise RuntimeError("ADMIN_PASSWORD_HASH is required")
  ObjectStorage()
 logging.getLogger("startup").info("event=APPLICATION_STARTED version=%s",__version__)

@app.middleware("http")
async def security(request:Request,call_next):
 auth_configured=bool(os.getenv("ADMIN_PASSWORD_HASH"))
 public=not auth_configured or request.url.path in {"/","/api/health","/api/ready","/api/auth/login"} or request.url.path.startswith("/assets/")
 if not public and not session_user(request.cookies.get(COOKIE)):
  response=JSONResponse({"error":{"code":"UNAUTHENTICATED","message":"Authentication required"}},401)
 elif not public and request.method not in {"GET","HEAD","OPTIONS"} and not secrets.compare_digest(request.cookies.get(CSRF_COOKIE,""),request.headers.get("X-CSRF-Token","")):
  response=JSONResponse({"error":{"code":"CSRF_FAILED","message":"CSRF validation failed"}},403)
 else: response=await call_next(request)
 response.headers.update({"X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","X-Frame-Options":"DENY","Content-Security-Policy":"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
 return response

@app.exception_handler(HTTPException)
async def http_error(_request,exc): return JSONResponse({"error":{"code":"REQUEST_FAILED","message":str(exc.detail)}},exc.status_code)

@app.post("/api/auth/login")
def login(value:Login,request:Request):
 rate_limit(request.client.host if request.client else "unknown")
 if value.username!=os.getenv("ADMIN_USERNAME","admin") or not password_matches(value.password): raise HTTPException(401,"Invalid username or password")
 token=new_session(value.username); csrf=secrets.token_urlsafe(32); secure=os.getenv("APP_ENV")=="production"
 response=JSONResponse({"authenticated":True,"csrf_token":csrf})
 response.set_cookie(COOKIE,token,httponly=True,secure=secure,samesite="strict",max_age=43200,path="/")
 response.set_cookie(CSRF_COOKIE,csrf,httponly=False,secure=secure,samesite="strict",max_age=43200,path="/")
 return response

@app.post("/api/auth/logout")
def logout(request:Request):
 revoke(request.cookies.get(COOKIE)); response=JSONResponse({"authenticated":False}); response.delete_cookie(COOKIE,path="/"); response.delete_cookie(CSRF_COOKIE,path="/"); return response

@app.get("/api/auth/session")
def auth_session(request:Request): return {"authenticated":True,"username":session_user(request.cookies.get(COOKIE))}
@app.get("/api/health")
def health():
 google=TokenStore().summary(); return {"status":"ok","version":__version__,"platform":platform.system().lower(),"database":{"ready":schema_version()==2,"schema_version":schema_version()},"scheduler":"external_process","google":{"connected":google["connected"]},"job_connector_count":3}
@app.get("/api/ready")
def ready():
 storage=ObjectStorage().healthy(); database=schema_version()==2
 body={"status":"ready" if storage and database else "not_ready","database":database,"storage":storage,"scheduler_configured":bool(os.getenv("CRON_SECRET")),"google_configured":bool(os.getenv("GOOGLE_CLIENT_ID")),"connectors":["greenhouse","lever","rss"]}
 return JSONResponse(body,200 if storage and database else 503)
@app.get("/api/config")
def config(): return {"profile":load_profile(),"preferences":load_preferences(),"openai_configured":bool(os.getenv("OPENAI_API_KEY"))}
@app.get("/api/profile")
def profile(): return load_profile()
@app.put("/api/profile")
def save_profile(value:dict): save_json("profile.json",value); return {"saved":True}
@app.get("/api/settings")
def settings(): return load_preferences()
@app.put("/api/settings")
def save_settings(value:dict): save_json("job_preferences.json",value); return {"saved":True}
@app.post("/api/setup")
def setup(value:Setup): save_json("profile.json",value.profile); save_json("job_preferences.json",value.preferences); return {"saved":True}
@app.post("/api/cv")
async def upload_cv(file:UploadFile=File(...)):
 suffix=Path(file.filename or "").suffix.lower()
 if suffix not in {".pdf",".docx"}: raise HTTPException(400,"CV must be PDF or DOCX")
 content=await file.read()
 if not content or len(content)>10_000_000: raise HTTPException(413,"CV must be between 1 byte and 10 MB")
 signatures={".pdf":b"%PDF-",".docx":b"PK"}
 if not content.startswith(signatures[suffix]): raise HTTPException(400,"File content does not match its extension")
 metadata=ObjectStorage().put(f"master-cvs/{secrets.token_hex(12)}{suffix}",content,file.content_type or "application/octet-stream")
 # Keep a working copy only outside production for local parsing; S3 remains authoritative in production.
 if os.getenv("APP_ENV")!="production":
  path=ROOT/"cv"/("master_cv"+suffix); path.write_bytes(content)
 from agents.cv_parser import parse_cv
 import tempfile
 with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
  tmp.write(content); tmp.flush(); extracted=parse_cv(tmp.name)
 with connect() as db:
  version=(db.execute("SELECT COALESCE(MAX(version),0)+1 FROM master_cvs WHERE username=?",(os.getenv("ADMIN_USERNAME","admin"),)).fetchone()[0])
  db.execute("INSERT INTO master_cvs(username,version,storage_key,sha256,content_type,original_name,extracted_text,created_at) VALUES(?,?,?,?,?,?,?,?)",(os.getenv("ADMIN_USERNAME","admin"),version,metadata["storage_key"],metadata["sha256"],metadata["content_type"],Path(file.filename or "cv").name,extracted,now()))
 return {"saved":True,"version":version,"sha256":metadata["sha256"],"extracted_text":extracted[:10000],"requires_verification":True}
@app.get("/api/jobs")
def jobs(status:str|None=None,min_score:float=0,q:str=""):
 sql="SELECT * FROM jobs WHERE COALESCE(score,0)>=?"; args=[min_score]
 if status:sql+=" AND status=?";args.append(status)
 if q:sql+=" AND (title LIKE ? OR company LIKE ? OR location LIKE ?)";args += [f"%{q}%"]*3
 return rows(sql+" ORDER BY priority DESC,score DESC,discovered_at DESC",args)
@app.get("/api/jobs/{job_id}")
def job(job_id:int):
 value=row("SELECT * FROM jobs WHERE id=?",(job_id,))
 if not value:raise HTTPException(404,"Job not found")
 value["history"]=rows("SELECT * FROM events WHERE job_id=? ORDER BY created_at DESC",(job_id,));return value
@app.post("/api/jobs/{job_id}/status")
def set_status(job_id:int,value:Status):
 if value.status not in ALLOWED:raise HTTPException(400,"Invalid status")
 with connect() as db:
  jobrow=db.execute("SELECT source FROM jobs WHERE id=?",(job_id,)).fetchone()
  if not jobrow:raise HTTPException(404,"Job not found")
  db.execute("UPDATE jobs SET status=? WHERE id=?",(value.status,job_id))
  if value.status=="APPLIED" and not db.execute("SELECT 1 FROM applications WHERE job_id=? AND status='APPLIED'",(job_id,)).fetchone():db.execute("INSERT INTO applications(job_id,application_date,source,status,created_at) VALUES(?,?,?,?,?)",(job_id,now(),jobrow[0],"APPLIED",now()))
 event("STATUS_CHANGED",value.status,job_id);return {"status":value.status}
@app.post("/api/jobs/{job_id}/cv")
def make_cv(job_id:int):
 j=row("SELECT * FROM jobs WHERE id=?",(job_id,)); master=cv_text()
 if not j:raise HTTPException(404,"Job not found")
 try:docx,pdf=generate_cv(j,load_profile(),master,job_id)
 except ValueError as exc:raise HTTPException(400,str(exc)) from exc
 with connect() as db:db.execute("UPDATE jobs SET cv_path=?,status='PREPARED' WHERE id=?",(docx,job_id))
 return {"docx":docx,"pdf":pdf}
@app.post("/api/jobs/{job_id}/cover-letter")
def cover(job_id:int):
 j=row("SELECT * FROM jobs WHERE id=?",(job_id,))
 if not j:raise HTTPException(404,"Job not found")
 try:path=generate_cover_letter(j,load_profile(),cv_text(),job_id)
 except ValueError as exc:raise HTTPException(400,str(exc)) from exc
 with connect() as db:db.execute("UPDATE jobs SET cover_letter_path=? WHERE id=?",(path,job_id))
 return {"path":path}
@app.get("/api/applications")
def applications(): return rows("SELECT a.*,j.title,j.company FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.created_at DESC")
@app.get("/api/documents")
def documents(): return rows("SELECT * FROM documents ORDER BY created_at DESC")
@app.post("/api/runs")
def start_run(background:BackgroundTasks,sample:bool=False): background.add_task(run,sample);return {"started":True}
@app.get("/api/runs/latest")
def latest(): return row("SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {"state":"IDLE","progress":0,"message":"Ready","stats":"{}"}
@app.post("/api/runs/{run_id}/discard")
def discard(run_id:int):
 with connect() as db:db.execute("UPDATE runs SET state='DISCARDED',finished_at=? WHERE id=? AND state='INTERRUPTED'",(now(),run_id))
 return {"discarded":True}
@app.get("/api/sources")
def sources():
 known=rows("SELECT * FROM source_status ORDER BY source_name"); return known or [{**RSSSource().capability(),"last_success":None,"last_error":None}]
@app.get("/api/overview")
def overview():
 result=row("SELECT COUNT(*) jobs_found,SUM(score>=80) high_match,SUM(status='PREPARED') prepared,SUM(status IN ('APPLIED','APPLIED_CONFIRMED')) submitted,SUM(status='NEEDS_USER_INPUT') needs_input,SUM(status='INTERVIEW') interviews,SUM(status='REJECTED') rejected,SUM(status IN ('APPLIED','APPLIED_CONFIRMED')) awaiting_response FROM jobs") or {}; result.update(row("SELECT COUNT(*) runs_today,MAX(started_at) last_run FROM runs WHERE date(started_at)=date('now')") or {});return result
@app.get("/api/google/status")
def google_status(): return TokenStore().summary()
@app.post("/api/google/connect")
def google_connect(value:GoogleStart):
 try:return start_authorization(value.features)
 except ValueError as exc:raise HTTPException(400,str(exc)) from exc
@app.get("/api/google/callback")
def google_callback(code:str,state:str):
 try:complete_authorization(code,state)
 except Exception as exc:raise HTTPException(400,"Google authorization failed. Reconnect and try again.") from exc
 return RedirectResponse("/?google=connected")
@app.delete("/api/google")
def google_disconnect(): disconnect();return {"connected":False}
@app.post("/api/gmail/sync")
def gmail_sync():
 try:return {"messages_saved":sync_messages()}
 except PermissionError as exc:raise HTTPException(401,str(exc)) from exc
@app.get("/api/gmail/messages")
def gmail_messages(): return rows("SELECT * FROM emails ORDER BY received_at DESC LIMIT 100")
@app.post("/api/gmail/drafts")
def gmail_draft(value:GmailDraft): return create_draft(value.to,value.subject,value.body,value.thread_id)
@app.post("/api/gmail/send")
def gmail_send(value:GmailDraft,confirm:bool=False): return send_message(value.to,value.subject,value.body,confirm)
@app.get("/api/drive/files")
def drive_files(): return list_app_files()
@app.post("/api/documents/{document_id}/drive")
def drive_upload(document_id:int):
 doc=row("SELECT * FROM documents WHERE id=?",(document_id,))
 if not doc:raise HTTPException(404,"Document not found")
 result=upload_file(ROOT/doc["local_path"],existing_id=doc.get("drive_file_id"));
 with connect() as db:db.execute("UPDATE documents SET drive_file_id=? WHERE id=?",(result["id"],document_id))
 return result
@app.post("/api/calendar/events")
def calendar_event(value:CalendarInput): return create_event(value.event,value.confirmed)
@app.get("/api/calendar/events")
def calendar_events(): return rows("SELECT * FROM calendar_events ORDER BY starts_at")
@app.get("/api/logs")
def logs():
 path=ROOT/"logs/job_agent.log"; lines=path.read_text(encoding="utf-8",errors="replace").splitlines()[-200:] if path.exists() else []; return {"lines":lines}
@app.get("/api/export.csv")
def export_csv():
 data=rows("SELECT company,title vacancy,discovered_at application_date,cv_path cv_version,source,status,salary FROM jobs ORDER BY discovered_at DESC");out=io.StringIO();w=csv.DictWriter(out,fieldnames=data[0].keys() if data else ["company","vacancy","status"]);w.writeheader();w.writerows(data);return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=applications.csv"})
app.mount("/assets",StaticFiles(directory=ROOT/"frontend"),name="assets")
@app.get("/")
def index():return FileResponse(ROOT/"frontend/index.html")
