import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "FLASK_SECRET_KEY")


class Config:
    STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
    STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
    STRAVA_REDIRECT_URI = os.environ.get(
        "STRAVA_REDIRECT_URI", "http://localhost:5000/auth/strava/callback"
    )
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    REFRESH_INTERVAL_MINUTES = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))


def validate_config():
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in the values."
        )
