from __future__ import annotations
import csv,io,json,logging,os,platform
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import FastAPI,HTTPException,BackgroundTasks,UploadFile,File,Request
from fastapi.responses import FileResponse,RedirectResponse,StreamingResponse,PlainTextResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from backend.version import __version__
from backend.config import ROOT,DATA_ROOT,private_path,load_profile,load_preferences,save_json
from backend.database import init_db,schema_version,rows,row,connect,now,event
from agents.pipeline import run,cv_text
from agents.cv_parser import parse_cv
from agents.documents import generate_cv,generate_cover_letter
from job_sources.rss import RSSSource
from integrations.google.oauth import start_authorization,complete_authorization,disconnect,client_config
from integrations.google.token_store import TokenStore
from integrations.google.gmail import sync_messages,create_draft,send_message
from integrations.google.drive import list_app_files,upload_file
from integrations.google.calendar import create_event
from backend.security import COOKIE,bootstrap_owner,login,logout,session,validate_csrf
from applications.workflow import prepare,persist
app=FastAPI(title="Tumelo Job Agent",version=__version__)
class Status(BaseModel): status:str
class Setup(BaseModel): profile:dict; preferences:dict
class GmailDraft(BaseModel): to:str; subject:str; body:str; thread_id:str|None=None; document_ids:list[int]=Field(default_factory=list)
class CalendarInput(BaseModel): event:dict; confirmed:bool=False
class GoogleStart(BaseModel): features:list[str]=Field(default_factory=lambda:["gmail","drive","calendar"])
class Login(BaseModel): username:str; password:str
class ApplicationUpdate(BaseModel): notes:str|None=None; follow_up_date:str|None=None; contact_person:str|None=None; recruiter_email:str|None=None
ALLOWED={"DISCOVERED","SHORTLISTED","PREPARING","PREPARED","NEEDS_USER_INPUT","NEEDS_USER_ACTION","READY_TO_APPLY","MANUAL_APPLICATION","APPLIED","APPLIED_CONFIRMED","INTERVIEW","ASSESSMENT","REJECTED","OFFER","WITHDRAWN","EXPIRED","ERROR"}
TRANSITIONS={"DISCOVERED":{"SHORTLISTED","EXPIRED","ERROR"},"SHORTLISTED":{"PREPARING","PREPARED","NEEDS_USER_INPUT","NEEDS_USER_ACTION","WITHDRAWN"},"PREPARING":{"PREPARED","NEEDS_USER_INPUT","ERROR"},"PREPARED":{"READY_TO_APPLY","NEEDS_USER_ACTION","APPLIED","WITHDRAWN"},"NEEDS_USER_INPUT":{"PREPARED","WITHDRAWN"},"NEEDS_USER_ACTION":{"READY_TO_APPLY","APPLIED","WITHDRAWN"},"READY_TO_APPLY":{"APPLIED","WITHDRAWN","EXPIRED"},"APPLIED":{"APPLIED_CONFIRMED","ASSESSMENT","INTERVIEW","REJECTED","OFFER","WITHDRAWN"},"APPLIED_CONFIRMED":{"ASSESSMENT","INTERVIEW","REJECTED","OFFER","WITHDRAWN"},"ASSESSMENT":{"INTERVIEW","REJECTED","OFFER","WITHDRAWN"},"INTERVIEW":{"ASSESSMENT","REJECTED","OFFER","WITHDRAWN"}}
@app.middleware("http")
async def security_middleware(request:Request,call_next):
 public=request.url.path in {"/","/manifest.webmanifest","/service-worker.js","/offline.html","/api/health","/api/auth/login","/api/auth/status"} or request.url.path.startswith("/assets/")
 sess=session(request)
 if request.url.path.startswith("/api/") and not public:
  if not sess:return PlainTextResponse("Authentication required",status_code=401)
  try:validate_csrf(request,sess)
  except HTTPException as exc:return PlainTextResponse(exc.detail,status_code=exc.status_code)
 response=await call_next(request);response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
 if request.url.path.startswith("/api/"):response.headers["Cache-Control"]="no-store"
 return response
def setup_logging():
 log=private_path("logs","job_agent.log"); log.parent.mkdir(exist_ok=True); handler=RotatingFileHandler(log,maxBytes=2_000_000,backupCount=4,encoding="utf-8"); handler.setFormatter(logging.Formatter('{"time":"%(asctime)s","severity":"%(levelname)s","component":"%(name)s","message":"%(message)s"}')); logging.getLogger().setLevel(logging.INFO); logging.getLogger().addHandler(handler)
@app.on_event("startup")
def startup(): init_db(); bootstrap_owner(); setup_logging(); logging.getLogger("startup").info("event=APPLICATION_STARTED version=%s",__version__)
@app.get("/api/health")
def health():
 return {"status":"ok","version":__version__}
@app.get("/api/auth/status")
def auth_status(request:Request):
 sess=session(request);return {"authenticated":bool(sess),"csrf_token":sess[3] if sess else None}
@app.post("/api/auth/login")
def auth_login(value:Login,request:Request):
 token,csrf,expires=login(value.username,value.password,request.client.host if request.client else "unknown");response=JSONResponse({"authenticated":True,"csrf_token":csrf});response.set_cookie(COOKIE,token,httponly=True,secure=os.getenv("COOKIE_SECURE","true").lower()=="true",samesite="strict",expires=expires,path="/");return response
