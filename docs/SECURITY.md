# Security review

## OAuth and tokens

OAuth uses Google's authorization-code endpoint, PKCE SHA-256, cryptographically random one-time state, a ten-minute state expiry, exact redirect URI, narrow scopes, and refresh. Tokens live outside static content under `data/tokens`, are chmod 0600 where supported, never returned by APIs, and are ignored by Git. Refresh failure is reported as reconnect-required rather than leaking a response.

## Local exposure and secrets

Launchers bind 127.0.0.1 by default. This product has no authentication layer and must not be exposed to LAN/public interfaces. `.env`, OAuth clients/tokens, SMTP secrets, CVs, documents, screenshots, runtime state, databases, and logs are ignored. Logs rotate and should contain event metadata, not tokens. Diagnostic APIs return connection booleans/scopes only.

## Uploads and paths

CV upload accepts only `.pdf`/`.docx`, caps at 10 MB, validates PDF/ZIP signatures, constructs the destination server-side, and never serves the CV directory. Generated/Drive filenames are normalized. Drive operations address database-known application documents and mark app files; unrelated Drive content is filtered out.

## Untrusted content

Vacancy/email text is untrusted. The frontend escapes HTML special characters before insertion. URLs are opened in a new browsing context and application submission remains user-controlled. Job descriptions must never become system instructions for AI. AI enrichment must use structured fields, treat vacancy text as data, and ground outputs in the master CV.

## Gmail and Calendar

Gmail queries are employment-focused. Sending defaults off and requires explicit confirmation or policy. Draft bodies must remain factual. Calendar creation requires confirmation and uses deterministic duplicate keys. Email-derived status changes should require high confidence; uncertain classifications remain review items.

## Remaining risks

Local malware or another process running as the same Android/Linux user may read files; chmod is not encryption. OAuth client secrets for installed/local apps cannot be perfectly protected. Users should lock their phone, keep Termux/app dependencies updated, revoke lost-device access, avoid public binding, and review generated documents/messages before use.
