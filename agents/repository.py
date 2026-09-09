import hashlib,json,re,sqlite3
from backend.database import connect,now
def norm(value):return re.sub(r"[^a-z0-9]+"," ",value.lower()).strip()
def ingest(job,verification=None):
 data=job.dict();digest=hashlib.sha256((data["description"]+data["requirements"]).encode()).hexdigest();metadata=json.dumps(data.get("metadata",{}),default=str);status=(verification or {}).get("status","UNVERIFIED");values=(data.get("vacancy_id"),data["title"],norm(data["title"]),data["company"],norm(data["company"]),data["location"],data["salary"],data["date_posted"],data["closing_date"],data["description"],data["requirements"],data["source"],data["vacancy_url"],data["application_url"],data["work_mode"],now(),digest,"DISCOVERED",metadata,status)
 with connect() as db:
  try:cur=db.execute("INSERT INTO jobs(vacancy_id,title,normalized_title,company,normalized_company,location,salary,date_posted,closing_date,description,requirements,source,vacancy_url,application_url,work_mode,discovered_at,description_hash,status,structured_metadata,verification_status) VALUES("+",".join("?"*20)+")",values);job_id=cur.lastrowid;duplicate=False
  except sqlite3.IntegrityError:
   found=db.execute("SELECT id FROM jobs WHERE vacancy_url=? OR (normalized_title=? AND normalized_company=? AND location=?) LIMIT 1",(data["vacancy_url"],norm(data["title"]),norm(data["company"]),data["location"])).fetchone();job_id=found[0] if found else None;duplicate=True
  if job_id and data["vacancy_url"]:db.execute("INSERT OR IGNORE INTO job_sources_found(job_id,source,source_url,discovered_at) VALUES(?,?,?,?)",(job_id,data["source"],data["vacancy_url"],now()))
  return job_id,duplicate
def update_analysis(job_id,result,status):
 with connect() as db:db.execute("UPDATE jobs SET score=?,classification=?,score_breakdown=?,missing_requirements=?,reasoning=?,status=?,priority=? WHERE id=?",(result["score"],result["classification"],json.dumps(result),json.dumps(result["missing_requirements"]),result["reasoning"],status,result["score"],job_id))
