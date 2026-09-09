# Backend audit (2026-09-09)

## Current production architecture

The application exposes a FastAPI app through `api/index.py` and Vercel rewrites. Neon Postgres is
the durable authority for job history, applications, sessions, OAuth state/tokens, master-CV text and
private file bytes. Local SQLite/files remain development-only.

## Findings and controls

| Area | Current state |
|---|---|
| Authentication | Argon2id dashboard password, signed server-side-recorded sessions, secure cookies, expiry/revocation, login throttling and CSRF checks. |
| Persistence | Postgres schema v4 with durable jobs, applications, documents, sessions, settings, OAuth state/tokens and file objects. |
| Runs | Postgres unique index prevents concurrent active runs; stale recovery happens only at the start of a later run; total/source time budgets bound Vercel execution. |
| Sources | Careers24 and configured iYouth feeds plus selected Greenhouse/Lever employers. Failures are isolated and stored in `source_status`. |
| RSA relevance | Greenhouse/Lever roles must be located in, or explicitly remotely open to, South Africa. Pretoria/Gauteng priority is applied in scoring/order. |
| Email safety | Only explicit CV/application email wording qualifies. The exact address is re-verified on the live vacancy immediately before preview/send. Gmail Sent is checked before delivery. |
| Documents | Master and vacancy-specific files are private database objects with SHA-256 metadata and authenticated downloads. Generation requires verified master-CV text. |
| Google | PKCE, expiring single-use state, minimal feature scopes, encrypted durable tokens, refresh-token support, Gmail attachments/sync, Drive app files and confirmed Calendar events. |
| Scheduling | Vercel Cron calls `/api/cron/search` daily at 05:00 UTC and must supply `Authorization: Bearer <CRON_SECRET>`. |
| Remaining gate | Live Vercel/Neon/Google configuration and end-to-end production verification; no successful send is claimed before owner approval. |
