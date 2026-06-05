"""SQLite schema — all CREATE TABLE statements and the migrate() entry point."""

import sqlite3

SCHEMA_VERSION = 1

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- One row per distinct model+prompt configuration
CREATE TABLE IF NOT EXISTS models (
    id             INTEGER PRIMARY KEY,
    provider       TEXT    NOT NULL,  -- "anthropic" | "openai" | "lmstudio" | "random"
    model_name     TEXT    NOT NULL,
    prompt_version TEXT    NOT NULL DEFAULT 'v1',
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Current ELO rating per model (single live row per model)
CREATE TABLE IF NOT EXISTS elo_ratings (
    model_id   INTEGER PRIMARY KEY REFERENCES models(id),
    rating     REAL    NOT NULL DEFAULT 1000.0,
    games      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- One row per completed battle
CREATE TABLE IF NOT EXISTS battles (
    id           INTEGER PRIMARY KEY,
    battle_tag   TEXT    NOT NULL UNIQUE,
    format       TEXT    NOT NULL,
    p1_model_id  INTEGER NOT NULL REFERENCES models(id),
    p2_model_id  INTEGER NOT NULL REFERENCES models(id),
    winner       INTEGER,           -- 1=p1, 2=p2, NULL=tie
    total_turns  INTEGER,
    started_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at  TEXT
);

-- ELO delta per model per battle (for history / audit)
CREATE TABLE IF NOT EXISTS elo_history (
    id            INTEGER PRIMARY KEY,
    battle_id     INTEGER NOT NULL REFERENCES battles(id),
    model_id      INTEGER NOT NULL REFERENCES models(id),
    rating_before REAL    NOT NULL,
    rating_after  REAL    NOT NULL,
    delta         REAL    NOT NULL
);

-- Per-turn log: action chosen, parse outcome, raw LLM response
CREATE TABLE IF NOT EXISTS turns (
    id            INTEGER PRIMARY KEY,
    battle_id     INTEGER NOT NULL REFERENCES battles(id),
    turn_number   INTEGER NOT NULL,
    player_role   TEXT    NOT NULL,   -- "p1" | "p2"
    prompt_version TEXT   NOT NULL,
    action_chosen TEXT,               -- e.g. "move 2" or "switch 1"
    parse_success INTEGER NOT NULL DEFAULT 1,  -- 0=fell back to random
    llm_response  TEXT                         -- full raw response (may be large)
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist. Idempotent."""
    conn.executescript(_DDL)
    cur = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
