# Backend audit (2026-09-09)

## Scope and baseline

The repository was reviewed across `backend`, `agents`, `applications`, `job_sources`,
`integrations`, `frontend`, `tests`, CI, environment configuration, scripts and documentation.
There was no `api/` directory, `vercel.json`, configured Git remote, or locally available PR #4
metadata in this checkout. The supplied hosted-branch SHA is not present in the local object
database; this checkout started on `work` at `c3a5d53`.

## Findings

| Area | Baseline finding | Remediation in this change |
|---|---|---|
| Authentication | Every private endpoint was anonymous. | Argon2 password verification, signed server-side-recorded sessions, expiry/revocation, rate limiting, CSRF double-submit protection, secure production cookies and a login screen. |
| Persistence | SQLite and JSON files were the only stores. This loses data on Vercel. | Added persistent domain tables and an explicit production storage guard. **PostgreSQL support is not implemented in this checkout, so it must not be deployed as production.** |
| Files | Uploads/generated files were local paths and no authenticated download existed. | Uploads use a private S3-compatible abstraction in production with hashes and version records. Generated documents still require migration to object storage. |
| Sources | Normal runs only used user-provided RSS; a sample adapter was reachable by query parameter. | Added Greenhouse and Lever public API adapters and SSRF/size/redirect defenses. Sample remains test/dev-only. |
| Search execution | FastAPI in-process background tasks and a process-local lock are not durable. | Run checkpoints already persist, but no queue/worker was available. This remains a production blocker. |
| Verification | Vacancies were not fetched/verified before recommendation. | Not completed; production blocker. |
| Dedupe | Three SQLite unique constraints provide exact dedupe only. | Existing exact dedupe retained; cross-source similarity/source-record merging remains incomplete. |
| Scoring | Deterministic token overlap with coarse dimensions; no hard-disqualifier output. | Not completed; production blocker. |
| Documents | Factual master-CV lines are reordered into DOCX; this is not genuine structured tailoring. | Truthfulness guard retained. Versioned upload facts added, but generation/storage/download remain incomplete. |
| Applications | Status updates can create an application, but transition validation and preparation are incomplete. | Not completed; production blocker. |
| Google | PKCE/state, narrow scopes, token refresh, draft/send confirmation and basic Drive/Calendar support exist. Tokens are local files, not encrypted durable records. | Protected behind app authentication. Durable encrypted token storage remains incomplete. |
| Scheduling | APScheduler/local scripts exist; UI schedule values do not configure a Vercel Cron. | Not completed; production blocker. |
| Frontend | One-page dashboard exposes core records and actions. It used alerts, had a cosmetic “12-step” list, and lacked authentication/download flows. | Added login. Remaining incomplete controls must not be represented as production-ready. |
| Security | No auth/CSRF; RSS had unrestricted outbound requests; upload signatures and size were checked. | Added auth/security headers and centralized JSON HTTP errors; public-source requests reject non-public IPs, redirects and oversized responses. CSP still permits inline scripts because legacy handlers require them. |
| Tests | Unit/API tests covered happy-path SQLite, parsing, scoring and document generation. No production infrastructure or browser E2E coverage. | Added security/source tests; live infrastructure and browser E2E remain unverified. |

## Deployment and data-loss risk

The application **must not be promoted to Vercel production yet**. The source checkout does not
contain PostgreSQL support, durable generated-document storage, a durable worker, or Vercel
configuration. `/api/ready` intentionally reports object-storage readiness and production startup
fails closed when session/password/storage requirements are absent. A local SQLite database remains
appropriate only for local development and tests.

## Buttons and incomplete flows

“Run search” is process-bound; “Generate CV” and “Cover letter” write local files; document rows have
no download action; “Mark applied” skips a formal preparation state machine; Google operations require
external credentials and local tokens; schedule display does not itself schedule hosted work. These
are documented blockers rather than claims of completed functionality.
