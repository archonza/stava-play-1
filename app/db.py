import psycopg
from psycopg.rows import dict_row
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
    athlete_id       INTEGER PRIMARY KEY,
    firstname        TEXT NOT NULL,
    lastname         TEXT NOT NULL,
    access_token     TEXT NOT NULL,
    refresh_token    TEXT NOT NULL,
    token_expires_at BIGINT NOT NULL,
    monthly_km       DOUBLE PRECISION NOT NULL DEFAULT 0,
    yearly_km        DOUBLE PRECISION NOT NULL DEFAULT 0,
    sex              TEXT,
    day_start_km     DOUBLE PRECISION NOT NULL DEFAULT 0,
    day_start_date   TEXT,
    last_synced_at   TEXT,
    last_sync_error  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

MIGRATIONS = [
    "ALTER TABLE athletes ADD COLUMN IF NOT EXISTS day_start_km DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE athletes ADD COLUMN IF NOT EXISTS day_start_date TEXT",
    "ALTER TABLE athletes ADD COLUMN IF NOT EXISTS yearly_km DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE athletes ADD COLUMN IF NOT EXISTS sex TEXT",
]


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        conn = psycopg.connect(app.config["DATABASE_URL"])
        conn.execute(SCHEMA)
        for migration in MIGRATIONS:
            conn.execute(migration)
        conn.commit()
        conn.close()
    app.teardown_appcontext(close_db)


def upsert_athlete(athlete_id, firstname, lastname, access_token, refresh_token, expires_at, sex=None):
    db = get_db()
    db.execute(
        """
        INSERT INTO athletes (athlete_id, firstname, lastname, access_token, refresh_token, token_expires_at, sex)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (athlete_id) DO UPDATE SET
            firstname = excluded.firstname,
            lastname = excluded.lastname,
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_expires_at = excluded.token_expires_at,
            sex = excluded.sex,
            last_sync_error = NULL
        """,
        (athlete_id, firstname, lastname, access_token, refresh_token, expires_at, sex),
    )
    db.commit()


def update_athlete_tokens(athlete_id, access_token, refresh_token, expires_at):
    db = get_db()
    db.execute(
        """
        UPDATE athletes
        SET access_token = %s, refresh_token = %s, token_expires_at = %s
        WHERE athlete_id = %s
        """,
        (access_token, refresh_token, expires_at, athlete_id),
    )
    db.commit()


def update_athlete_totals(athlete_id, monthly_km, yearly_km, synced_at, today, error=None):
    """Update an athlete's monthly/yearly totals and roll over their "start of
    day" baseline whenever `today` differs from the stored day_start_date, so
    `monthly_km > day_start_km` reflects whether they've run today.
    """
    db = get_db()
    db.execute(
        """
        UPDATE athletes
        SET
            day_start_km = CASE
                WHEN day_start_date IS DISTINCT FROM %(today)s
                    THEN CASE WHEN %(km)s < monthly_km THEN 0 ELSE monthly_km END
                ELSE day_start_km
            END,
            day_start_date = %(today)s,
            monthly_km = %(km)s,
            yearly_km = %(yearly_km)s,
            last_synced_at = %(synced_at)s,
            last_sync_error = %(error)s
        WHERE athlete_id = %(athlete_id)s
        """,
        {
            "today": today,
            "km": monthly_km,
            "yearly_km": yearly_km,
            "synced_at": synced_at,
            "error": error,
            "athlete_id": athlete_id,
        },
    )
    db.commit()


def record_sync_error(athlete_id, error):
    db = get_db()
    db.execute(
        "UPDATE athletes SET last_sync_error = %s WHERE athlete_id = %s",
        (error, athlete_id),
    )
    db.commit()


def get_all_athletes():
    db = get_db()
    return db.execute(
        """
        SELECT *, (monthly_km > day_start_km) AS ran_today
        FROM athletes
        ORDER BY monthly_km DESC
        """
    ).fetchall()


def get_athlete(athlete_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM athletes WHERE athlete_id = %s", (athlete_id,)
    ).fetchone()
