#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"; RUNTIME="$ROOT/runtime"; mkdir -p "$RUNTIME" logs
[[ -x .venv/bin/python ]] || { echo "Missing .venv. Run ./INSTALL_ANDROID.sh first." >&2; exit 1; }
source .venv/bin/activate
python -m agents.cli doctor || { echo "Configuration validation failed." >&2; exit 1; }
check_pid(){ [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }
if check_pid "$RUNTIME/backend.pid" || check_pid "$RUNTIME/scheduler.pid"; then echo "Tumelo Job Agent is already running. Use ./scripts/status_android.sh"; exit 1; fi
rm -f "$RUNTIME/backend.pid" "$RUNTIME/scheduler.pid"
HOST="${HOST:-127.0.0.1}"; PORT="${PORT:-8000}"
nohup python -m uvicorn backend.main:app --host "$HOST" --port "$PORT" >>logs/backend.log 2>&1 & echo $! >"$RUNTIME/backend.pid"
nohup python -m agents.scheduler >>logs/scheduler.log 2>&1 & echo $! >"$RUNTIME/scheduler.pid"
sleep 2
if ! check_pid "$RUNTIME/backend.pid"; then echo "Backend failed to start. See logs/backend.log" >&2; ./STOP_ANDROID.sh >/dev/null 2>&1 || true; exit 1; fi
if command -v termux-open-url >/dev/null 2>&1; then termux-open-url "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true; fi
echo "Tumelo Job Agent running"; echo "Dashboard: http://127.0.0.1:$PORT"; echo "Status: ./scripts/status_android.sh"
