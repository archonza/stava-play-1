import logging
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db, strava

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    athletes = db.get_all_athletes()
    synced_timestamps = [a["last_synced_at"] for a in athletes if a["last_synced_at"]]
    last_updated = max(synced_timestamps) if synced_timestamps else None
    return render_template("index.html", athletes=athletes, last_updated=last_updated)


@bp.route("/auth/strava")
def auth_strava():
    return redirect(strava.build_authorize_url())


@bp.route("/auth/strava/callback")
def auth_strava_callback():
    if request.args.get("error"):
        flash("Strava authorization was cancelled.", "error")
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
            athlete["id"], km, datetime.now(timezone.utc).isoformat(), error=None
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
