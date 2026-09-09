# Tumelo Job Agent 3.0.0

A private hosted career operations workspace: discover genuine vacancies from configured public sources, verify/deduplicate/score them against factual candidate data, generate ATS-safe documents, prepare and track applications, and optionally connect Gmail, Drive and Calendar.

## Hosted deployment (canonical)

The included `render.yaml` provisions **one** Render web instance and a persistent disk. SQLite and the embedded scheduler intentionally require a single instance.

1. Fork or push this repository to a private GitHub repository.
2. In Render choose **New → Blueprint**, connect the repository, and apply `render.yaml`.
3. Set secret `ADMIN_PASSWORD` to a unique value of at least 12 characters. Keep `ADMIN_USERNAME=owner` or change it before first boot.
4. Deploy. Render installs `requirements.txt` and `requirements-google.txt`, then starts `python -m backend.serve`.
5. Open `/api/health`; it intentionally returns only status and version. Open `/`, sign in, complete setup, upload/verify the CV, add source identifiers/pages, and run the first search.
6. For Google integration, set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI=https://YOUR-HOST/api/google/callback`, then register that exact URI in Google Cloud.

Persistent `APP_DATA_DIR=/var/data/tumelo-job-agent` stores the database, private config, CV, generated documents, tokens and logs across deploys. Do not scale above one instance. A future multi-instance deployment must use PostgreSQL and a distributed scheduler lock.

## Required and optional environment values

| Variable | Required | Purpose |
|---|---:|---|
| `ADMIN_PASSWORD` | yes | First-boot owner password (12+ characters) |
| `ADMIN_USERNAME` | recommended | Owner login name; defaults to `owner` |
| `APP_DATA_DIR` | hosted | Persistent disk root |
| `DATABASE_PATH` | no | Relative to `APP_DATA_DIR`; default `data/job_agent.db` |
| `COOKIE_SECURE` | production | Must be `true` on HTTPS |
| `SESSION_HOURS` | no | Server-side session lifetime |
| `SESSION_SECRET` | production | HMAC signing key; Render generates it |
| `HOST`, `PORT` | hosting | Bind address/hosting port |
| `TIMEZONE` | no | Defaults to `Africa/Johannesburg` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Google only | OAuth client and exact hosted callback |
| `OPENAI_API_KEY` | no | Reserved optional semantic analysis; deterministic scoring works without it |
| `GOOGLE_GMAIL_AUTO_SEND` | no | Defaults false; explicit confirmation remains standard |

Never commit `.env`, credentials, tokens, passwords, CVs, generated documents or databases.

## Real discovery sources

Configure these in Settings/profile JSON. Empty source lists truthfully return no invented jobs.

- `search_feeds`: permitted RSS feeds.
- `career_pages`: public pages containing Schema.org `JobPosting` JSON-LD.
- `greenhouse_boards`: employer Greenhouse public board identifiers.
- `lever_sites`: employer Lever public site identifiers.

Every connector runs independently, publishes capability/last-success/error/count state, and cannot abort other sources. Fetching is limited to globally routable HTTP(S) hosts; private, loopback, link-local and metadata addresses are blocked, including after redirects. Sample jobs require both an explicit demo call and `ALLOW_SAMPLE_SOURCE=true`.

## Product workflow

`SEARCH → NORMALIZE → VERIFY → DEDUPLICATE → PARSE → SCORE → PRIORITIZE → TAILOR → PREPARE → REVIEW → EXPLICIT SEND/SUBMIT → TRACK`

Scoring separates role, skills, experience, education, location, work arrangement, salary, language, industry, seniority and portfolio requirements. Hard unverified work-authorization requirements stop automatic shortlisting. The score is not a hiring probability. One logical vacancy retains all discovered source URLs.

The master CV and user-verified profile are the only candidate truth. Tailoring may reorder/emphasize verified facts, never invent them. Authenticated downloads keep generated files outside static assets. External submissions remain assisted unless a permitted dedicated adapter exists; CAPTCHA, Cloudflare, OTP, MFA and unknown questions always require the user.

## Security

All private APIs require an expiring server-side session. Passwords use salted PBKDF2-SHA256; login is rate-limited; cookies are HttpOnly, SameSite Strict and Secure in production; mutations require a CSRF token. CSP/frame/MIME/referrer/permissions headers, no-store API responses, SSRF checks, upload signature/size checks, path-contained downloads, bounded logs and escaped UI content protect the hosted workspace. Only the static shell, login/status and minimal health endpoint are public.

See `docs/SECURITY.md`, `docs/GOOGLE_API_SETUP.md`, and `PRODUCTION_READINESS.md`.

## Google

OAuth uses Authorization Code + PKCE, one-time expiring state and narrow scopes. Gmail searches employment-related metadata, classifies conservatively, associates only on employer/role evidence, and does not auto-reject. Drafts are reviewable; sending is confirmation-gated. Drive uses `drive.file` and app-marked files. Calendar events require confirmation and are deduplicated.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-google.txt
cp .env.example .env                     # PowerShell: Copy-Item .env.example .env
# Set ADMIN_PASSWORD to 12+ characters and COOKIE_SECURE=false
python -m agents.cli init-db
python -m backend.serve
```

Open http://127.0.0.1:8000. Windows launchers and Android scripts remain available for secondary local use. Desktop Playwright is optional via `requirements-browser.txt`; it is not part of the hosted core.

## Verification

```bash
python -m compileall -q backend agents applications integrations job_sources tests
ruff check .
pytest -q
git diff --check
```

CI runs these on Python 3.12 and 3.13. External HTTP/Google services are mocked. Before production use, also complete the signed-in staging journey: setup → CV parse/verification → configure source → search → match review → generate/download CV → prepare application → track it → optionally create Gmail draft and Calendar event.
