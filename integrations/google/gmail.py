from __future__ import annotations
import base64,os,re
from email.message import EmailMessage
import requests
from backend.database import connect,now
from .oauth import access_token
BASE="https://gmail.googleapis.com/gmail/v1/users/me"
JOB_QUERY='newer_than:90d (application OR interview OR assessment OR recruiter OR vacancy OR offer OR rejection OR "thank you for applying")'
RULES=[("JOB_OFFER",.93,["job offer","offer of employment"]),("INTERVIEW_INVITE",.92,["invite you for an interview","interview invitation","schedule an interview"]),("APPLICATION_CONFIRMATION",.9,["received your application","application has been received","thank you for applying"]),("ASSESSMENT_REQUEST",.88,["complete the assessment","assessment invitation","assessment deadline"]),("APPLICATION_REJECTION",.82,["unfortunately","not progressing","other candidates"]),("SALARY_REQUEST",.8,["salary expectation","current salary"]),("DOCUMENT_REQUEST",.8,["send your cv","supporting documents","proof of"]),("FOLLOW_UP_REQUIRED",.72,["following up","awaiting your response"]),("RECRUITER_MESSAGE",.65,["recruiter","opportunity","vacancy"])]
def classify_email(subject,body):
 text=f"{subject} {body}".lower()
 for category,confidence,phrases in RULES:
  hits=sum(p in text for p in phrases)
  if hits:return {"classification":category,"confidence":min(.99,confidence+.03*(hits-1)),"action_required":category in {"INTERVIEW_INVITE","ASSESSMENT_REQUEST","SALARY_REQUEST","DOCUMENT_REQUEST","JOB_OFFER","FOLLOW_UP_REQUIRED"}}
 return {"classification":"OTHER","confidence":.2,"action_required":False}
def _headers(token): return {"Authorization":f"Bearer {token}"}
def search_messages(max_results=25,http=requests):
 token=access_token(http); response=http.get(f"{BASE}/messages",headers=_headers(token),params={"q":JOB_QUERY,"maxResults":min(max_results,100)},timeout=30); response.raise_for_status(); return response.json().get("messages",[])
def sync_messages(max_results=25,http=requests):
 token=access_token(http); saved=0
 for ref in search_messages(max_results,http):
  response=http.get(f"{BASE}/messages/{ref['id']}",headers=_headers(token),params={"format":"metadata","metadataHeaders":["From","Subject","Date"]},timeout=30); response.raise_for_status(); data=response.json(); headers={x["name"].lower():x["value"] for x in data.get("payload",{}).get("headers",[])}; result=classify_email(headers.get("subject",""),data.get("snippet",""))
  with connect() as db:
   text=f"{headers.get('subject','')} {data.get('snippet','')}".lower(); related=None
   for job in db.execute("SELECT id,title,company FROM jobs WHERE status IN ('APPLIED','APPLIED_CONFIRMED','ASSESSMENT','INTERVIEW') ORDER BY discovered_at DESC LIMIT 200"):
    company_words=[word for word in re.findall(r"[a-z0-9]+",job[2].lower()) if len(word)>3]; title_words=[word for word in re.findall(r"[a-z0-9]+",job[1].lower()) if len(word)>4]
    if company_words and any(word in text for word in company_words) and (not title_words or any(word in text for word in title_words)):related=job[0];break
   response_status="NEEDS_REVIEW" if result["confidence"]<.85 or result["classification"]=="APPLICATION_REJECTION" else "UNREAD"
   db.execute("INSERT OR REPLACE INTO emails(google_message_id,thread_id,sender,subject,received_at,classification,confidence,related_job_id,action_required,response_status,snippet) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(data["id"],data.get("threadId"),headers.get("from",""),headers.get("subject",""),headers.get("date"),result["classification"],result["confidence"],related,int(result["action_required"]),response_status,data.get("snippet","")))
   status_map={"APPLICATION_CONFIRMATION":"APPLIED_CONFIRMED","INTERVIEW_INVITE":"INTERVIEW","ASSESSMENT_REQUEST":"ASSESSMENT","JOB_OFFER":"OFFER"}
   if related and result["confidence"]>=.88 and result["classification"] in status_map:
    status=status_map[result["classification"]];db.execute("UPDATE jobs SET status=? WHERE id=?",(status,related));db.execute("INSERT INTO events(job_id,event_type,detail,created_at) VALUES(?,?,?,?)",(related,"GMAIL_STATUS_UPDATE",status,now()))
  saved+=1
 return saved
def build_message(to,subject,body,reply_to=None):
 if not to or not subject or not body: raise ValueError("Recipient, subject, and factual body are required")
 msg=EmailMessage(); msg["To"]=to; msg["Subject"]=subject
 if reply_to: msg["In-Reply-To"]=reply_to; msg["References"]=reply_to
 msg.set_content(body); return base64.urlsafe_b64encode(msg.as_bytes()).decode()
def create_draft(to,subject,body,thread_id=None,http=requests):
 token=access_token(http); payload={"message":{"raw":build_message(to,subject,body)}}
 if thread_id:payload["message"]["threadId"]=thread_id
 response=http.post(f"{BASE}/drafts",headers={**_headers(token),"Content-Type":"application/json"},json=payload,timeout=30); response.raise_for_status(); return response.json()
def send_message(to,subject,body,explicit=False,http=requests):
 if not explicit and os.getenv("GOOGLE_GMAIL_AUTO_SEND","false").lower()!="true": raise PermissionError("Gmail auto-send is disabled; explicit confirmation is required")
 token=access_token(http); response=http.post(f"{BASE}/messages/send",headers={**_headers(token),"Content-Type":"application/json"},json={"raw":build_message(to,subject,body)},timeout=30); response.raise_for_status(); return response.json()
