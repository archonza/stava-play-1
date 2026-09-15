# Deploying to Google Cloud Run (free tier)

This app is stateless and gets its 30-minute refresh from an external Cloud
Scheduler job, so it runs cleanly on Cloud Run. You'll need:

- A Google account with billing enabled on a Cloud project (Cloud Run's
  "Always Free" quota is generous enough that a small group tracker shouldn't
  be charged, but Google still requires a card on file).
- A free [Neon](https://neon.tech) Postgres database (no card required).
- A Strava API application (same as local dev, see [README.md](README.md)).

None of these accounts can be created on your behalf — this doc is the exact
sequence of steps and commands to run yourself.

## 1. Create the Neon database

1. Sign up at https://neon.tech and create a new project.
2. Copy the connection string it gives you (looks like
   `postgresql://user:password@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`).
   You'll use this as `DATABASE_URL`. The app creates its own table on first
   boot — no manual schema setup needed.

## 2. Create the Strava API application

Follow [README.md](README.md) section 1, but leave **Authorization Callback
Domain** as `localhost` for now — you'll come back and update it in step 8
once you know the app's real URL.

## 3. Install and authenticate the Google Cloud CLI

1. Install `gcloud`: https://cloud.google.com/sdk/docs/install
2. `gcloud init` — sign in and either select or create a project.
3. Enable the APIs this deployment needs:

   ```bash
   gcloud services enable run.googleapis.com \
     cloudbuild.googleapis.com \
     secretmanager.googleapis.com \
     cloudscheduler.googleapis.com
   ```

## 4. Generate secret values

Generate a strong `FLASK_SECRET_KEY` and `SYNC_TOKEN` (used to authenticate
Cloud Scheduler's calls to `/internal/sync` — keep it secret, don't reuse it
elsewhere):

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # FLASK_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"   # SYNC_TOKEN
```

## 5. Store secrets in Secret Manager

Run each of these, pasting in the real value when prompted (piping the value
in via stdin keeps it out of your shell history):

```bash
printf '%s' 'your-strava-client-secret'   | gcloud secrets create STRAVA_CLIENT_SECRET --data-file=-
printf '%s' 'the-flask-secret-key'        | gcloud secrets create FLASK_SECRET_KEY --data-file=-
printf '%s' 'the-sync-token'              | gcloud secrets create SYNC_TOKEN --data-file=-
printf '%s' 'your-neon-connection-string' | gcloud secrets create DATABASE_URL --data-file=-
```

## 6. Grant Cloud Run access to the secrets

Cloud Run runs as your project's default compute service account, which needs
explicit permission to read each secret before it can mount them as env vars:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format="value(projectNumber)")

for SECRET in STRAVA_CLIENT_SECRET FLASK_SECRET_KEY SYNC_TOKEN DATABASE_URL; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

Skipping this step causes `gcloud run deploy` to fail with `Permission denied
on secret` when it tries to attach the secrets to the service.

## 7. First deploy

From the repo root:

```bash
gcloud run deploy strava-km-tracker \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --timeout=300 \
  --set-env-vars APP_ENV=production,STRAVA_CLIENT_ID=your_strava_client_id,STRAVA_REDIRECT_URI=https://placeholder,REFRESH_INTERVAL_MINUTES=30 \
  --set-secrets STRAVA_CLIENT_SECRET=STRAVA_CLIENT_SECRET:latest,FLASK_SECRET_KEY=FLASK_SECRET_KEY:latest,SYNC_TOKEN=SYNC_TOKEN:latest,DATABASE_URL=DATABASE_URL:latest
```

`--allow-unauthenticated` is required because the leaderboard page and OAuth
callback must be publicly reachable; `/internal/sync` protects itself with
the `SYNC_TOKEN` bearer check instead of relying on Cloud Run's IAM (which is
service-wide, not per-route).

When it finishes, note the **Service URL** it prints, e.g.
`https://strava-km-tracker-xxxxxxxx-uc.a.run.app`.

## 8. Point the redirect URI at the real URL

1. In the Strava API settings, set **Authorization Callback Domain** to the
   host from your Service URL (e.g. `strava-km-tracker-xxxxxxxx-uc.a.run.app`,
   no `https://` prefix).
2. Update the redirect URI env var and redeploy just that change:

   ```bash
   gcloud run services update strava-km-tracker \
     --region us-central1 \
     --update-env-vars STRAVA_REDIRECT_URI=https://strava-km-tracker-xxxxxxxx-uc.a.run.app/auth/strava/callback
   ```

## 9. Create the Cloud Scheduler job

This replaces the in-process 30-minute refresh (disabled automatically when
`APP_ENV=production`, see [run.py](run.py)):

```bash
gcloud scheduler jobs create http strava-km-sync \
  --location=us-central1 \
  --schedule="*/30 * * * *" \
  --uri="https://strava-km-tracker-xxxxxxxx-uc.a.run.app/internal/sync" \
  --http-method=POST \
  --headers="Authorization=Bearer the-sync-token" \
  --attempt-deadline=300s
```

Use the same `SYNC_TOKEN` value you stored in Secret Manager in step 5.

## 10. Verify

- Visit the Service URL, click "Connect your Strava account", and confirm the
  full OAuth round-trip and leaderboard row work.
- Trigger the sync job once manually to confirm it's wired correctly:

  ```bash
  gcloud scheduler jobs run strava-km-sync --location=us-central1
  ```
- `gcloud run services logs read strava-km-tracker --region us-central1`
  should show `Strava sync complete: N synced, 0 errored` after that run.

## Redeploying after code changes

```bash
gcloud run deploy strava-km-tracker --source . --region us-central1
```

Env vars and secrets already set on the service persist across redeploys —
you only need `--set-env-vars`/`--set-secrets` again if a value changes.

## Redeploying from GitHub Actions instead

If you'd rather trigger redeploys from GitHub than run `gcloud` locally every
time, this repo includes `.github/workflows/deploy.yml`, a manually-triggered
("Run workflow" button in the Actions tab) job that runs the same `gcloud run
deploy` command shown above. It authenticates using Workload Identity
Federation — no long-lived Google credential is stored in GitHub.

This is a one-time setup, run locally with `gcloud` (already authenticated
from step 3):

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# 1. A workload identity pool + OIDC provider that trusts GitHub Actions,
#    restricted to this repo only.
gcloud iam workload-identity-pools create "github-pool" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='archonza/stava-play-1'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 2. A dedicated deployer service account with just enough permission to
#    build (via Cloud Build) and deploy to Cloud Run.
gcloud iam service-accounts create "github-deployer" \
  --project="$PROJECT_ID" \
  --display-name="GitHub Actions Cloud Run deployer"

DEPLOYER_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor roles/storage.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${DEPLOYER_SA}" \
    --role="$ROLE"
done

# 3. Let only this repo impersonate that service account.
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/archonza/stava-play-1"

# 4. Print the value you need for the GCP_WIF_PROVIDER secret below.
gcloud iam workload-identity-pools providers describe "github-provider" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
```

Then, in the GitHub repo (Settings → Secrets and variables → Actions →
"New repository secret"), add three secrets:

| Secret name | Value |
|---|---|
| `GCP_PROJECT_ID` | `$PROJECT_ID` from above |
| `GCP_WIF_PROVIDER` | the full resource name printed by the last command |
| `GCP_SERVICE_ACCOUNT` | `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |

After that, go to the repo's **Actions** tab → **Deploy to Cloud Run** →
**Run workflow** any time you want to push the latest commit live.
