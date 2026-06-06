"""BattleStore — all database read/write operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from nidozo.db.elo import DEFAULT_RATING, updated_ratings
from nidozo.db.schema import migrate

_DEFAULT_DB = Path(__file__).parent.parent.parent.parent / "nidozo.db"


class BattleStore:
    """SQLite store for battle results, ELO ratings, and turn logs.

    Uses a single connection with WAL mode.  **Not safe for concurrent
    writers** — serialise all writes through one instance.  Multi-step
    mutations (e.g. finish_battle + ELO update) are wrapped in
    ``with self._conn:`` for atomic commit/rollback.

    Args:
        db_path: Path to the SQLite file. Created if it doesn't exist.
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def get_or_create_model(
        self,
        provider: str,
        model_name: str,
        prompt_version: str = "v1",
    ) -> int:
        """Return the model id, creating the row if it doesn't exist."""
        cur = self._conn.execute(
            "SELECT id FROM models WHERE provider=? AND model_name=? AND prompt_version=?",
            (provider, model_name, prompt_version),
        )
        row = cur.fetchone()
        if row:
            return int(row["id"])

        cur = self._conn.execute(
            "INSERT INTO models (provider, model_name, prompt_version) VALUES (?,?,?)",
            (provider, model_name, prompt_version),
        )
        model_id = cur.lastrowid
        assert model_id is not None
        self._conn.execute(
            "INSERT INTO elo_ratings (model_id, rating, games) VALUES (?,?,0)",
            (model_id, DEFAULT_RATING),
        )
        self._conn.commit()
        return model_id

    # ------------------------------------------------------------------
    # Battles
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Tournaments
    # ------------------------------------------------------------------

    def create_tournament(
        self,
        players: list[dict[str, Any]],
        rounds: int,
        prompt_version: str,
        total_battles: int,
    ) -> int:
        """Insert a tournament row and return its id."""
        cur = self._conn.execute(
            """INSERT INTO tournaments (players, rounds, prompt_version, total_battles)
               VALUES (?,?,?,?)""",
            (json.dumps(players), rounds, prompt_version, total_battles),
        )
        self._conn.commit()
        row_id = cur.lastrowid
        assert row_id is not None
        return row_id

    def finish_tournament(self, tournament_id: int, status: str = "completed") -> None:
        self._conn.execute(
            """UPDATE tournaments SET status=?,
               finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE id=?""",
            (status, tournament_id),
        )
        self._conn.commit()

    def get_tournament(self, tournament_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM tournaments WHERE id=?", (tournament_id,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Battles
    # ------------------------------------------------------------------

    def get_battle(self, battle_id: int) -> dict[str, Any] | None:
        """Return a single battle row by id, or None if not found."""
        row = self._conn.execute(
            """SELECT b.id, b.battle_tag, b.format, b.winner, b.total_turns,
                      b.status, b.started_at, b.finished_at, b.tournament_id,
                      p1.provider||'/'||p1.model_name AS p1,
                      p2.provider||'/'||p2.model_name AS p2
               FROM battles b
               JOIN models p1 ON p1.id = b.p1_model_id
               JOIN models p2 ON p2.id = b.p2_model_id
               WHERE b.id=?""",
            (battle_id,),
        ).fetchone()
        return dict(row) if row else None

    def create_battle(
        self,
        battle_tag: str,
        format: str,
        p1_model_id: int,
        p2_model_id: int,
        tournament_id: int | None = None,
    ) -> int:
        """Insert a battle row and return its id."""
        cur = self._conn.execute(
            """INSERT INTO battles (battle_tag, format, p1_model_id, p2_model_id, tournament_id, status)
               VALUES (?,?,?,?,?,'pending')""",
            (battle_tag, format, p1_model_id, p2_model_id, tournament_id),
        )
        self._conn.commit()
        row_id = cur.lastrowid
        assert row_id is not None
        return row_id

    def set_battle_status(self, battle_id: int, status: str) -> None:
        """Update the status field of a battle (pending/running/completed/cancelled/failed)."""
        self._conn.execute(
            "UPDATE battles SET status=? WHERE id=?", (status, battle_id)
        )
        self._conn.commit()

    def cancel_battle(self, battle_id: int) -> bool:
        """Mark a battle as cancelled. Returns False if already finished."""
        row = self._conn.execute(
            "SELECT status FROM battles WHERE id=?", (battle_id,)
        ).fetchone()
        if not row or row["status"] in ("completed", "cancelled", "failed"):
            return False
        self._conn.execute(
            """UPDATE battles SET status='cancelled',
               finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE id=?""",
            (battle_id,),
        )
        self._conn.commit()
        return True

    def finish_battle(
        self,
        battle_id: int,
        winner: int | None,
        total_turns: int,
    ) -> None:
        """Mark battle as finished, record winner, and update ELO atomically."""
        with self._conn:
            self._conn.execute(
                """UPDATE battles
                   SET winner=?, total_turns=?,
                       finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                   WHERE id=?""",
                (winner, total_turns, battle_id),
            )
            self._update_elo(battle_id, winner)

    def _update_elo(self, battle_id: int, winner: int | None) -> None:
        """Compute and persist ELO deltas. Must be called inside a transaction."""
        row = self._conn.execute(
            "SELECT p1_model_id, p2_model_id FROM battles WHERE id=?",
            (battle_id,),
        ).fetchone()
        p1_id, p2_id = row["p1_model_id"], row["p2_model_id"]

        r1 = self._conn.execute(
            "SELECT rating FROM elo_ratings WHERE model_id=?", (p1_id,)
        ).fetchone()["rating"]
        r2 = self._conn.execute(
            "SELECT rating FROM elo_ratings WHERE model_id=?", (p2_id,)
        ).fetchone()["rating"]

        new_r1, new_r2 = updated_ratings(r1, r2, winner)

        for model_id, before, after in ((p1_id, r1, new_r1), (p2_id, r2, new_r2)):
            self._conn.execute(
                """UPDATE elo_ratings
                   SET rating=?, games=games+1,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                   WHERE model_id=?""",
                (after, model_id),
            )
            self._conn.execute(
                """INSERT INTO elo_history (battle_id, model_id, rating_before, rating_after, delta)
                   VALUES (?,?,?,?,?)""",
                (battle_id, model_id, before, after, after - before),
            )
        # No commit here — the `with self._conn:` block in finish_battle handles it.

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    def log_turn(
        self,
        battle_id: int,
        turn_number: int,
        player_role: str,
        prompt_version: str,
        action_chosen: str | None,
        parse_success: bool,
        llm_response: str | None = None,
        state_json: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO turns
               (battle_id, turn_number, player_role, prompt_version,
                action_chosen, parse_success, llm_response, state_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                battle_id, turn_number, player_role, prompt_version,
                action_chosen, int(parse_success), llm_response, state_json,
            ),
        )
        self._conn.commit()

    def get_turns_basic(self, battle_id: int) -> list[dict[str, Any]]:
        """Return per-turn summary rows (no state_json) ordered by turn number."""
        cur = self._conn.execute(
            """SELECT turn_number, player_role, prompt_version,
                      action_chosen, parse_success
               FROM turns WHERE battle_id=? ORDER BY turn_number""",
            (battle_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_player_model_ids(self, battle_id: int) -> tuple[int, int] | None:
        """Return (p1_model_id, p2_model_id) for a battle, or None if not found."""
        row = self._conn.execute(
            "SELECT p1_model_id, p2_model_id FROM battles WHERE id=?", (battle_id,)
        ).fetchone()
        return (row["p1_model_id"], row["p2_model_id"]) if row else None

    def get_battle_players(self, battle_id: int) -> dict[str, Any] | None:
        """Return provider and model_name for both players of a battle, or None."""
        row = self._conn.execute(
            """SELECT p1.provider AS p1_provider, p1.model_name AS p1_model,
                      p2.provider AS p2_provider, p2.model_name AS p2_model
               FROM battles b
               JOIN models p1 ON p1.id = b.p1_model_id
               JOIN models p2 ON p2.id = b.p2_model_id
               WHERE b.id=?""",
            (battle_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_battle_tag(self, battle_id: int, battle_tag: str) -> None:
        """Overwrite the battle_tag once the real Showdown tag is known."""
        self._conn.execute(
            "UPDATE battles SET battle_tag=? WHERE id=?", (battle_tag, battle_id)
        )
        self._conn.commit()

    def get_turns_with_state(self, battle_id: int) -> list[dict[str, Any]]:
        """Return all turns for a battle including state_json, ordered by turn then player."""
        cur = self._conn.execute(
            """SELECT turn_number, player_role, prompt_version,
                      action_chosen, parse_success, llm_response, state_json
               FROM turns WHERE battle_id=?
               ORDER BY turn_number, player_role""",
            (battle_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Leaderboard queries
    # ------------------------------------------------------------------

    def leaderboard(self, grouped: bool = True) -> list[dict[str, Any]]:
        """Return models sorted by ELO descending.

        Args:
            grouped: If True (default), aggregate all prompt versions for the same
                     (provider, model_name) into a single row — shows best ELO,
                     summed W/L/T, and a 'versions' field listing what was played.
                     If False, return one row per (provider, model_name, prompt_version).
        """
        if grouped:
            return self._leaderboard_grouped()
        return self._leaderboard_per_version()

    def _leaderboard_grouped(self) -> list[dict[str, Any]]:
        """One row per (provider, model_name) — aggregated across prompt versions."""
        cur = self._conn.execute(
            """SELECT m.provider, m.model_name,
                      MAX(e.rating)          AS rating,
                      SUM(e.games)           AS games,
                      COALESCE(SUM(wld.wins),   0) AS wins,
                      COALESCE(SUM(wld.losses), 0) AS losses,
                      COALESCE(SUM(wld.ties),   0) AS ties,
                      GROUP_CONCAT(DISTINCT m.prompt_version) AS versions,
                      (SELECT m2.id FROM models m2
                         JOIN elo_ratings e2 ON e2.model_id = m2.id
                        WHERE m2.provider = m.provider AND m2.model_name = m.model_name
                        ORDER BY e2.rating DESC LIMIT 1) AS model_id
               FROM models m
               JOIN elo_ratings e ON e.model_id = m.id
               LEFT JOIN (
                   SELECT model_id,
                          SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END) AS wins,
                          SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                          SUM(CASE WHEN result='tie'  THEN 1 ELSE 0 END) AS ties
                   FROM (
                       SELECT p1_model_id AS model_id,
                              CASE WHEN winner=1 THEN 'win'
                                   WHEN winner=2 THEN 'loss'
                                   ELSE 'tie' END AS result
                       FROM battles WHERE finished_at IS NOT NULL
                       UNION ALL
                       SELECT p2_model_id,
                              CASE WHEN winner=2 THEN 'win'
                                   WHEN winner=1 THEN 'loss'
                                   ELSE 'tie' END
                       FROM battles WHERE finished_at IS NOT NULL
                   ) GROUP BY model_id
               ) wld ON wld.model_id = m.id
               GROUP BY m.provider, m.model_name
               ORDER BY MAX(e.rating) DESC""",
        )
        return [dict(r) for r in cur.fetchall()]

    def _leaderboard_per_version(self) -> list[dict[str, Any]]:
        """One row per (provider, model_name, prompt_version) — original behaviour."""
        cur = self._conn.execute(
            """SELECT m.provider, m.model_name, m.prompt_version,
                      e.rating, e.games,
                      COALESCE(wld.wins,   0) AS wins,
                      COALESCE(wld.losses, 0) AS losses,
                      COALESCE(wld.ties,   0) AS ties
               FROM models m
               JOIN elo_ratings e ON e.model_id = m.id
               LEFT JOIN (
                   SELECT model_id,
                          SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END) AS wins,
                          SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                          SUM(CASE WHEN result='tie'  THEN 1 ELSE 0 END) AS ties
                   FROM (
                       SELECT p1_model_id AS model_id,
                              CASE WHEN winner=1 THEN 'win'
                                   WHEN winner=2 THEN 'loss'
                                   ELSE 'tie' END AS result
                       FROM battles WHERE finished_at IS NOT NULL
                       UNION ALL
                       SELECT p2_model_id,
                              CASE WHEN winner=2 THEN 'win'
                                   WHEN winner=1 THEN 'loss'
                                   ELSE 'tie' END
                       FROM battles WHERE finished_at IS NOT NULL
                   ) GROUP BY model_id
               ) wld ON wld.model_id = m.id
               ORDER BY e.rating DESC""",
        )
        return [dict(r) for r in cur.fetchall()]

    def recent_battles(self, limit: int = 10) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """SELECT b.id, b.battle_tag, b.format, b.total_turns, b.winner, b.finished_at,
                      p1.provider||'/'||p1.model_name AS p1,
                      p2.provider||'/'||p2.model_name AS p2
               FROM battles b
               JOIN models p1 ON p1.id = b.p1_model_id
               JOIN models p2 ON p2.id = b.p2_model_id
               WHERE b.finished_at IS NOT NULL
               ORDER BY b.finished_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Lessons (post-battle LLM reflections)
    # ------------------------------------------------------------------

    def create_lesson(self, model_id: int, battle_id: int, content: str) -> int:
        """Persist a post-battle lesson and return its id."""
        cur = self._conn.execute(
            "INSERT INTO lessons (model_id, battle_id, content) VALUES (?,?,?)",
            (model_id, battle_id, content),
        )
        self._conn.commit()
        row_id = cur.lastrowid
        assert row_id is not None
        return row_id

    def get_lessons(self, model_id: int, limit: int = 5) -> list[dict[str, Any]]:
        """Return the most recent lessons for a model, newest first."""
        cur = self._conn.execute(
            """SELECT id, battle_id, content, created_at
               FROM lessons WHERE model_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (model_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Model stats (per-model history page)
    # ------------------------------------------------------------------

    def get_model_stats(self, model_id: int) -> dict[str, Any] | None:
        """Return comprehensive stats for a model: identity, ELO history,
        battle history, turn quality summary, and recent lessons.

        Returns None if the model_id does not exist.
        """
        # Identity + current ELO + W/L/T
        info_row = self._conn.execute(
            """SELECT m.id, m.provider, m.model_name, m.prompt_version,
                      e.rating, e.games,
                      COALESCE(wld.wins,   0) AS wins,
                      COALESCE(wld.losses, 0) AS losses,
                      COALESCE(wld.ties,   0) AS ties
               FROM models m
               JOIN elo_ratings e ON e.model_id = m.id
               LEFT JOIN (
                   SELECT model_id,
                          SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END) AS wins,
                          SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                          SUM(CASE WHEN result='tie'  THEN 1 ELSE 0 END) AS ties
                   FROM (
                       SELECT p1_model_id AS model_id,
                              CASE WHEN winner=1 THEN 'win' WHEN winner=2 THEN 'loss' ELSE 'tie' END AS result
                       FROM battles WHERE finished_at IS NOT NULL
                       UNION ALL
                       SELECT p2_model_id,
                              CASE WHEN winner=2 THEN 'win' WHEN winner=1 THEN 'loss' ELSE 'tie' END AS result
                       FROM battles WHERE finished_at IS NOT NULL
                   ) GROUP BY model_id
               ) wld ON wld.model_id = m.id
               WHERE m.id = ?""",
            (model_id,),
        ).fetchone()
        if not info_row:
            return None

        # ELO history (chronological, capped to last 30 battles)
        elo_rows = self._conn.execute(
            """SELECT eh.battle_id, eh.rating_before, eh.rating_after, eh.delta,
                      b.finished_at
               FROM elo_history eh
               JOIN battles b ON b.id = eh.battle_id
               WHERE eh.model_id = ?
               ORDER BY b.finished_at ASC
               LIMIT 30""",
            (model_id,),
        ).fetchall()

        # Per-battle history (last 20 completed)
        battle_rows = self._conn.execute(
            """SELECT b.id, b.total_turns, b.winner, b.finished_at,
                      CASE WHEN b.p1_model_id = ? THEN 'p1' ELSE 'p2' END AS my_role,
                      CASE WHEN b.p1_model_id = ?
                           THEN p2.provider||'/'||p2.model_name
                           ELSE p1.provider||'/'||p1.model_name END AS opponent,
                      CASE WHEN (b.p1_model_id = ? AND b.winner = 1)
                                OR (b.p2_model_id = ? AND b.winner = 2) THEN 'win'
                           WHEN b.winner IS NULL THEN 'tie'
                           ELSE 'loss' END AS result
               FROM battles b
               JOIN models p1 ON p1.id = b.p1_model_id
               JOIN models p2 ON p2.id = b.p2_model_id
               WHERE (b.p1_model_id = ? OR b.p2_model_id = ?)
                 AND b.finished_at IS NOT NULL
               ORDER BY b.finished_at DESC
               LIMIT 20""",
            (model_id, model_id, model_id, model_id, model_id, model_id),
        ).fetchall()

        # Turn quality summary — parse_success rate
        turn_rows = self._conn.execute(
            """SELECT t.parse_success
               FROM turns t
               JOIN battles b ON b.id = t.battle_id
               WHERE (b.p1_model_id = ? AND t.player_role = 'p1')
                  OR (b.p2_model_id = ? AND t.player_role = 'p2')""",
            (model_id, model_id),
        ).fetchall()

        total_turns = len(turn_rows)
        parse_ok = sum(1 for r in turn_rows if r["parse_success"])
        parse_fail = total_turns - parse_ok
        parse_success_rate = round(parse_ok / total_turns * 100, 1) if total_turns else None

        # Recent lessons
        lesson_rows = self._conn.execute(
            """SELECT id, battle_id, content, created_at
               FROM lessons WHERE model_id=?
               ORDER BY created_at DESC LIMIT 10""",
            (model_id,),
        ).fetchall()

        return {
            "model": dict(info_row),
            "elo_history": [dict(r) for r in elo_rows],
            "battle_history": [dict(r) for r in battle_rows],
            "turn_stats": {
                "total_turns": total_turns,
                "parse_ok": parse_ok,
                "parse_fail": parse_fail,
                "parse_success_rate": parse_success_rate,
            },
            "lessons": [dict(r) for r in lesson_rows],
        }

    def close(self) -> None:
        self._conn.close()
