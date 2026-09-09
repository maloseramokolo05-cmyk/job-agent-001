# Google API and OAuth setup

This integration is for the private **Tumelo Job Agent** production app. The backend uses Google's server-side OAuth flow with one-time `state`, PKCE, offline access, refresh tokens, and server-side token storage.

## 1. Create/select the Google Cloud project

Create or select a Google Cloud project named **Tumelo Job Agent**.

Enable these APIs:

- Gmail API
- Google Drive API
- Google Calendar API

## 2. Configure Google Auth Platform

Open **Google Auth Platform** for the project.

### Branding

Use:

- App name: `Tumelo Job Agent`
- User support email: the Gmail account used by Tumelo Job Agent
- Developer contact email: the same monitored account

This is a private/personal-use application, not a public SaaS product.

### Audience

Use **External** for a normal consumer Gmail account.

While testing, add the Tumelo Gmail account under **Audience → Test users**.

For a long-running production agent, do not leave the project in Testing indefinitely: Google can issue refresh tokens with a limited lifetime for External apps in Testing. For personal use, Google documents an exception from OAuth verification for apps used only by the owner or a few personally known users; the account may still see an unverified-app warning and user caps can apply.

## 3. Configure Data Access scopes

Declare only the scopes used by the app:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/calendar.events`

`gmail.compose` already authorizes Gmail draft creation and email sending, so a separate `gmail.send` grant is not required for the current implementation.

## 4. Create the OAuth client

Create an **OAuth 2.0 Client ID** with application type **Web application**.

Recommended name:

`Tumelo Job Agent Web`

### Authorized redirect URIs

Production must use a stable HTTPS hostname. Add exactly:

`https://<STABLE-PRODUCTION-HOST>/api/google/callback`

The app's production environment must set the same value in `GOOGLE_REDIRECT_URI` (or derive it from an identical `APP_BASE_URL`). Google requires the redirect URI to match exactly.

For local development you may additionally add:

`http://127.0.0.1:8000/api/google/callback`

No Authorized JavaScript Origin is required for the current server-side authorization-code flow.

## 5. Configure private production credentials

Never commit the client ID or client secret.

Set these private production values in the hosting environment:

```text
GOOGLE_CLIENT_ID=<oauth-web-client-id>
GOOGLE_CLIENT_SECRET=<oauth-web-client-secret>
GOOGLE_REDIRECT_URI=https://<STABLE-PRODUCTION-HOST>/api/google/callback
GOOGLE_GMAIL_ENABLED=true
GOOGLE_DRIVE_ENABLED=true
GOOGLE_CALENDAR_ENABLED=true
```

`SESSION_SECRET` or `TOKEN_ENCRYPTION_KEY` must also be at least 32 characters because the production Google token is encrypted before being stored in the durable database.

## 6. Connect the account

1. Log into Tumelo Job Agent.
2. Open **Google Integrations**.
3. Click **Connect Google account**.
4. Sign in with the Tumelo Gmail account on Google's own page.
5. Review and approve the requested Gmail, Drive and Calendar permissions.
6. Google redirects to `/api/google/callback`; the server validates `state` + PKCE, exchanges the authorization code, encrypts the resulting token and stores it in the production database.

The app never receives or stores the Google account password.

## 7. Production verification checklist

After OAuth completes, verify:

- `/api/google/status` returns `connected: true`
- Gmail scopes include `gmail.readonly` and `gmail.compose`
- Gmail sync can read job-related mail
- Draft creation works
- A user-confirmed test send works
- Drive upload works
- Calendar event creation works after explicit confirmation
- The encrypted Google token persists across a redeploy/restart
- Token refresh works after the access token expires

## Revoke or recover

**Disconnect Google** clears the locally stored encrypted token used by Tumelo Job Agent.

To revoke access at Google as well, open Google Account → Security → third-party app access and remove **Tumelo Job Agent**.

If refresh fails with `AUTH_EXPIRED` / `invalid_grant`, reconnect the account. If the Google project is still in Testing, check its publishing status because Testing can cause limited refresh-token lifetime for External apps.
