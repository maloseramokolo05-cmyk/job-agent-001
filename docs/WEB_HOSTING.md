# Hosted Website Setup

The recommended testing path is a Render web service connected directly to this GitHub repository. Every push to the linked branch can auto-deploy, so testing updates does not require rebuilding an APK or running Termux.

## One-click test deployment

1. Sign in to Render and connect the GitHub account that can access `maloseramokolo05-cmyk/job-agent-001`.
2. For a private repository, install/authorize Render's GitHub app for this repo.
3. Use the Deploy to Render flow for this repository. Render reads the root `render.yaml`.
4. When prompted for secret environment variables, set:
   - `APP_USERNAME` — the username you want for the private website.
   - `APP_PASSWORD` — use a strong unique password.
   - `OPENAI_API_KEY` — optional until AI-backed generation is enabled.
   - `GOOGLE_CLIENT_ID` — optional until Google is configured.
   - `GOOGLE_CLIENT_SECRET` — optional until Google is configured.
5. Deploy.
6. Open the generated `https://<service>.onrender.com` URL and sign in with the app username/password.

The service starts with:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

The public health check is `/api/health`. The dashboard and all private APIs require HTTP Basic authentication when `APP_AUTH_ENABLED=true`.

## Google OAuth for the hosted site

After the first deployment, copy the exact service URL and add this Authorized redirect URI to the Google Cloud OAuth Web Client:

```text
https://<your-render-service>.onrender.com/api/google/callback
```

The application automatically builds the callback from Render's external hostname unless `GOOGLE_REDIRECT_URI` or `APP_BASE_URL` is explicitly set.

Enable the Gmail API, Google Drive API, and Google Calendar API in the same Google Cloud project. Keep Gmail auto-send disabled while testing.

## Free testing limitation

The checked-in `render.yaml` intentionally uses Render's free web-service plan so the product can be tested quickly. Free Render web services use an ephemeral filesystem. That means the following can be lost after a redeploy, restart, or idle spin-down:

- SQLite job/application history
- uploaded master CV
- generated CVs and cover letters
- Google OAuth refresh token
- edited local profile/preferences
- local logs

This is acceptable only for short-lived testing.

## Production persistence

Before relying on the website daily, use one of these options:

### Option A — paid Render service + persistent disk

Upgrade the web service to a paid compute plan and attach a persistent disk. Set:

```text
APP_DATA_DIR=/opt/render/project/src/persistent
```

Mount the disk at that exact path or another writable path and update `APP_DATA_DIR` to match. The application already routes SQLite, CVs, generated documents, editable configuration, Google tokens, and logs through `APP_DATA_DIR`.

### Option B — managed database/object storage

A future cloud-native release can migrate SQLite to Postgres and CV/document storage to managed object storage. This is better for multiple instances but is not required for the first private single-user website.

## Updating the website

With Render Git integration and auto-deploy enabled:

1. Make changes on a branch.
2. Let CI run.
3. Merge into the branch connected to Render (normally `main`).
4. Render automatically builds and deploys the new version.

No APK rebuild is required.

## Security notes

- Do not make `APP_USERNAME` or `APP_PASSWORD` public.
- Do not commit Google client secrets, OAuth tokens, CVs, `.env`, or API keys.
- Keep the default application mode `PREPARE` during testing.
- Gmail auto-send stays disabled by default.
- The `/api/health` endpoint intentionally exposes only non-sensitive service health.
