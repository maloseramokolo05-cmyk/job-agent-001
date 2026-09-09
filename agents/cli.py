import argparse,json,sys
from backend.database import init_db
p=argparse.ArgumentParser();p.add_argument("command",choices=["init-db","run","doctor","status"]);p.add_argument("--sample",action="store_true");a=p.parse_args()
if a.command=="init-db":init_db();print("Database initialized and migrated")
elif a.command=="doctor":
 from agents.doctor import print_doctor
 sys.exit(print_doctor())
elif a.command=="status":
 from backend.database import row
 from integrations.google.token_store import TokenStore
 print(json.dumps({"latest_run":row("SELECT * FROM runs ORDER BY id DESC LIMIT 1"),"google":TokenStore().summary()},indent=2))
else:
 from agents.pipeline import run
 init_db();print(json.dumps(run(a.sample),indent=2))
