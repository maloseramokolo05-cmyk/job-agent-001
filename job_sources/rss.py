import xml.etree.ElementTree as ET
from agents.models import Job
from agents.parsers import clean
from .base import JobSource
from .http import get as http_get
class RSSSource(JobSource):
 name="configured-rss-atom"
 def search(self,profile,preferences):
  jobs=[]
  for feed in preferences.get("search_feeds",[]):
   root=ET.fromstring(http_get(feed).content);items=root.findall(".//item")
   for item in items:
    value=lambda name:clean(item.findtext(name,""));url=value("link");jobs.append(Job(value("title") or "Untitled vacancy",value("author") or value("source") or "Unknown employer","",self.name,url,value("description"),application_url=url,vacancy_id=value("guid") or url,date_posted=value("pubDate")))
   namespace="{http://www.w3.org/2005/Atom}"
   for entry in root.findall(f".//{namespace}entry"):
    value=lambda name:clean(entry.findtext(f"{namespace}{name}",""));link=entry.find(f"{namespace}link");url=link.get("href","") if link is not None else "";author=value("author") or "Unknown employer";jobs.append(Job(value("title") or "Untitled vacancy",author,"",self.name,url,value("summary") or value("content"),application_url=url,vacancy_id=value("id") or url,date_posted=value("updated") or value("published")))
  return jobs
