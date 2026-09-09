import xml.etree.ElementTree as ET
import requests
from agents.models import Job
from agents.parsers import clean
from .base import JobSource
class RSSSource(JobSource):
 name="configured-rss"
 def search(self,profile,preferences):
  jobs=[]
  for feed in preferences.get("search_feeds",[]):
   response=requests.get(feed,timeout=20,headers={"User-Agent":"TumeloJobAgent/1.0"}); response.raise_for_status()
   for item in ET.fromstring(response.content).findall(".//item"):
    get=lambda n: clean(item.findtext(n,"")); url=get("link")
    jobs.append(Job(get("title") or "Untitled vacancy",get("author") or "Unknown employer","",self.name,url,get("description"),application_url=url,vacancy_id=get("guid") or url,date_posted=get("pubDate")))
  return jobs
