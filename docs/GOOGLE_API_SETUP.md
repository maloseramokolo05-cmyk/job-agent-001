# Google API and OAuth setup

1. Open Google Cloud Console and create/select a project named **Tumelo Job Agent**.
2. In **APIs & Services → Library**, enable **Gmail API**, **Google Drive API**, and **Google Calendar API**.
3. Configure the OAuth consent screen. Choose External for a normal consumer account, provide the required app/contact details, add your account as a test user while the app remains in testing, and declare only the scopes you enable.
4. Create an **OAuth 2.0 Client ID** of type **Web application**. Add exactly `http://127.0.0.1:8000/api/google/callback` as an authorized redirect URI. Google requires the callback string to match.
5. Download the client JSON. On Android, use the dashboard/storage copy workflow or:
   ```bash
   mkdir -p data/secrets
   cp ~/storage/downloads/client_secret_*.json data/secrets/credentials.json
   chmod 600 data/secrets/credentials.json
   ```
   Alternatively set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. Never commit either form.
6. Set `GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/google/callback`, restart the app, open **Google Integrations**, and press **Connect Google account**.
7. The browser uses Google's own login/consent page. The app never receives a Google password. The callback validates a one-time state and PKCE verifier, exchanges the code, and saves the token at `data/tokens/google_token.json` with restrictive permissions where supported. Deprecated out-of-band OAuth is not used.
8. If localhost returns to the wrong browser/device, make sure authorization was opened on the same phone where Termux is serving port 8000. Copying the authorization URL into that phone's browser is the safe fallback.

## Permissions

Gmail read/compose supports focused job-mail sync and drafts. Gmail send is separate and should only be enabled when required. `drive.file` limits access to app-created/opened files. `calendar.events` creates/updates events but does not grant broad Drive or mailbox access.

## Revoke or recover

**Clear local Google state** deletes only the local token. To revoke server-side access, visit Google Account → Security → Third-party apps and remove Tumelo Job Agent. `AUTH_EXPIRED` means refresh failed: clear local state and reconnect. Rotating the OAuth client secret also requires updating the private config and reconnecting.
