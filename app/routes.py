import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from app import db, strava
from app.utils import SAST, today_sast

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

# Dev-only fixtures for eyeballing the "ran today" arrow without a real Strava
# account. Never shown when APP_ENV=production (see index() below), so this
# never reaches the deployed site.
FAKE_ATHLETES = [
    {
        "athlete_id": -1,
        "firstname": "Test",
        "lastname": "Ran-Today",
        "monthly_km": 42.5,
        "day_start_km": 30.0,
        "ran_today": True,
        "last_sync_error": None,
        "last_synced_at": None,
    },
    {
        "athlete_id": -2,
        "firstname": "Test",
        "lastname": "Rest-Day",
        "monthly_km": 15.0,
        "day_start_km": 15.0,
        "ran_today": False,
        "last_sync_error": None,
        "last_synced_at": None,
    },
]


def _parse_utc(iso_str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@bp.route("/")
def index():
    athletes = db.get_all_athletes()
    synced_timestamps = [a["last_synced_at"] for a in athletes if a["last_synced_at"]]
    last_updated_raw = max(synced_timestamps) if synced_timestamps else None

    last_updated_display = None
    minutes_until_next = None
    if last_updated_raw:
        last_updated_utc = _parse_utc(last_updated_raw)
        last_updated_display = last_updated_utc.astimezone(SAST).strftime("%d %b %Y, %H:%M SAST")

        next_update_utc = last_updated_utc + timedelta(minutes=current_app.config["REFRESH_INTERVAL_MINUTES"])
        remaining_minutes = (next_update_utc - datetime.now(timezone.utc)).total_seconds() / 60
        minutes_until_next = max(0, round(remaining_minutes))

    display_athletes = athletes
    if current_app.config["APP_ENV"] != "production":
        display_athletes = sorted(
            list(athletes) + FAKE_ATHLETES, key=lambda a: a["monthly_km"], reverse=True
        )

    return render_template(
        "index.html",
        athletes=display_athletes,
        last_updated_display=last_updated_display,
        minutes_until_next=minutes_until_next,
    )


@bp.route("/auth/strava")
def auth_strava():
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    return redirect(strava.build_authorize_url(state))


@bp.route("/auth/strava/callback")
def auth_strava_callback():
    if request.args.get("error"):
        session.pop("oauth_state", None)
        flash("Strava authorization was cancelled.", "error")
        return redirect(url_for("main.index"))

    expected_state = session.pop("oauth_state", None)
    if not expected_state or not hmac.compare_digest(request.args.get("state", ""), expected_state):
        flash("Invalid or expired authorization request. Please try connecting again.", "error")
        return redirect(url_for("main.index"))

    code = request.args.get("code")
    if not code:
        flash("No authorization code received from Strava.", "error")
        return redirect(url_for("main.index"))

    try:
        token_data = strava.exchange_code_for_token(code)
    except (strava.StravaAuthError, strava.StravaAPIError) as exc:
        flash(f"Could not connect to Strava: {exc}", "error")
        return redirect(url_for("main.index"))

    athlete = token_data["athlete"]
    db.upsert_athlete(
        athlete["id"],
        athlete.get("firstname") or "",
        athlete.get("lastname") or "",
        token_data["access_token"],
        token_data["refresh_token"],
        token_data["expires_at"],
    )

    try:
        km = strava.fetch_monthly_running_km(token_data["access_token"])
        db.update_athlete_totals(
            athlete["id"],
            km,
            datetime.now(timezone.utc).isoformat(),
            today_sast(),
            error=None,
        )
    except (strava.StravaAuthError, strava.StravaAPIError) as exc:
        logger.warning("Initial fetch failed for athlete %s: %s", athlete["id"], exc)
        db.record_sync_error(athlete["id"], str(exc))

    flash(
        f"Welcome, {athlete.get('firstname', 'athlete')}! "
        "Your stats will update automatically every 30 minutes.",
        "success",
    )
    return redirect(url_for("main.index"))


@bp.route("/internal/sync", methods=["POST"])
def internal_sync():
    expected = current_app.config["SYNC_TOKEN"]
    auth_header = request.headers.get("Authorization", "")
    provided = auth_header[len("Bearer "):] if auth_header.startswith("Bearer ") else ""
    if not expected or not hmac.compare_digest(provided, expected):
        abort(401)

    from app.scheduler import refresh_all_athletes

    refresh_all_athletes(current_app._get_current_object())
    return {"status": "ok"}, 200
