from __future__ import annotations
from agents.models import Job
from .base import JobSource
from .http import get
class LeverSource(JobSource):
 name="lever-public-api"
 def search(self,profile,preferences):
  jobs=[]
  for site in preferences.get("lever_sites",[]):
   url=f"https://api.lever.co/v0/postings/{site}?mode=json"
   for item in get(url).json():
    categories=item.get("categories",{});location=categories.get("location","");description=" ".join([item.get("descriptionPlain","")]+[section.get("content","") for section in item.get("lists",[])])
    jobs.append(Job(item.get("text") or "Untitled vacancy",site.replace("-"," ").title(),location,self.name,item.get("hostedUrl") or "",description,application_url=item.get("applyUrl") or item.get("hostedUrl") or "",vacancy_id=item.get("id"),work_mode=categories.get("workplaceType","") or item.get("workplaceType",{}),metadata=item))
  return jobs
