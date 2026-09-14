import os

from app import create_app
from app.scheduler import start_scheduler

debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
app_env = os.environ.get("APP_ENV", "development")

app = create_app()
if app_env != "production":
    # In production (Cloud Run), the 30-min refresh is driven externally by
    # Cloud Scheduler hitting /internal/sync — an in-process scheduler would
    # either duplicate syncs across instances or never fire when idle/scaled
    # to zero.
    start_scheduler(app, debug=debug)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug)
