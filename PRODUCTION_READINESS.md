# Production readiness — Tumelo Job Agent 3.0.0

## Audit findings addressed

The inherited v2 foundation had no authentication, assumed local-only exposure, offered only RSS/sample discovery, used shallow keyword scoring, exposed no authenticated document download, and had no hosted deployment topology. The CI definition existed but the supplied execution environment could not install its dependencies. This release concentrates on those engine and security gaps rather than another cosmetic redesign.

## Production architecture

A single FastAPI/SQLite web instance owns one persistent disk. `backend.serve` starts one APScheduler instance alongside one Uvicorn worker. An in-process lock plus a persisted expiring `run_locks` row prevents overlapping searches. `APP_DATA_DIR` contains SQLite, copied configuration, master CV, generated documents, OAuth tokens and logs. Render is deliberately configured with `numInstances: 1`; horizontal scaling requires migrating to a shared database and distributed scheduler lock.

The discovery registry contains independent configured RSS, JSON-LD `JobPosting`, Greenhouse public job-board and Lever public-posting connectors. URLs are resolved and rejected unless globally routable, redirects are revalidated, source failures are isolated, and source counts/health are persisted. Sample data is excluded unless both an explicit flag and explicit sample run are used.

## Security model

A single owner account is bootstrapped from deployment secrets. Passwords are PBKDF2-SHA256 hashed with unique salts and 600,000 iterations. Random opaque sessions are stored server-side; browser cookies are HttpOnly, SameSite Strict, and Secure in production. Session expiry, login throttling, CSRF headers, restrictive CSP/security headers, protected APIs, private downloads, bounded logs, upload signatures, path containment and SSRF controls protect hosted data. `/api/health` returns only status/version.

OAuth remains Google Authorization Code + PKCE and one-time expiring state. OAuth clients, tokens and CVs stay on the persistent disk and outside static assets. Gmail sends and Calendar creation remain confirmation gated.

## Workflow and factual safety

Vacancies are normalized, verified, deduplicated across source URLs, scored with structured dimensions, and stopped on hard unverified work-authorization requirements. Scoring is an explanation, not a hiring probability. Documents reorder only master-CV facts. Application packages surface missing profile fields/questions and never guess screening answers. CAPTCHA, Cloudflare, login, OTP, MFA and identity checks remain manual by design.

## Deliberately manual

External web submission has no generic auto-submit because legality, forms and protections vary. The workspace prepares documents/known answers, preserves state and opens the external URL. A reviewed source-specific adapter may be added later. Gmail sending and Calendar event creation require explicit confirmation. Google and external sources show not configured until their owner-supplied settings exist.

## Validation status

Compile, shell syntax, migration and dependency-independent tests can run in the provided container. Full FastAPI/document/HTTP tests require installing declared dependencies. CI installs them on Python 3.12/3.13 and runs compileall, Ruff, pytest, diff checks and shell syntax. A green hosted CI run and staging smoke test are required before merge; this document does not claim they occurred locally.
