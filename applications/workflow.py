from __future__ import annotations
import json
from backend.database import connect,now,event
REQUIRED_PROFILE=("name","email","phone","location")
def prepare(job,profile,questions=None):
 missing=[field for field in REQUIRED_PROFILE if not profile.get(field)];answers={field:profile.get(field) for field in REQUIRED_PROFILE if profile.get(field)};unknown=[]
 for question in questions or []:
  key=question.get("profile_field")
  if key and profile.get(key):answers[question["question"]]=profile[key]
  elif question.get("required",True):unknown.append(question["question"])
 method="EMAIL" if job.get("recruiter_email") else "EXTERNAL_WEB" if job.get("application_url") else "MANUAL"
 return {"method":method,"answers":answers,"missing_profile_fields":missing,"unanswered_questions":unknown,"ready":not missing and not unknown and bool(job.get("cv_path")),"requires_confirmation":True}
def persist(job_id,package):
 status="READY_TO_APPLY" if package["ready"] else "NEEDS_USER_INPUT"
 with connect() as db:
  existing=db.execute("SELECT id FROM applications WHERE job_id=?",(job_id,)).fetchone()
  if existing:application_id=existing[0];db.execute("UPDATE applications SET status=?,answers=? WHERE id=?",(status,json.dumps(package),application_id))
  else:application_id=db.execute("INSERT INTO applications(job_id,status,answers,created_at) VALUES(?,?,?,?)",(job_id,status,json.dumps(package),now())).lastrowid
  db.execute("UPDATE jobs SET status=? WHERE id=?",(status,job_id))
 event("APPLICATION_PACKAGE_PREPARED",json.dumps({"application_id":application_id,"method":package["method"],"status":status}),job_id);return application_id,status
