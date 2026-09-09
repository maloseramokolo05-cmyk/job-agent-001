#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
./STOP_ANDROID.sh || true
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-google.txt
python -m agents.cli init-db
python -m agents.cli doctor
echo "Updated. Start with ./START_ANDROID.sh"
