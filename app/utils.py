from datetime import datetime, timedelta, timezone

SAST = timezone(timedelta(hours=2))


def today_sast():
    """Return today's date in SAST as an ISO string (YYYY-MM-DD)."""
    return datetime.now(SAST).date().isoformat()
