from defusedxml import ElementTree as ET
from agents.models import Job
from agents.parsers import clean
from .base import JobSource
from .http import safe_get
class RSSSource(JobSource):
 name="configured-rss"
 def search(self,profile,preferences):
  jobs=[]
  for feed in preferences.get("search_feeds",[]):
   response=safe_get(feed,timeout=20)
   for item in ET.fromstring(response.content).findall(".//item"):
    get=lambda n: clean(item.findtext(n,"")); url=get("link")
    jobs.append(Job(get("title") or "Untitled vacancy",get("author") or "Unknown employer","",self.name,url,get("description"),application_url=url,vacancy_id=get("guid") or url,date_posted=get("pubDate")))
  return jobs