@app.post("/api/auth/logout")
def auth_logout(request:Request):
 logout(request.cookies.get(COOKIE));response=JSONResponse({"authenticated":False});response.delete_cookie(COOKIE,path="/");return response
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
 path=private_path("cv","master_cv"+suffix);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);return {"saved":path.name,"parsed_text":parse_cv(path)[:20000]}
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
  jobrow=db.execute("SELECT source,status FROM jobs WHERE id=?",(job_id,)).fetchone()
  if not jobrow:raise HTTPException(404,"Job not found")
  if value.status not in TRANSITIONS.get(jobrow[1],set()) and value.status!=jobrow[1]:raise HTTPException(409,f"Transition from {jobrow[1]} to {value.status} is not allowed")
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
@app.post("/api/jobs/{job_id}/prepare")
def prepare_application(job_id:int):
 job_value=row("SELECT * FROM jobs WHERE id=?",(job_id,))
 if not job_value:raise HTTPException(404,"Job not found")
 package=prepare(job_value,load_profile());application_id,status=persist(job_id,package);return {"application_id":application_id,"status":status,"package":package}
@app.patch("/api/applications/{application_id}")
def update_application(application_id:int,value:ApplicationUpdate):
 fields=value.model_dump(exclude_none=True)
 if not fields:return {"updated":False}
 with connect() as db:
  if not db.execute("SELECT 1 FROM applications WHERE id=?",(application_id,)).fetchone():raise HTTPException(404,"Application not found")
  db.execute("UPDATE applications SET "+",".join(f"{key}=?" for key in fields)+" WHERE id=?",(*fields.values(),application_id))
 return {"updated":True}
@app.get("/api/documents")
def documents(): return rows("SELECT * FROM documents ORDER BY created_at DESC")
@app.get("/api/documents/{document_id}/download")
def download_document(document_id:int):
 doc=row("SELECT * FROM documents WHERE id=?",(document_id,))
 if not doc:raise HTTPException(404,"Document not found")
 base=DATA_ROOT.resolve();path=(base/doc["local_path"]).resolve()
 if base not in path.parents or not path.is_file():raise HTTPException(404,"Document file not found")
 return FileResponse(path,filename=path.name,media_type="application/octet-stream")
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
def google_status():
 result=TokenStore().summary();result["configured"]=bool(client_config()[0]);result["status"]="CONNECTED" if result["connected"] else "DISCONNECTED" if result["configured"] else "NOT_CONFIGURED";return result
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
def gmail_draft(value:GmailDraft):
 attachments=[]
 for document_id in value.document_ids:
  document=row("SELECT local_path FROM documents WHERE id=?",(document_id,))
  if not document:raise HTTPException(404,f"Document {document_id} not found")
  path=(DATA_ROOT/document["local_path"]).resolve()
  if DATA_ROOT.resolve() not in path.parents or not path.is_file():raise HTTPException(404,"Attachment file not found")
  attachments.append(path)
 result=create_draft(value.to,value.subject,value.body,value.thread_id,attachments=attachments);event("GMAIL_DRAFT_CREATED",json.dumps({"message_id":result.get("message",{}).get("id"),"document_ids":value.document_ids}));return result
@app.post("/api/gmail/send")
def gmail_send(value:GmailDraft,confirm:bool=False):
 paths=[]
 for document_id in value.document_ids:
  document=row("SELECT local_path FROM documents WHERE id=?",(document_id,))
  if not document:raise HTTPException(404,f"Document {document_id} not found")
  path=(DATA_ROOT/document["local_path"]).resolve()
  if DATA_ROOT.resolve() not in path.parents or not path.is_file():raise HTTPException(404,"Attachment file not found")
  paths.append(path)
 result=send_message(value.to,value.subject,value.body,confirm,attachments=paths);event("GMAIL_MESSAGE_SENT",json.dumps({"message_id":result.get("id"),"document_ids":value.document_ids}));return result
@app.get("/api/drive/files")
def drive_files(): return list_app_files()
@app.post("/api/documents/{document_id}/drive")
def drive_upload(document_id:int):
 doc=row("SELECT * FROM documents WHERE id=?",(document_id,))
 if not doc:raise HTTPException(404,"Document not found")
 result=upload_file(DATA_ROOT/doc["local_path"],existing_id=doc.get("drive_file_id"));
 with connect() as db:db.execute("UPDATE documents SET drive_file_id=? WHERE id=?",(result["id"],document_id))
 return result
@app.post("/api/calendar/events")
def calendar_event(value:CalendarInput): return create_event(value.event,value.confirmed)
@app.get("/api/calendar/events")
def calendar_events(): return rows("SELECT * FROM calendar_events ORDER BY starts_at")
@app.get("/api/logs")
def logs():
 path=private_path("logs","job_agent.log"); lines=path.read_text(encoding="utf-8",errors="replace").splitlines()[-200:] if path.exists() else []; return {"lines":lines}
@app.get("/api/export.csv")
def export_csv():
 data=rows("SELECT company,title vacancy,discovered_at application_date,cv_path cv_version,source,status,salary FROM jobs ORDER BY discovered_at DESC");out=io.StringIO();w=csv.DictWriter(out,fieldnames=data[0].keys() if data else ["company","vacancy","status"]);w.writeheader();w.writerows(data);return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=applications.csv"})
app.mount("/assets",StaticFiles(directory=ROOT/"frontend"),name="assets")
@app.get("/")
def index():return FileResponse(ROOT/"frontend/index.html")
@app.get("/manifest.webmanifest")
def manifest():return FileResponse(ROOT/"frontend/manifest.webmanifest",media_type="application/manifest+json")
@app.get("/service-worker.js")
def service_worker():return FileResponse(ROOT/"frontend/service-worker.js",media_type="application/javascript",headers={"Cache-Control":"no-cache"})
@app.get("/offline.html")
def offline():return FileResponse(ROOT/"frontend/offline.html")
