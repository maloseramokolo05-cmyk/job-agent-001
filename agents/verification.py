from __future__ import annotations
from datetime import datetime,timezone
from urllib.parse import urlparse
def verify_job(job):
 risks=[]
 if not job.title or job.title.lower().startswith("untitled"):risks.append("missing_title")
 if not job.company or job.company.lower().startswith("unknown"):risks.append("missing_employer")
 if len(job.description)<80:risks.append("thin_description")
 url=job.application_url or job.vacancy_url;parsed=urlparse(url)
 if not url:risks.append("missing_url")
 elif parsed.scheme not in {"http","https"} or not parsed.netloc:risks.append("unsafe_url")
 expired=False
 if job.closing_date:
  try:expired=datetime.fromisoformat(job.closing_date.replace("Z","+00:00"))<datetime.now(timezone.utc)
  except ValueError:risks.append("unparsed_closing_date")
 return {"active":not expired and not {"missing_url","unsafe_url"}&set(risks),"status":"EXPIRED" if expired else "VERIFIED" if not risks else "PARTIAL","risks":risks}
