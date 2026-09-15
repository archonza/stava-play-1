import calendar
from datetime import datetime, timedelta, timezone

SAST = timezone(timedelta(hours=2))


def today_sast():
    """Return today's date in SAST as an ISO string (YYYY-MM-DD)."""
    return datetime.now(SAST).date().isoformat()


def year_progress_sast():
    """Return (day_of_year, days_in_year) for 'today' in SAST."""
    now = datetime.now(SAST)
    days_in_year = 366 if calendar.isleap(now.year) else 365
    return now.timetuple().tm_yday, days_in_year


def track_fraction(yearly_km, leader_km, day_of_year, days_in_year):
    """Position (0..1) along a yearly progress track: the leader sits exactly
    on today's day-of-year mark, everyone else behind, scaled by how far
    behind in km they are relative to the leader.
    """
    if leader_km <= 0 or yearly_km <= 0:
        return 0.0
    return (day_of_year / days_in_year) * (yearly_km / leader_km)
