# Tumelo Job Agent 2.0.0

## WEBSITE QUICK START — RECOMMENDED

The easiest way to test and keep this project updated is now as a **private hosted website**. The repository includes a Render Blueprint (`render.yaml`) that deploys the FastAPI backend and mobile-friendly dashboard together.

### Deploy

1. Sign in to Render and connect the GitHub account that can access this private repository.
2. Authorize Render's GitHub app for `maloseramokolo05-cmyk/job-agent-001`.
3. Deploy the repository as a Blueprint using the included `render.yaml`.
4. When Render asks for secret environment variables, provide:
   - `APP_USERNAME`
   - `APP_PASSWORD`
   - `OPENAI_API_KEY` (optional for initial UI testing)
   - `GOOGLE_CLIENT_ID` (optional until Google integration is configured)
   - `GOOGLE_CLIENT_SECRET` (optional until Google integration is configured)
5. Open the generated `https://...onrender.com` URL and sign in with your app username/password.

The website is responsive and works directly in Chrome on Android. No Termux is needed for normal website use. It can also be installed to the Android home screen as a PWA if the browser offers the install option.

### Updates

The Blueprint has Git auto-deploy enabled. After CI passes and a change is merged to the connected branch (normally `main`), Render automatically rebuilds the website. No APK rebuild is needed.

### Free testing warning

The default Blueprint uses Render's free web-service plan so you can test without committing to hosting costs. Free Render services have ephemeral local storage, so SQLite history, uploaded CVs, generated files, Google tokens, and edited settings can disappear after a restart, idle spin-down, or redeploy.

For daily use, upgrade to a paid Render service and attach a persistent disk, then set `APP_DATA_DIR` to the disk mount path. The code already routes runtime data through `APP_DATA_DIR`.

Read the full guide: [`docs/WEB_HOSTING.md`](docs/WEB_HOSTING.md).

## Google setup for the website

After the website is deployed, add this exact redirect URI to the Google Cloud OAuth Web Client:

```text
https://<your-render-service>.onrender.com/api/google/callback
```

Enable Gmail, Drive, and Calendar APIs in the same Google Cloud project. The hosted app automatically uses the Render external hostname for OAuth unless an explicit redirect URL is configured.

Gmail auto-send remains disabled by default. Calendar creation still requires confirmation.

## Security

Hosted mode supports private HTTP Basic authentication. `APP_AUTH_ENABLED=true` is set by the Render Blueprint, and you provide `APP_USERNAME` and `APP_PASSWORD` as Render secrets. The public health endpoint contains no credentials, OAuth tokens, CV data, or API keys.

Never commit `.env`, CVs, Google secrets/tokens, generated documents, or logs.

## ANDROID LOCAL MODE

If you prefer everything to remain on your phone instead of hosting it, Termux is still supported:

```bash
pkg update -y
pkg install git -y
git clone https://github.com/maloseramokolo05-cmyk/job-agent-001.git
cd job-agent-001
chmod +x INSTALL_ANDROID.sh START_ANDROID.sh STOP_ANDROID.sh UPDATE_ANDROID.sh scripts/status_android.sh
./INSTALL_ANDROID.sh
./START_ANDROID.sh
```

Open `http://127.0.0.1:8000`.

Use `./scripts/status_android.sh`, `./STOP_ANDROID.sh`, and `./UPDATE_ANDROID.sh` for lifecycle management. See [`docs/ANDROID_SETUP.md`](docs/ANDROID_SETUP.md).

## Capability truth table

| Capability | Hosted website | Android local | Notes |
|---|---|---|---|
| Dashboard, scoring, CRM | SUPPORTED | SUPPORTED | FastAPI + responsive frontend |
| SQLite persistence | TEST-ONLY on free hosting | SUPPORTED | Use paid Render disk for hosted persistence |
| CV upload/generation | SUPPORTED | SUPPORTED | Hosted files persist only with persistent storage |
| Google OAuth | SUPPORTED | SUPPORTED | Hosted redirect URI must be added to Google Cloud |
| Gmail | PARTIAL | PARTIAL | Search/classification/drafts/send guard exist; full reply threading still needs work |
| Drive | PARTIAL | PARTIAL | Upload/list basics exist; complete two-way master-CV sync is not finished |
| Calendar | PARTIAL | PARTIAL | Confirmed event creation/dedupe exists; Gmail-to-event extraction needs work |
| Application links | ASSISTED | ASSISTED | User reviews/submits supported application pages |
| Generic browser auto-apply | NOT READY | DESKTOP ONLY | No CAPTCHA/login bypass |

## Pipeline

`SEARCH → NORMALIZE → DEDUPLICATE → PARSE → SCORE → PRIORITIZE → DOCUMENTS → PREPARE → REVIEW → explicit send/submit → TRACK`

Default application mode is `PREPARE`.

## Job-source limitation

Real job discovery is still the largest unfinished product area. The current core source is configurable RSS and the default `search_feeds` list can be empty. Configure legitimate vacancy feeds/connectors before expecting meaningful daily search results.

## Local configuration

Copy `.env.example` to `.env` for local use. Important defaults:

- `HOST=127.0.0.1`
- `PORT=8000`
- `APPLICATION_MODE=PREPARE`
- `TIMEZONE=Africa/Johannesburg`
- `GOOGLE_GMAIL_AUTO_SEND=false`
- `APP_AUTH_ENABLED=false` locally

## Doctor and tests

```bash
source .venv/bin/activate
python -m agents.cli doctor
python -m agents.cli init-db
python -m agents.cli run --sample
python -m pytest -q
```

CI tests Python 3.12/3.13, compileall, pytest, Ruff, diff cleanliness, Android script syntax, and the existence of the Render Blueprint. CI cannot by itself prove a real Google OAuth account or physical Android device works end-to-end.

## Windows

Python 3.12+ remains supported. Copy `.env.example` to `.env` and run `START_JOB_AGENT.bat`; use `STOP_JOB_AGENT.bat` to stop it.

## Production note

The hosted web path is currently the easiest way to test and receive updates. Treat the free Render deployment as a **test environment**, not the final production datastore. Before relying on it for job history and Google tokens, add persistent storage or migrate the runtime state to managed database/object storage.
