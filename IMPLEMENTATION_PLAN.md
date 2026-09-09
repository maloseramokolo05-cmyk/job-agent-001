# Tumelo Job Agent Implementation Plan

## Architecture
A local FastAPI service hosts a responsive vanilla-JavaScript dashboard and JSON API. A modular Python pipeline coordinates configuration, CV extraction, source discovery, deterministic scoring, document preparation, and safe application queuing. SQLite provides durable local storage; APScheduler and Windows Task Scheduler entry points support unattended searches.

## Database schema
`jobs` stores normalized vacancies, content hashes, score breakdowns, document paths, unanswered questions, and lifecycle status with unique URL/vacancy/fingerprint indexes. `applications` stores an immutable preparation/submission audit trail and CRM fields. `runs`, `events`, and `settings` support progress, logs, and dashboard configuration.

## Agent structure
The orchestrator executes SEARCH → DEDUPLICATE → PARSE → SCORE → SHORTLIST → DOCUMENTS → PREPARE. Focused services handle CV parsing, matching, document generation, email drafts, application safety, and scheduling.

## Search connectors
Every connector implements one interface and fails independently. Initial connectors use permitted public feeds/pages and a local sample connector for verification. Restricted, authenticated, CAPTCHA, or unsupported flows are retained as manual URLs rather than bypassed.

## AI pipeline
Deterministic extraction and scoring run first. Optional OpenAI analysis receives only relevant vacancy fields and grounded CV text, is budget-limited, and cached by description hash. Generated content is constrained to facts from the profile/master CV.

## Application pipeline
Four modes are supported, defaulting to `PREPARE`. Applications are deduplicated and audited before interaction. Playwright adapters may populate factual fields; unknown questions stop the workflow as `NEEDS USER INPUT`. Submission and email sending require explicit opt-in.

## Dashboard structure
The single-page local UI provides first-run setup, metrics, live run progress, filtering, vacancy detail, document/action controls, settings, and CSV export.

## Security
Secrets remain in `.env`, sensitive files are ignored, API keys are never returned by settings APIs or logged, URLs are validated, and automation respects access controls and rate limits.

## Implementation phases
1. Scaffold configuration, persistence, domain models, and logging.
2. Implement CV/job parsers, connectors, scoring, deduplication, and orchestration.
3. Add grounded DOCX/PDF/cover-letter and safe application/email preparation.
4. Add FastAPI API, dashboard, setup wizard, scheduler, and Windows scripts.
5. Add unit/integration tests, initialize the database, ingest a sample vacancy, generate a CV, and smoke-test startup/dashboard.
