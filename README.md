# Tumelo Job Agent

A standalone, safety-first Windows job discovery and application-preparation workspace. It runs locally at **http://localhost:8000** and does not require the ChatGPT website. The initial application mode is **PREPARE**: it can search, score, produce grounded documents, and queue work, but it will not submit an application.

## What it does

- Loads the editable candidate profile and master PDF/DOCX CV; the CV remains the factual source of truth.
- Searches configured public RSS vacancy feeds through independent connectors. The connector interface supports dedicated Careers24, PNet, CareerJunction, public-sector, recruitment, or company-career adapters without coupling the pipeline to a website. Sites requiring login, CAPTCHA, or unsupported interaction remain manual.
- Deduplicates by vacancy/source, URL, and normalized role/employer/location, then scores each vacancy from 0–100 with an explainable weighted breakdown.
- Generates plain ATS-friendly DOCX and PDF CV versions, optional cover letters, and tracks lifecycle/status locally in SQLite.
- Provides a setup wizard, dashboard, filters, vacancy detail/actions, live run state, CSV export, scheduling, email-draft primitives, and guarded Playwright extension points.

> **Important:** Public websites change their terms and markup. Configure only feeds/pages you are permitted to access. This project does not bypass CAPTCHAs, authentication, access restrictions, or rate limits. Generic sources are marked manual; automatic submission requires a reviewed site-specific adapter, complete factual answers, `AUTO_APPLY`, and explicit confirmation.

## Windows setup (copy into PowerShell)

1. Install 64-bit Python 3.12 from python.org and select **Add Python to PATH**.
2. Download/clone this repository, then open PowerShell in it:
   ```powershell
   cd C:\path\to\job-agent-001
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Copy the environment template:
   ```powershell
   Copy-Item .env.example .env
   ```
4. Put your CV at `cv\master_cv.pdf` or `cv\master_cv.docx`. Do not commit it.
5. Edit `config\profile.json` and `config\job_preferences.json`, or use the first-run wizard. Never add a qualification or skill that is not true.
6. Optionally put `OPENAI_API_KEY=...` in `.env`. The deterministic core works without it; no key is sent to the browser.
7. Install browser automation support (needed only by future permitted site adapters): `playwright install chromium`.
8. Double-click **`START_JOB_AGENT.bat`**. It checks/installs dependencies, initializes SQLite, launches the scheduler and backend, and opens the browser.
9. Open **http://localhost:8000**, complete setup, then click **Start Job Run**.
10. To stop, double-click **`STOP_JOB_AGENT.bat`**.

### Scheduling while the dashboard is closed

Open PowerShell **as Administrator**:
```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_windows_task.ps1
```
Times are 07:00, 13:00, and 18:00 in the Windows task. In-app scheduler times come from `config/job_preferences.json` and use Africa/Johannesburg time.

### Add public search feeds

Add permitted RSS/Atom-compatible vacancy feed URLs to `search_feeds` in `config/job_preferences.json`. Empty defaults avoid pretending to search unsupported websites. A developer can add a connector under `job_sources/` by implementing `JobSource.search`; connector failures are isolated.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | Optional future AI enrichment; never exposed in UI | empty |
| `OPENAI_MODEL` | Optional enrichment model | `gpt-5-mini` |
| `DATABASE_PATH` | SQLite location | `data/job_agent.db` |
| `DAILY_AI_BUDGET` | Daily API-cost ceiling | `2.00` |
| `MAX_JOBS_PER_RUN` | Discovery processing limit | `100` |
| `MIN_MATCH_SCORE` | Environment fallback | `75` |
| `EMAIL_AUTO_SEND` | Must be true before SMTP sending | `false` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional SMTP details | empty |

## Useful commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m agents.cli init-db
python -m agents.cli run
python -m agents.cli run --sample
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pytest -q
```

`--sample` inserts one clearly labelled, non-real example vacancy for end-to-end verification. Normal dashboard runs do not insert samples.

## Automatic versus human-controlled

**Automatic:** permitted feed retrieval, parsing, deduplication, deterministic factual matching, score explanations, shortlisting, grounded document creation when a master CV exists, audit logging, scheduling, and CSV export.

**Human/review required:** adding/reviewing source permissions; entering missing profile facts; validating every generated document; CAPTCHA/login/anti-bot flows; unsupported questions; final submission in default mode; and email sending unless explicitly enabled. The generic automation layer never guesses answers or submits merely because a score is high.

## Project map

- `backend/`: FastAPI, configuration, SQLite API
- `agents/`: orchestrator, parsers, scoring, documents, scheduler
- `job_sources/`: isolated connector interface and configured RSS/sample connectors
- `applications/`: guarded browser/email preparation primitives and screenshot storage
- `frontend/`: responsive local dashboard and first-run wizard
- `config/`: editable candidate and search preferences
- `cv/`: private master CV input
- `generated_cvs/`, `cover_letters/`: generated application documents
- `data/`, `logs/`: private runtime database/logs
- `scripts/`: Windows launch and Task Scheduler helpers
- `tests/`: core and HTTP integration tests

## Email setup

Enter SMTP variables in `.env`. Keep `EMAIL_AUTO_SEND=false` to prepare drafts only. Gmail accounts should use OAuth or an app password rather than the normal account password. Sending remains off unless explicitly enabled.

## Privacy and recovery

Everything is local except requests to configured vacancy feeds and any services you explicitly enable. Back up `data/job_agent.db`, `config/`, and document folders. Secrets, CVs, logs, runtime databases, generated files, and screenshots are excluded from Git.
