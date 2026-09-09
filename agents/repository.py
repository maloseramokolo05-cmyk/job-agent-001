import hashlib,json,re,sqlite3
from backend.database import connect,now,event
def norm(v): return re.sub(r"[^a-z0-9]+"," ",v.lower()).strip()
def ingest(job):
 d=job.dict(); h=hashlib.sha256((d["description"]+d["requirements"]).encode()).hexdigest(); values=(d.get("vacancy_id"),d["title"],norm(d["title"]),d["company"],norm(d["company"]),d["location"],d["salary"],d["date_posted"],d["closing_date"],d["description"],d["requirements"],d["source"],d["vacancy_url"],d["application_url"],d["work_mode"],now(),h)
 try:
  with connect() as db:
   cur=db.execute("INSERT INTO jobs(vacancy_id,title,normalized_title,company,normalized_company,location,salary,date_posted,closing_date,description,requirements,source,vacancy_url,application_url,work_mode,discovered_at,description_hash) VALUES("+",".join("?"*17)+")",values); return cur.lastrowid,False
 except sqlite3.IntegrityError: return None,True
def update_analysis(job_id,result,status):
 with connect() as db: db.execute("UPDATE jobs SET score=?,classification=?,score_breakdown=?,missing_requirements=?,reasoning=?,status=? WHERE id=?",(result["score"],result["classification"],json.dumps(result["breakdown"]),json.dumps(result["missing_requirements"]),result["reasoning"],status,job_id))
