import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from flask import current_app

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

RUNNING_TYPES = {"Run", "TrailRun"}
PER_PAGE = 200
TOKEN_REFRESH_BUFFER_SECONDS = 300


class StravaAuthError(Exception):
    """Raised when Strava rejects auth (revoked access, dead refresh token)."""


class StravaAPIError(Exception):
    """Raised for other non-2xx Strava responses or network errors."""


def build_authorize_url():
    params = {
        "client_id": current_app.config["STRAVA_CLIENT_ID"],
        "redirect_uri": current_app.config["STRAVA_REDIRECT_URI"],
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code):
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": current_app.config["STRAVA_CLIENT_ID"],
            "client_secret": current_app.config["STRAVA_CLIENT_SECRET"],
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if resp.status_code == 401:
        raise StravaAuthError(f"Strava rejected the authorization code: {resp.text}")
    if not resp.ok:
        raise StravaAPIError(f"Strava token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def refresh_access_token(refresh_token):
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": current_app.config["STRAVA_CLIENT_ID"],
            "client_secret": current_app.config["STRAVA_CLIENT_SECRET"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code == 401:
        raise StravaAuthError(f"Strava refresh token rejected: {resp.text}")
    if not resp.ok:
        raise StravaAPIError(f"Strava token refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()


def get_valid_access_token(athlete_row):
    from app import db

    now = int(time.time())
    if athlete_row["token_expires_at"] - now > TOKEN_REFRESH_BUFFER_SECONDS:
        return athlete_row["access_token"]

    data = refresh_access_token(athlete_row["refresh_token"])
    db.update_athlete_tokens(
        athlete_row["athlete_id"],
        data["access_token"],
        data["refresh_token"],
        data["expires_at"],
    )
    return data["access_token"]


def month_bounds_utc():
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp()), int(end.timestamp())


def fetch_monthly_running_km(access_token):
    after, before = month_bounds_utc()
    headers = {"Authorization": f"Bearer {access_token}"}
    total_meters = 0.0
    page = 1

    while True:
        try:
            resp = requests.get(
                ACTIVITIES_URL,
                headers=headers,
                params={"after": after, "before": before, "page": page, "per_page": PER_PAGE},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise StravaAPIError(f"Network error fetching activities: {exc}") from exc

        if resp.status_code == 401:
            raise StravaAuthError(f"Strava rejected the access token: {resp.text}")
        if resp.status_code == 429:
            raise StravaAPIError("Strava rate limit exceeded (429)")
        if not resp.ok:
            raise StravaAPIError(f"Strava activities fetch failed ({resp.status_code}): {resp.text}")

        activities = resp.json()
        if not activities:
            break

        for activity in activities:
            sport = activity.get("sport_type") or activity.get("type")
            if sport in RUNNING_TYPES:
                total_meters += activity.get("distance", 0) or 0

        if len(activities) < PER_PAGE:
            break
        page += 1

    return total_meters / 1000.0
