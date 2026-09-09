import argparse,json
from backend.database import init_db
from agents.pipeline import run
p=argparse.ArgumentParser(); p.add_argument("command",choices=["init-db","run"]); p.add_argument("--sample",action="store_true"); a=p.parse_args()
if a.command=="init-db": init_db(); print("Database initialized")
else: init_db(); print(json.dumps(run(a.sample),indent=2))
