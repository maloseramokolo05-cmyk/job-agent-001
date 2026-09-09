#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
show(){ file="runtime/$1.pid"; if [[ -f "$file" ]] && kill -0 "$(cat "$file")" 2>/dev/null; then echo "$1: RUNNING (PID $(cat "$file"))"; else echo "$1: NOT RUNNING"; fi; }
show backend; show scheduler
if [[ -x .venv/bin/python ]]; then source .venv/bin/activate; echo "database: ${DATABASE_PATH:-data/job_agent.db}"; echo "port: ${PORT:-8000}"; python -m agents.cli status; python - <<'PY'
from job_sources.rss import RSSSource
print("active connectors:", RSSSource.name)
PY
else echo "environment: NOT INSTALLED"; fi
