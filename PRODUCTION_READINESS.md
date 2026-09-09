# Production readiness

The codebase is production-capable, but completion is determined only by the live acceptance test.
No deployment is declared complete merely because a build reports Ready.

Implemented controls:

- private login, signed durable sessions, CSRF validation and production-only secure cookies;
- Neon/Postgres schema migrations and durable storage for jobs, applications, documents and tokens;
- database-backed private master-CV and generated-document downloads;
- Careers24, iYouth RSS, Greenhouse and Lever discovery with source isolation;
- South Africa filtering and Pretoria/Gauteng scoring priority;
- truthful CV generation from verified master-CV text;
- strict vacancy email extraction and immediate live re-verification before a send;
- Gmail Sent duplicate checks, PDF attachments and application tracking;
- a no-send email preview for the first-production-send approval gate;
- one active run across serverless instances, stale-run recovery and execution budgets;
- Vercel Cron bearer authorization and a daily 05:00 UTC / 07:00 SAST schedule.

Production remains incomplete until the deployed `/api/health` and `/api/ready` endpoints pass,
Google OAuth stores a refresh token in Neon, a real RSA search persists results, a generated PDF is
downloaded after a reload, Gmail sync succeeds, and the first suitable verified email application is
approved by the owner and recorded with a Gmail message ID.

The checked-in preference keeps `email_auto_send` disabled. It may be enabled in the durable
production preferences only after that first approved send. Login/CAPTCHA/OTP/MFA-gated web forms
remain `NEEDS_USER_ACTION`.
