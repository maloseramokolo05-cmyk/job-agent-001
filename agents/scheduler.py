from apscheduler.schedulers.blocking import BlockingScheduler
from backend.config import load_preferences
from agents.pipeline import run
def main():
 scheduler=BlockingScheduler(timezone="Africa/Johannesburg")
 for index,value in enumerate(load_preferences().get("schedule_times",[])):
  hour,minute=map(int,value.split(":")); scheduler.add_job(run,"cron",hour=hour,minute=minute,id=f"search-{index}",max_instances=1,coalesce=True)
 print("Tumelo Job Agent scheduler running. Press Ctrl+C to stop."); scheduler.start()
if __name__=="__main__": main()
