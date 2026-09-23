"""SQLite data layer.

Schema philosophy: events are the ONLY thing recorded about participants'
behaviour, and they carry no free-form payload — see safety.py for the
storage-level guard that enforces this.
"""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    template_key      TEXT NOT NULL,
    consent_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (consent_confirmed IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id       INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    email             TEXT NOT NULL,
    consent_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (consent_confirmed IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    campaign_id    INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    event_type     TEXT NOT NULL CHECK (event_type IN ('clicked', 'submitted')),
    user_agent     TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign_id);
CREATE INDEX IF NOT EXISTS idx_participants_campaign ON participants(campaign_id);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.config.setdefault("DATABASE", "phishguard.db")
    app.teardown_appcontext(close_db)
    with app.app_context():
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def create_campaign(name: str, template_key: str, consent: bool) -> int:
    if not consent:
        raise ValueError("Campaign creation requires explicit consent confirmation.")
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO campaigns (name, template_key, consent_confirmed) VALUES (?, ?, 1)",
        (name, template_key),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_campaigns() -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM campaigns ORDER BY id DESC"
    ).fetchall()


def get_campaign(campaign_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()


def create_participant(campaign_id: int, name: str, email: str, consent: bool) -> int:
    if not consent:
        raise ValueError("Participant creation requires explicit consent confirmation.")
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO participants (campaign_id, name, email, consent_confirmed)"
        " VALUES (?, ?, ?, 1)",
        (campaign_id, name, email),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_participants(campaign_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM participants WHERE campaign_id = ? ORDER BY id",
        (campaign_id,),
    ).fetchall()


def get_participant(participant_id: int, campaign_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT * FROM participants WHERE id = ? AND campaign_id = ?",
        (participant_id, campaign_id),
    ).fetchone()


def record_event(participant_id: int, campaign_id: int, event_type: str,
                 user_agent: str | None = None) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO events (participant_id, campaign_id, event_type, user_agent)"
        " VALUES (?, ?, ?, ?)",
        (participant_id, campaign_id, event_type, user_agent),
    )
    conn.commit()


def campaign_stats(campaign_id: int) -> dict:
    conn = get_db()
    participants = conn.execute(
        "SELECT COUNT(*) AS n FROM participants WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()["n"]
    clicks = conn.execute(
        "SELECT COUNT(DISTINCT participant_id) AS n FROM events"
        " WHERE campaign_id = ? AND event_type = 'clicked'",
        (campaign_id,),
    ).fetchone()["n"]
    submits = conn.execute(
        "SELECT COUNT(DISTINCT participant_id) AS n FROM events"
        " WHERE campaign_id = ? AND event_type = 'submitted'",
        (campaign_id,),
    ).fetchone()["n"]
    click_rate = (clicks / participants * 100) if participants else 0.0
    submit_rate = (submits / participants * 100) if participants else 0.0
    return {
        "participants": participants,
        "clicks": clicks,
        "submissions": submits,
        "click_rate": round(click_rate, 1),
        "submit_rate": round(submit_rate, 1),
    }


def participant_events(campaign_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT p.name, p.email, e.event_type, e.created_at"
        " FROM events e JOIN participants p ON p.id = e.participant_id"
        " WHERE e.campaign_id = ? ORDER BY e.id DESC",
        (campaign_id,),
    ).fetchall()
