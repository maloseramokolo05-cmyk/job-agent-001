from __future__ import annotations
import re
from bs4 import BeautifulSoup
from agents.models import Job
def clean(text): return re.sub(r"\s+", " ", text or "").strip()
def parse_job_html(html:str, url:str, source="web") -> Job:
 soup=BeautifulSoup(html,"html.parser")
 title=(soup.select_one("h1") or soup.select_one("title")); title=clean(title.get_text()) if title else "Untitled vacancy"
 company=soup.select_one('[class*="company" i]'); location=soup.select_one('[class*="location" i]')
 main=soup.select_one("main") or soup.select_one("article") or soup.body
 desc=clean(main.get_text(" ")) if main else ""
 return Job(title, clean(company.get_text()) if company else "Unknown employer", clean(location.get_text()) if location else "", source, url, desc)
