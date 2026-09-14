# Strava Group KM Tracker

A small Flask app that tracks a group of runners' total running distance for
the current calendar month, pulled from the real Strava API, and displays a
leaderboard web page. Each group member connects their own Strava account
once; the server then refreshes everyone's totals automatically every 30
minutes.

## Prerequisites

- Python 3.10+
- A Strava account for each group member (they authorize the app themselves)

## 1. Create a Strava API application

1. Go to https://www.strava.com/settings/api and create an app.
2. Set **Authorization Callback Domain** to `localhost` (Strava only stores
   the domain; the full callback path/port your app sends must still match
   what you configure below).
3. Copy the **Client ID** and **Client Secret**.

## 2. Set up the project

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:

```
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REDIRECT_URI=http://localhost:5000/auth/strava/callback
FLASK_SECRET_KEY=some-random-string
REFRESH_INTERVAL_MINUTES=30
```

## 3. Run

```bash
python run.py
```

Visit `http://localhost:5000`.

## 4. Usage

- Each group member clicks **"Connect your Strava account"** and authorizes
  the app once.
- Their monthly running total is fetched immediately on connect, and then
  refreshed automatically every `REFRESH_INTERVAL_MINUTES` (default 30)
  minutes in the background.
- The leaderboard sorts everyone by kilometers run this month, descending.

## Notes and limitations

- **Metric**: only `Run` and `TrailRun` activities count toward the total
  (rides, walks, swims, etc. are excluded).
- **Month boundaries** are computed in UTC, not each athlete's local
  timezone, for simplicity and consistency. An activity logged right around
  midnight near a month boundary could occasionally be attributed to the
  "wrong" calendar month for athletes far from UTC.
- **Rate limits**: Strava allows 100 requests/15 min and 1000/day. The
  background job syncs athletes sequentially, which is well within limits
  for a small group.
- **Revoked access**: if someone disconnects the app from their Strava
  settings, their row shows a "sync error" badge and keeps its last known
  total until they reconnect via the same "Connect your Strava account"
  link.
- **Data storage**: tokens and cached totals are stored locally in
  `instance/strava_tracker.db` (SQLite), which is not committed to git.
