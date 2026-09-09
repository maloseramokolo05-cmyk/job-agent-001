#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
trap 'echo "INSTALL FAILED at line $LINENO. Review the message above." >&2' ERR
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
if [[ "${PREFIX:-}" != *com.termux* ]] && [[ ! -d /data/data/com.termux ]]; then echo "This installer is intended for Termux. For Linux use python -m venv .venv." >&2; exit 1; fi
echo "[1/6] Updating Termux packages"; pkg update -y
echo "[2/6] Installing runtime packages"; pkg install -y python git libxml2 libxslt libjpeg-turbo
python -m venv .venv; source .venv/bin/activate
echo "[3/6] Updating Python tooling"; python -m pip install --upgrade pip setuptools wheel
echo "[4/6] Installing Android-compatible core and Google dependencies"; pip install -r requirements.txt -r requirements-google.txt
mkdir -p cv applications/screenshots generated_cvs cover_letters data/tokens data/secrets logs runtime
[[ -f .env ]] || cp .env.example .env
chmod 700 data/tokens data/secrets runtime || true
echo "[5/6] Initializing and migrating SQLite"; python -m agents.cli init-db
echo "[6/6] Verifying"; python -m agents.cli doctor || { echo "Doctor found a blocking problem."; exit 1; }
echo "Installation complete. Run: ./START_ANDROID.sh"
