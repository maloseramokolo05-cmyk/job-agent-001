#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"; RUNTIME="$ROOT/runtime"; stopped=0
for name in backend scheduler; do file="$RUNTIME/$name.pid"; [[ -f "$file" ]] || continue; pid="$(cat "$file")"
 if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then kill "$pid"; for _ in 1 2 3 4 5; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done; kill -0 "$pid" 2>/dev/null && kill -9 "$pid"; echo "Stopped $name (PID $pid)"; stopped=1; fi
 rm -f "$file"
done
[[ $stopped -eq 1 ]] || echo "Tumelo Job Agent is not running."
command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock >/dev/null 2>&1 || true
