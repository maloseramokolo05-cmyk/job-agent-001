# Tumelo Job Agent 3.1.0

Private South African job discovery, factual CV tailoring, verified email applications and an
application CRM. The Vercel runtime uses Neon Postgres for durable records, private documents,
sessions and encrypted Google OAuth tokens. Read [production readiness](PRODUCTION_READINESS.md)
for the live-deployment acceptance gate; CI alone is not proof of a working deployment.

## Production security and storage

Set `ADMIN_PASSWORD_HASH` to an Argon2id hash, use a randomly generated `SESSION_SECRET` of at least
32 characters, and set `APP_ENV=production`. Production startup fails closed unless authentication,
Postgres and durable storage are configured. `STORAGE_PROVIDER=database` stores private bytes in
Neon; `s3` remains an optional alternative. See `.env.example` for the consumed variables.

The real-source adapters are Careers24, configured iYouth RSS feeds, selected Greenhouse boards and
selected Lever employer sites. Greenhouse and Lever results are filtered to roles explicitly located
in or remotely open to South Africa. Source URLs are treated as untrusted and guarded against private
network access, redirects, oversized responses and unbounded waits.

## ANDROID QUICK START

Install [Termux from F-Droid](https://f-droid.org/packages/com.termux/) rather than the obsolete Play Store build. In Termux:

```bash
pkg update -y
pkg install git -y
git clone https://github.com/maloseramokolo05-cmyk/job-agent-001.git
cd job-agent-001
chmod +x INSTALL_ANDROID.sh START_ANDROID.sh STOP_ANDROID.sh UPDATE_ANDROID.sh scripts/status_android.sh
./INSTALL_ANDROID.sh
./START_ANDROID.sh
```

Open **http://127.0.0.1:8000**. Complete the mobile setup, upload the master CV, configure permitted feeds, and press **RUN JOB SEARCH**. The app runs locally and does not require ChatGPT to remain open.

Use `./scripts/status_android.sh`, `./STOP_ANDROID.sh`, and `./UPDATE_ANDROID.sh` for lifecycle management. Run `termux-setup-storage` only if you want access to `~/storage/downloads` or `~/storage/shared`; dashboard uploads copy the selected PDF/DOCX into private app storage. See [the complete Android guide](docs/ANDROID_SETUP.md).

## Capability truth table

| Capability | Status | Notes |
|---|---|---|
| Core dashboard, SQLite, scoring, CRM, scheduler | ANDROID_SUPPORTED | Runs in Termux and an Android browser |
| Google OAuth, Gmail, Drive, Calendar REST APIs | ANDROID_SUPPORTED | Requires the user's Google Cloud OAuth client configuration |
| Application links and prepared answers | ANDROID_ASSISTED | User opens the link, reviews, submits, and marks applied |
| Playwright form automation | DESKTOP_ONLY | Optional `requirements-browser.txt`; not installed on Android |
| Generic CAPTCHA/login automation | NOT_IMPLEMENTED | Intentionally prohibited |

## Safety and architecture

The pipeline is **SEARCH → NORMALIZE → DEDUPLICATE → PARSE → SCORE → PRIORITIZE → DOCUMENTS → PREPARE → REVIEW → explicit send/submit → TRACK**. Connectors fail independently and publish capabilities/status. Restricted sources become `MANUAL_APPLICATION`; unknown questions become `NEEDS_USER_INPUT`.

The default mode is `PREPARE`. Gmail auto-send is false and Calendar creation requires confirmation. Google uses Authorization Code + PKCE, one-time CSRF state, narrow feature scopes, refresh tokens, and private token storage. The frontend never receives token values. External content is rendered through HTML escaping. Read the [security review](docs/SECURITY.md).

## Google setup

Follow [Google API setup](docs/GOOGLE_API_SETUP.md). In short: enable Gmail, Drive, and Calendar APIs; create a Web OAuth client; authorize `http://127.0.0.1:8000/api/google/callback`; save the downloaded JSON as `data/secrets/credentials.json`; restart; then select **Connect Google account**. No Gmail password is requested or stored.

Scopes are separated by feature:

- Gmail read/compose; send scope is requested only when the send feature is selected.
- Drive `drive.file`, which is limited to files created/opened by the app.
- Calendar `calendar.events`.

Gmail sync uses a job-focused query and deterministic confidence-based classification. It stores message metadata/snippets, not the entire mailbox. Drafts are allowed; sends require a dashboard confirmation or `GOOGLE_GMAIL_AUTO_SEND=true`. Drive lists only files bearing the app marker and detects local/remote master-CV conflicts. Calendar deterministically prevents duplicate events.

## Profile, CVs, and documents

The dashboard profile supports identity/contact information, work authorization, locations, target roles, minimum salary, schedule, skills, and application mode. `config/profile.json` remains editable for education, employment, languages, tools, links, notice period, and work preferences. The master CV is the factual authority.

Generated files have date-prefixed safe names and metadata recording the job, type, master-CV hash, content hash, template/generator versions, and optional Drive ID. CV facts can be reordered by relevance but are not invented. DOCX is always the primary output. PDF is best-effort and never aborts a run if unavailable on Termux.

## Configuration

Copy `.env.example` to `.env`. Important safe defaults:

- `HOST=127.0.0.1`, `PORT=8000` — local device only.
- `DATABASE_PATH=data/job_agent.db`.
- `APPLICATION_MODE=PREPARE`.
- `TIMEZONE=Africa/Johannesburg`.
- `GOOGLE_CREDENTIALS_FILE=data/secrets/credentials.json`.
- `GOOGLE_GMAIL_AUTO_SEND=false`.

Never commit `.env`, CVs, credentials, tokens, generated files, or logs.

## Doctor and manual commands

```bash
source .venv/bin/activate
python -m agents.cli doctor
python -m agents.cli init-db
python -m agents.cli run
python -m agents.cli run --sample
pytest -q
```

`doctor` prints PASS/WARN/FAIL for Python, database/schema, folders, CV, configuration, Google credentials/token, scheduler, and sources without printing secrets. `--sample` inserts one non-real example only for verification.

## Windows

Install Python 3.12+, copy `.env.example` to `.env`, and double-click `START_JOB_AGENT.bat`. It keeps the original Windows dashboard/scheduler workflow and opens http://localhost:8000. Use `STOP_JOB_AGENT.bat` to stop its named windows. Desktop Playwright is optional:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-google.txt -r requirements-browser.txt
playwright install chromium
```

## Linux

Use Python 3.12+, create `.venv`, install `requirements.txt` and `requirements-google.txt`, run `python -m agents.cli init-db`, then start Uvicorn and `python -m agents.scheduler` as separate processes.

## Database upgrades and interrupted runs

Startup runs additive SQLite/Postgres migrations; existing job/application history is retained. A
partial unique index permits one active run across serverless instances. A run older than the stale
window becomes `INTERRUPTED` when the next run begins, without cold starts invalidating healthy work.
Job/source uniqueness prevents restart duplicates. Granular within-source resume is not yet implemented.

## Tests and platform caveat

CI tests Python 3.12/3.13, compileall, pytest, Ruff fatal errors, diff cleanliness, and shell syntax. Linux CI validates portable code and scripts, **not a physical Android device**. Run `./INSTALL_ANDROID.sh`, `doctor`, a sample ingestion, CV generation, OAuth, and API smoke tests on the target phone before treating a build as device-validated.
