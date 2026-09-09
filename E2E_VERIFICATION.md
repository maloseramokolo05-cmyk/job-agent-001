# End-to-end verification

## Result: NOT RUN against a live deployment

No Vercel project credentials, production database, private bucket, Git remote, deployed URL, or
browser automation facility was configured in this checkout. It would be misleading to mark the
requested 22-step live journey as passed. Local automated checks cover API startup, health, SQLite
ingestion, CV parsing/generation, scoring, Google helpers, source URL protections and authentication
primitives. They do not establish redeployment durability or a live South African vacancy workflow.

A production E2E must remain a release gate and must use a dedicated test account/CV, real permitted
source configuration, and non-production Google account. It must preserve the resulting run IDs,
job URLs, object hashes, application-event IDs, screenshots, deployment ID, and HTTP/log evidence.
