"""SQLite schema — all CREATE TABLE statements and the migrate() entry point."""

import sqlite3

SCHEMA_VERSION = 3

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

-- Round-robin or bracket tournament sessions
CREATE TABLE IF NOT EXISTS tournaments (
    id             INTEGER PRIMARY KEY,
    players        TEXT    NOT NULL,  -- JSON array of {provider, model_name}
    rounds         INTEGER NOT NULL DEFAULT 1,
    prompt_version TEXT    NOT NULL DEFAULT 'v2',
    total_battles  INTEGER NOT NULL DEFAULT 0,
    status         TEXT    NOT NULL DEFAULT 'running',  -- running|completed|cancelled
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at    TEXT
);

-- One row per completed battle
CREATE TABLE IF NOT EXISTS battles (
    id              INTEGER PRIMARY KEY,
    battle_tag      TEXT    NOT NULL UNIQUE,
    format          TEXT    NOT NULL,
    p1_model_id     INTEGER NOT NULL REFERENCES models(id),
    p2_model_id     INTEGER NOT NULL REFERENCES models(id),
    tournament_id   INTEGER REFERENCES tournaments(id),   -- NULL for standalone battles
    winner          INTEGER,           -- 1=p1, 2=p2, NULL=tie
    total_turns     INTEGER,
    status          TEXT    NOT NULL DEFAULT 'pending',   -- pending|running|completed|cancelled
    started_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at     TEXT
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

-- Per-turn log: action chosen, parse outcome, raw LLM response, and full battle state
CREATE TABLE IF NOT EXISTS turns (
    id            INTEGER PRIMARY KEY,
    battle_id     INTEGER NOT NULL REFERENCES battles(id),
    turn_number   INTEGER NOT NULL,
    player_role   TEXT    NOT NULL,   -- "p1" | "p2"
    prompt_version TEXT   NOT NULL,
    action_chosen TEXT,               -- e.g. "move 2" or "switch pikachu"
    parse_success INTEGER NOT NULL DEFAULT 1,  -- 0=fell back to random
    llm_response  TEXT,                        -- full raw response (may be large)
    state_json    TEXT                         -- serialized battle state at decision time (v2+)
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist and upgrade schema version."""
    conn.executescript(_DDL)

    cur = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        # Fresh install — schema already includes state_json column
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return

    cur = conn.execute("SELECT version FROM schema_version")
    version = cur.fetchone()[0]

    if version < 2:
        # Add state_json column to existing turns table
        try:
            conn.execute("ALTER TABLE turns ADD COLUMN state_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute("UPDATE schema_version SET version=2")
        conn.commit()

    if version < 3:
        # Add tournaments table and new columns to battles
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tournaments (
                    id             INTEGER PRIMARY KEY,
                    players        TEXT    NOT NULL,
                    rounds         INTEGER NOT NULL DEFAULT 1,
                    prompt_version TEXT    NOT NULL DEFAULT 'v2',
                    total_battles  INTEGER NOT NULL DEFAULT 0,
                    status         TEXT    NOT NULL DEFAULT 'running',
                    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                    finished_at    TEXT
                )
            """)
        except sqlite3.OperationalError:
            pass
        for col, defn in (
            ("tournament_id", "INTEGER REFERENCES tournaments(id)"),
            ("status", "TEXT NOT NULL DEFAULT 'completed'"),
        ):
            try:
                conn.execute(f"ALTER TABLE battles ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.execute("UPDATE schema_version SET version=3")
        conn.commit()
