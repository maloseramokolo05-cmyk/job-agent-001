# Android / Termux setup

Use the maintained F-Droid Termux release. Follow the README quick start. `INSTALL_ANDROID.sh` detects Termux, installs Python/Git/native libraries without sudo, creates `.venv`, installs core/Google dependencies, initializes additive SQLite migrations, and runs the doctor.

## Storage and CV upload

Run `termux-setup-storage` and approve Android's prompt only if shared storage is useful. Files become available under `~/storage/downloads` and `~/storage/shared`. Prefer the dashboard's PDF/DOCX upload: it validates extension, size, and file signature, then copies the CV to private `cv/` storage. CV files are not mounted as FastAPI static assets.

## Lifecycle

- `./START_ANDROID.sh` validates the environment, prevents duplicate tracked processes, starts localhost-only backend/scheduler, records exact PIDs in `runtime/`, and uses `termux-open-url` when available.
- `./scripts/status_android.sh` reports only this app's backend/scheduler PIDs plus non-secret database, run, Google, port, and source information.
- `./STOP_ANDROID.sh` signals only recorded PIDs. It never uses `pkill` or `killall`.
- `./UPDATE_ANDROID.sh` stops, fast-forward pulls, updates dependencies, migrates, and runs doctor.

## Android background behaviour

Disable battery optimization for Termux if scheduled runs matter. Android may still stop background processes. Optionally run `termux-wake-lock` before starting; this is not required and consumes battery. Stop releases it if available. After a kill, restart normally: migrations mark stale runs interrupted and database uniqueness prevents duplicate vacancies/applications.

## Google OAuth

Configure Google Cloud using `GOOGLE_API_SETUP.md`. Open the consent link on the same phone so the browser callback can reach Termux at 127.0.0.1. No out-of-band code or Google password is used.

## Troubleshooting

Run `python -m agents.cli doctor`, inspect `logs/backend.log`, `logs/scheduler.log`, and the rotating `logs/job_agent.log`, then check status. If port 8000 belongs to another application, change `PORT` in `.env` and update the Google redirect URI consistently. Playwright is intentionally desktop-only; on Android use Open Application, generated documents/prepared answers, then Mark Applied.
