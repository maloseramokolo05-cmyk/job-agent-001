from __future__ import annotations
import requests
from backend.database import connect,now
from .oauth import access_token
BASE="https://www.googleapis.com/calendar/v3/calendars/primary/events"
def create_event(event,confirmed=False,http=requests):
 if not confirmed: raise PermissionError("Calendar event creation requires user confirmation")
 required={"summary","start","end"}
 if not required.issubset(event): raise ValueError("Calendar event requires summary, start, and end")
 job_id=event.get("job_id"); thread=event.get("source_thread_id"); starts=event["start"].get("dateTime") or event["start"].get("date")
 with connect() as db:
  existing=db.execute("SELECT google_event_id FROM calendar_events WHERE job_id IS ? AND source_thread_id IS ? AND starts_at=?",(job_id,thread,starts)).fetchone()
  if existing:return {"id":existing[0],"duplicate":True}
 token=access_token(http); public={k:v for k,v in event.items() if k not in {"job_id","source_thread_id","event_type"}}; r=http.post(BASE,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},json=public,timeout=30); r.raise_for_status(); data=r.json()
 with connect() as db: db.execute("INSERT INTO calendar_events(google_event_id,job_id,source_thread_id,event_type,starts_at,created_at) VALUES(?,?,?,?,?,?)",(data["id"],job_id,thread,event.get("event_type","INTERVIEW"),starts,now()))
 return {**data,"duplicate":False}
