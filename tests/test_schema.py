"""Tests for the SQLite schema DDL and migrate() upgrade paths.

All tests use in-memory or tmp-path SQLite databases — no disk state survives.
"""

from __future__ import annotations

import sqlite3

from nidozo.db.schema import SCHEMA_VERSION, migrate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_conn() -> sqlite3.Connection:
    """In-memory SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT version FROM schema_version").fetchone()["version"]


# ---------------------------------------------------------------------------
# Fresh install tests
# ---------------------------------------------------------------------------

def test_fresh_install_creates_all_tables() -> None:
    """migrate() on a brand-new DB creates all required tables."""
    conn = _fresh_conn()
    migrate(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    for expected in ("models", "elo_ratings", "battles", "turns", "elo_history", "tournaments"):
        assert expected in tables, f"Missing table: {expected}"


def test_fresh_install_schema_version_is_current() -> None:
    """After a fresh install, schema_version equals SCHEMA_VERSION."""
    conn = _fresh_conn()
    migrate(conn)

    assert _version(conn) == SCHEMA_VERSION


def test_fresh_install_creates_indexes() -> None:
    """All six performance indexes are created on a fresh install."""
    conn = _fresh_conn()
    migrate(conn)

    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }

    for idx in (
        "idx_turns_battle",
        "idx_battles_finished",
        "idx_battles_tournament",
        "idx_battles_p1",
        "idx_battles_p2",
        "idx_elohist_battle",
    ):
        assert idx in indexes, f"Missing index: {idx}"


# ---------------------------------------------------------------------------
# Idempotency test
# ---------------------------------------------------------------------------

def test_migrate_twice_is_idempotent() -> None:
    """Calling migrate() twice on the same DB raises no errors and version stays the same."""
    conn = _fresh_conn()
    migrate(conn)
    migrate(conn)  # should be a no-op

    assert _version(conn) == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# v1 → current migration
# ---------------------------------------------------------------------------

def _build_v1_db() -> sqlite3.Connection:
    """Create a minimal v1 schema (no state_json, no tournaments, no indexes)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1);

        CREATE TABLE models (
            id             INTEGER PRIMARY KEY,
            provider       TEXT    NOT NULL,
            model_name     TEXT    NOT NULL,
            prompt_version TEXT    NOT NULL DEFAULT 'v1',
            created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

        CREATE TABLE elo_ratings (
            model_id   INTEGER PRIMARY KEY REFERENCES models(id),
            rating     REAL    NOT NULL DEFAULT 1000.0,
            games      INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

        CREATE TABLE battles (
            id              INTEGER PRIMARY KEY,
            battle_tag      TEXT    NOT NULL UNIQUE,
            format          TEXT    NOT NULL,
            p1_model_id     INTEGER NOT NULL REFERENCES models(id),
            p2_model_id     INTEGER NOT NULL REFERENCES models(id),
            winner          INTEGER,
            total_turns     INTEGER,
            started_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            finished_at     TEXT
        );

        CREATE TABLE elo_history (
            id            INTEGER PRIMARY KEY,
            battle_id     INTEGER NOT NULL REFERENCES battles(id),
            model_id      INTEGER NOT NULL REFERENCES models(id),
            rating_before REAL    NOT NULL,
            rating_after  REAL    NOT NULL,
            delta         REAL    NOT NULL
        );

        CREATE TABLE turns (
            id            INTEGER PRIMARY KEY,
            battle_id     INTEGER NOT NULL REFERENCES battles(id),
            turn_number   INTEGER NOT NULL,
            player_role   TEXT    NOT NULL,
            prompt_version TEXT   NOT NULL,
            action_chosen TEXT,
            parse_success INTEGER NOT NULL DEFAULT 1,
            llm_response  TEXT
        );
    """)
    return conn


def test_migrate_from_v1_to_current() -> None:
    """migrate() on a v1 DB upgrades to SCHEMA_VERSION without errors."""
    conn = _build_v1_db()
    migrate(conn)

    assert _version(conn) == SCHEMA_VERSION


def test_migrate_from_v1_adds_state_json_column() -> None:
    """After migration, turns table has the state_json column (added in v2)."""
    conn = _build_v1_db()
    migrate(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(turns)").fetchall()}
    assert "state_json" in cols


def test_migrate_from_v1_adds_tournaments_table() -> None:
    """After migration, tournaments table exists (added in v3)."""
    conn = _build_v1_db()
    migrate(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "tournaments" in tables


def test_migrate_from_v1_adds_indexes() -> None:
    """After migration, all six indexes are present (added in v4)."""
    conn = _build_v1_db()
    migrate(conn)

    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }

    for idx in (
        "idx_turns_battle",
        "idx_battles_finished",
        "idx_battles_tournament",
        "idx_battles_p1",
        "idx_battles_p2",
        "idx_elohist_battle",
    ):
        assert idx in indexes, f"Missing index after migration from v1: {idx}"


# ---------------------------------------------------------------------------
# v3 → v4 migration (only indexes added)
# ---------------------------------------------------------------------------

def _build_v3_db() -> sqlite3.Connection:
    """Build a v3 DB (all tables and columns, but no indexes)."""
    conn = _build_v1_db()
    # Apply v2 changes
    conn.execute("ALTER TABLE turns ADD COLUMN state_json TEXT")
    # Apply v3 changes
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id             INTEGER PRIMARY KEY,
            players        TEXT    NOT NULL,
            rounds         INTEGER NOT NULL DEFAULT 1,
            prompt_version TEXT    NOT NULL DEFAULT 'v2',
            total_battles  INTEGER NOT NULL DEFAULT 0,
            status         TEXT    NOT NULL DEFAULT 'running',
            created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            finished_at    TEXT
        );
    """)
    try:
        conn.execute("ALTER TABLE battles ADD COLUMN tournament_id INTEGER REFERENCES tournaments(id)")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE battles ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    except Exception:
        pass
    conn.execute("UPDATE schema_version SET version=3")
    conn.commit()
    return conn


def test_migrate_from_v3_to_v4_adds_indexes() -> None:
    """migrate() on a v3 DB adds all six indexes and bumps version to 4."""
    conn = _build_v3_db()
    assert _version(conn) == 3

    migrate(conn)

    assert _version(conn) == SCHEMA_VERSION

    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for idx in (
        "idx_turns_battle",
        "idx_battles_finished",
        "idx_battles_tournament",
        "idx_battles_p1",
        "idx_battles_p2",
        "idx_elohist_battle",
    ):
        assert idx in indexes, f"Missing index after v3→v4 migration: {idx}"


def test_migrate_from_v3_preserves_existing_data() -> None:
    """migrate() does not destroy existing rows during v3→v4 upgrade."""
    conn = _build_v3_db()
    # Insert a model row before migration
    conn.execute(
        "INSERT INTO models (provider, model_name, prompt_version) VALUES ('random','random','v1')"
    )
    conn.commit()

    migrate(conn)

    count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# New coverage tests — missing lines
# ---------------------------------------------------------------------------

def test_migrate_idempotent_tables_already_exist() -> None:
    """Running migrate() on an already-migrated DB is safe (CREATE TABLE IF NOT EXISTS)."""
    conn = _fresh_conn()
    migrate(conn)
    # Second call should not raise
    migrate(conn)
    assert _version(conn) == SCHEMA_VERSION


def test_migrate_idempotent_indexes_already_exist() -> None:
    """CREATE INDEX IF NOT EXISTS makes index creation idempotent."""
    conn = _fresh_conn()
    migrate(conn)
    # Manually create an index that would normally be in the migration
    # Then migrate again — should not raise
    migrate(conn)
    indexes = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    assert "idx_turns_battle" in indexes


def test_migrate_from_v6_adds_bracket_columns() -> None:
    """Migrating from v6 adds tournament_format and bracket_state columns."""
    # Fresh install gives us full schema; downgrade to v6
    conn = _fresh_conn()
    migrate(conn)
    # Simulate a v6 DB by rolling back the bracket columns
    conn.execute("UPDATE schema_version SET version=6")
    try:
        conn.execute("ALTER TABLE tournaments DROP COLUMN tournament_format")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tournaments DROP COLUMN bracket_state")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    migrate(conn)

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(tournaments)").fetchall()}
    assert "tournament_format" in cols
    assert "bracket_state" in cols


def test_migrate_v1_state_json_already_exists_no_error() -> None:
    """Lines 166-167: OperationalError is silenced when state_json already exists.

    Build a v1 DB but pre-add state_json to turns, leave version=1.
    Calling migrate() must not raise even though ALTER TABLE would fail.
    """
    conn = _build_v1_db()
    # Pre-add the column that v2 migration would add
    conn.execute("ALTER TABLE turns ADD COLUMN state_json TEXT")
    conn.commit()
    # migrate() should detect version < 2, try ALTER TABLE, catch OperationalError, and continue
    migrate(conn)
    assert _version(conn) == SCHEMA_VERSION


def test_migrate_v2_battle_columns_already_exist_no_error() -> None:
    """Lines 194-195: OperationalError is silenced when tournament_id/status already exist.

    Build a v1 DB, apply v2 manually (add state_json, set version=2),
    pre-add tournament_id and status columns to battles, then call migrate().
    """
    conn = _build_v1_db()
    # Apply v2 changes manually
    conn.execute("ALTER TABLE turns ADD COLUMN state_json TEXT")
    conn.execute("UPDATE schema_version SET version=2")
    conn.commit()
    # Pre-add the columns that v3 migration would add — triggers OperationalError path
    conn.execute("ALTER TABLE battles ADD COLUMN tournament_id INTEGER")
    conn.execute("ALTER TABLE battles ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    conn.commit()
    # migrate() should detect version < 3, try ALTERs, catch OperationalErrors, and continue
    migrate(conn)
    assert _version(conn) == SCHEMA_VERSION


def test_migrate_v9_creates_unique_elo_history_index() -> None:
    """v9 migration replaces the non-unique idx_elohist_battle with a UNIQUE index."""
    conn = _fresh_conn()
    migrate(conn)
    # PRAGMA index_list returns (seq, name, unique, origin, partial)
    indexes = {
        (row[1], bool(row[2]))  # (name, is_unique)
        for row in conn.execute("PRAGMA index_list(elo_history)").fetchall()
    }
    assert ("idx_elohist_battle", True) in indexes, (
        "idx_elohist_battle should be a UNIQUE index after v9 migration"
    )


def test_migrate_v9_idempotent() -> None:
    """Running migrate() twice does not fail even though DROP INDEX fires on v9."""
    conn = _fresh_conn()
    migrate(conn)
    conn.execute("UPDATE schema_version SET version=8")
    conn.commit()
    migrate(conn)  # re-runs v9 block — DROP INDEX IF EXISTS + CREATE UNIQUE INDEX
    assert _version(conn) == SCHEMA_VERSION


def test_finish_battle_idempotent_elo(tmp_path) -> None:
    """Calling finish_battle twice for the same battle must not apply ELO twice."""
    from nidozo.db.store import BattleStore

    store = BattleStore(db_path=tmp_path / "test.db")
    conn = store._conn

    p1 = store.get_or_create_model("random", "bot1", "v1")
    p2 = store.get_or_create_model("random", "bot2", "v1")
    bid = store.create_battle("tag-idem", "gen3randombattle", p1, p2)

    store.finish_battle(bid, winner=1, total_turns=10)
    r1_after_first = conn.execute(
        "SELECT rating FROM elo_ratings WHERE model_id=?", (p1,)
    ).fetchone()["rating"]

    # Second call — should be a no-op
    store.finish_battle(bid, winner=1, total_turns=10)
    r1_after_second = conn.execute(
        "SELECT rating FROM elo_ratings WHERE model_id=?", (p1,)
    ).fetchone()["rating"]

    assert r1_after_first == r1_after_second, (
        "ELO changed on second finish_battle call — double-apply regression"
    )

    history_rows = conn.execute(
        "SELECT COUNT(*) FROM elo_history WHERE battle_id=? AND model_id=?", (bid, p1)
    ).fetchone()[0]
    assert history_rows == 1, "elo_history should have exactly one row per (battle, model)"


def test_migration_v9_to_v10_adds_seasons_table(tmp_path) -> None:
    """A v9 database gains the seasons table and season_id on battles after migrate()."""
    import sqlite3

    from nidozo.db.schema import migrate

    db_path = tmp_path / "v9.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Replicate a v9 schema (tables without seasons / season_id)
    conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (9);
        CREATE TABLE models (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE battles (
            id INTEGER PRIMARY KEY,
            battle_tag TEXT NOT NULL UNIQUE,
            format TEXT NOT NULL,
            p1_model_id INTEGER NOT NULL REFERENCES models(id),
            p2_model_id INTEGER NOT NULL REFERENCES models(id),
            winner INTEGER,
            total_turns INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            finished_at TEXT
        );
        CREATE TABLE elo_ratings (
            model_id INTEGER PRIMARY KEY REFERENCES models(id),
            rating REAL NOT NULL DEFAULT 1000.0,
            games INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE elo_history (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL REFERENCES battles(id),
            model_id INTEGER NOT NULL REFERENCES models(id),
            rating_before REAL NOT NULL,
            rating_after REAL NOT NULL,
            delta REAL NOT NULL
        );
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL REFERENCES battles(id),
            turn_number INTEGER NOT NULL,
            player_role TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            action_chosen TEXT,
            parse_success INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE tournaments (
            id INTEGER PRIMARY KEY,
            players TEXT NOT NULL,
            rounds INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE lessons (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            battle_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            tier TEXT NOT NULL,
            format TEXT NOT NULL,
            pokemon TEXT NOT NULL,
            team_string TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE draft_sessions (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            tier TEXT NOT NULL,
            pool_size INTEGER NOT NULL,
            picked TEXT NOT NULL,
            prompt_version TEXT NOT NULL DEFAULT 'v3',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE UNIQUE INDEX idx_elohist_battle ON elo_history(battle_id, model_id);
    """)
    conn.commit()

    migrate(conn)
    conn.close()

    # Re-open and verify
    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row

    # seasons table must exist
    tables = {r[0] for r in conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "seasons" in tables, "seasons table not created by v10 migration"

    # season_id column must exist on battles
    cols = {r[1] for r in conn2.execute("PRAGMA table_info(battles)").fetchall()}
    assert "season_id" in cols, "season_id column not added to battles by v10 migration"

    # schema version must be 10
    version = conn2.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 10

    conn2.close()
