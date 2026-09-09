# Production readiness

**Decision: NOT READY FOR PRODUCTION.** This is a truthful gate, not a deployment guide claiming a
successful hosted workflow.

Completed hardening includes application login/session/CSRF controls, security headers, private
S3-compatible master-CV uploads, upload hashes/version records, and public Greenhouse/Lever/RSS
connectors with SSRF defenses.

Blocking work remains: PostgreSQL repository/migrations, S3 storage for generated documents and
authenticated downloads, durable queue/workflow execution, hosted scheduling, complete vacancy
verification and cross-source dedupe, application state-machine enforcement, encrypted durable Google
tokens, and full browser E2E against provisioned infrastructure. No production URL or infrastructure
credentials were available in this checkout, and no deployment was attempted.

Required production variables currently implemented are `APP_ENV`, `APP_BASE_URL`, `SESSION_SECRET`,
`ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `STORAGE_PROVIDER`, `S3_BUCKET`, optional
`S3_ENDPOINT_URL`, AWS SDK credentials, `S3_SERVER_SIDE_ENCRYPTION`, Google OAuth variables,
`CRON_SECRET`, `OPENAI_API_KEY`, and `MAX_JOBS_PER_RUN`.
