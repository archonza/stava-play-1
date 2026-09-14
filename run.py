import os

from app import create_app
from app.scheduler import start_scheduler

debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

app = create_app()
start_scheduler(app, debug=debug)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug)
