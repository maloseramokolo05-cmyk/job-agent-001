from __future__ import annotations
import json
from bs4 import BeautifulSoup
from agents.models import Job
from .base import JobSource
from .http import get
class JsonLdSource(JobSource):
 name="jsonld-careers"
 def search(self,profile,preferences):
  jobs=[]
  for url in preferences.get("career_pages",[]):
   soup=BeautifulSoup(get(url).text,"html.parser")
   for script in soup.select('script[type="application/ld+json"]'):
    try:data=json.loads(script.string or "{}")
    except json.JSONDecodeError:continue
    items=data.get("@graph",[]) if isinstance(data,dict) and "@graph" in data else data if isinstance(data,list) else [data]
    for item in items:
     if not isinstance(item,dict) or item.get("@type")!="JobPosting":continue
     org=item.get("hiringOrganization") or {};loc=item.get("jobLocation") or {};loc=loc[0] if isinstance(loc,list) and loc else loc;address=loc.get("address",{}) if isinstance(loc,dict) else {};location=", ".join(str(address.get(x,"")) for x in ("addressLocality","addressRegion","addressCountry") if address.get(x));identifier=item.get("identifier",{});ident=identifier.get("value") if isinstance(identifier,dict) else identifier
     jobs.append(Job(item.get("title") or "Untitled vacancy",org.get("name") or "Unknown employer",location,self.name,item.get("url") or url,BeautifulSoup(item.get("description","") or "","html.parser").get_text(" ",strip=True),application_url=item.get("url") or url,vacancy_id=str(ident or item.get("url") or url),date_posted=item.get("datePosted"),closing_date=item.get("validThrough"),work_mode="Remote" if item.get("jobLocationType")=="TELECOMMUTE" else "",metadata=item))
  return jobs
