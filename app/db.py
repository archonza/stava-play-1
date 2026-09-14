import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
    athlete_id       INTEGER PRIMARY KEY,
    firstname        TEXT NOT NULL,
    lastname         TEXT NOT NULL,
    access_token     TEXT NOT NULL,
    refresh_token    TEXT NOT NULL,
    token_expires_at INTEGER NOT NULL,
    monthly_km       REAL NOT NULL DEFAULT 0,
    last_synced_at   TEXT,
    last_sync_error  TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE_PATH"])
        db.executescript(SCHEMA)
        db.commit()
        db.close()
    app.teardown_appcontext(close_db)


def upsert_athlete(athlete_id, firstname, lastname, access_token, refresh_token, expires_at):
    db = get_db()
    db.execute(
        """
        INSERT INTO athletes (athlete_id, firstname, lastname, access_token, refresh_token, token_expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(athlete_id) DO UPDATE SET
            firstname = excluded.firstname,
            lastname = excluded.lastname,
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_expires_at = excluded.token_expires_at,
            last_sync_error = NULL
        """,
        (athlete_id, firstname, lastname, access_token, refresh_token, expires_at),
    )
    db.commit()


def update_athlete_tokens(athlete_id, access_token, refresh_token, expires_at):
    db = get_db()
    db.execute(
        """
        UPDATE athletes
        SET access_token = ?, refresh_token = ?, token_expires_at = ?
        WHERE athlete_id = ?
        """,
        (access_token, refresh_token, expires_at, athlete_id),
    )
    db.commit()


def update_athlete_totals(athlete_id, monthly_km, synced_at, error=None):
    db = get_db()
    db.execute(
        """
        UPDATE athletes
        SET monthly_km = ?, last_synced_at = ?, last_sync_error = ?
        WHERE athlete_id = ?
        """,
        (monthly_km, synced_at, error, athlete_id),
    )
    db.commit()


def record_sync_error(athlete_id, error):
    db = get_db()
    db.execute(
        "UPDATE athletes SET last_sync_error = ? WHERE athlete_id = ?",
        (error, athlete_id),
    )
    db.commit()


def get_all_athletes():
    db = get_db()
    return db.execute("SELECT * FROM athletes ORDER BY monthly_km DESC").fetchall()


def get_athlete(athlete_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM athletes WHERE athlete_id = ?", (athlete_id,)
    ).fetchone()
