import logging
import os
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app import db, strava
from app.utils import today_sast

logger = logging.getLogger(__name__)


def refresh_all_athletes(app):
    with app.app_context():
        athletes = db.get_all_athletes()
        synced = 0
        errored = 0
        today = today_sast()

        for athlete in athletes:
            try:
                access_token = strava.get_valid_access_token(athlete)
                km = strava.fetch_monthly_running_km(access_token)
                db.update_athlete_totals(
                    athlete["athlete_id"],
                    km,
                    datetime.now(timezone.utc).isoformat(),
                    today,
                    error=None,
                )
                synced += 1
            except strava.StravaAuthError:
                db.record_sync_error(
                    athlete["athlete_id"],
                    "Strava authorization revoked — please reconnect.",
                )
                errored += 1
            except strava.StravaAPIError as exc:
                db.record_sync_error(athlete["athlete_id"], str(exc))
                errored += 1
                if "429" in str(exc):
                    time.sleep(2)
            except Exception as exc:  # noqa: BLE001 - safety net so one athlete never kills the job
                logger.exception("Unexpected error syncing athlete %s", athlete["athlete_id"])
                db.record_sync_error(athlete["athlete_id"], str(exc))
                errored += 1

        logger.info("Strava sync complete: %d synced, %d errored", synced, errored)


def start_scheduler(app, debug=False):
    # Flask's debug reloader re-executes this script in a parent "watcher"
    # process and a child "reloader" process. Only start the scheduler in
    # the child (WERKZEUG_RUN_MAIN=true) to avoid running it twice.
    if debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: refresh_all_athletes(app),
        "interval",
        minutes=app.config["REFRESH_INTERVAL_MINUTES"],
        next_run_time=datetime.now(),
    )
    scheduler.start()
    return scheduler
