# Security design and audit

## Hosted authentication

Only the application shell, login/status endpoints and minimal health response are public. Candidate data, configuration, jobs, applications, Gmail metadata, logs, OAuth callback, Drive/Calendar actions and documents require the single owner's server-side session. The bootstrap password comes from `ADMIN_PASSWORD`, is stored only as salted PBKDF2-SHA256 (600,000 iterations), and must contain at least 12 characters. Login attempts are window-rate-limited.

The random opaque session token is represented only by a SHA-256 digest in SQLite. Cookies are HttpOnly, SameSite Strict and Secure when `COOKIE_SECURE=true`; sessions expire. Every authenticated mutation requires the session CSRF token in `X-CSRF-Token`. Responses receive CSP, frame denial, MIME sniffing prevention, restrictive referrer/permissions policy, and APIs use `Cache-Control: no-store`.

## OAuth and tokens

Google OAuth uses Authorization Code + PKCE SHA-256, random one-time state, ten-minute expiry and exact redirect URI. Tokens are under persistent private storage, chmod 0600 where supported, outside web assets, ignored by Git and never returned by APIs. Refresh failures ask the owner to reconnect. Google passwords are never requested.

## Network and untrusted data

Configured feeds/pages must be HTTP(S), cannot contain URL credentials, must resolve, and every resolved address must be globally routable. Loopback, RFC1918/private, link-local, reserved and cloud-metadata destinations are rejected; redirects are revalidated. Production connectors use public structured interfaces and do not evade CAPTCHA, Cloudflare, authentication or rate limits.

Vacancies and emails are untrusted data, never instructions. Browser rendering escapes their HTML. Application URLs must be HTTP(S). Any future model integration must pass structured data as untrusted content and constrain output to the verified candidate model.

## Files

CV uploads accept PDF/DOCX only, have a 10 MB cap and validate magic bytes. Server-generated destination names prevent traversal. CVs/documents are outside static assets. Downloads resolve database-known paths and enforce containment under `APP_DATA_DIR`. Drive filenames are normalized and only app-marked files are listed.

## Consequential operations

Gmail sending defaults off and requires explicit confirmation; Calendar creation requires confirmation and deterministic duplicate checks. External submissions, login, CAPTCHA, OTP, MFA, identity checks and unsupported screening questions stay human-controlled. Status transitions are allow-listed and timeline events are immutable additions.

## Deployment boundary

SQLite plus embedded APScheduler is supported only as one process/instance on one persistent disk. Render is configured accordingly. Bind production behind HTTPS and never set `COOKIE_SECURE=false` there. Rotate the owner/Google secrets after suspected compromise and revoke Google access through the Google Account security page.

Local malware or a process running as the same OS user may still read private files; file permissions are not encryption. Backups and host/disk access controls remain the operator's responsibility.
