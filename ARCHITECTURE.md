# Architecture

The current application is FastAPI plus a static, dependency-free browser client. Domain work is
split between source adapters (`job_sources`), pipeline/scoring/document services (`agents`), Google
REST adapters (`integrations/google`), security (`backend/security.py`) and private object storage
(`backend/storage.py`). SQLite is used for local development and tests.

Production is designed to use an S3-compatible private bucket. Objects are addressed by opaque keys;
only the backend possesses storage credentials. `APP_ENV=production` fails startup unless S3 and
authentication settings are present. PostgreSQL and a durable worker are required before production
deployment, but are not present in this revision; see `PRODUCTION_READINESS.md`.

Greenhouse and Lever use their documented public JSON job-board endpoints. Configured RSS is also
supported. All generic outbound source requests resolve DNS and reject private/non-global addresses,
do not follow redirects, have connect/read timeouts, and enforce a 5 MB response limit.

Browser authentication uses an Argon2id administrator hash, an HttpOnly signed session token also
recorded in the database for revocation, a readable SameSite CSRF token that must match a custom
header, and Secure cookies in production. Private endpoints are denied by middleware.
