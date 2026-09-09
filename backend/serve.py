from __future__ import annotations
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn
from agents.pipeline import run
from backend.config import load_preferences
from backend.database import connect
from backend.database import init_db
def scheduled_tick():
 timezone=os.getenv("TIMEZONE","Africa/Johannesburg");minute=datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
 if minute[-5:] not in load_preferences().get("schedule_times",[]):return
 with connect() as db:
  previous=db.execute("SELECT value FROM settings WHERE key='last_scheduled_search_minute'").fetchone()
  if previous and previous[0]==minute:return
  db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('last_scheduled_search_minute',?)",(minute,))
 try:run()
 except RuntimeError:pass
def build_scheduler():
 scheduler=BackgroundScheduler(timezone=os.getenv("TIMEZONE","Africa/Johannesburg"));scheduler.add_job(scheduled_tick,"interval",seconds=30,id="schedule-dispatcher",max_instances=1,coalesce=True);return scheduler
def main():
 init_db();scheduler=build_scheduler();scheduler.start()
 try:uvicorn.run("backend.main:app",host=os.getenv("HOST","127.0.0.1"),port=int(os.getenv("PORT","8000")),workers=1,proxy_headers=True,forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS","127.0.0.1"))
 finally:scheduler.shutdown(wait=False)
if __name__=="__main__":main()
