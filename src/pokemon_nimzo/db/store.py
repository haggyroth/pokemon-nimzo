"""BattleStore — all database read/write operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from pokemon_nimzo.db.schema import migrate
from pokemon_nimzo.db.elo import DEFAULT_RATING, updated_ratings

_DEFAULT_DB = Path(__file__).parent.parent.parent.parent / "nimzo.db"


class BattleStore:
    """Thread-safe SQLite store for battle results, ELO ratings, and turn logs.

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
            return row["id"]

        cur = self._conn.execute(
            "INSERT INTO models (provider, model_name, prompt_version) VALUES (?,?,?)",
            (provider, model_name, prompt_version),
        )
        model_id = cur.lastrowid
        self._conn.execute(
            "INSERT INTO elo_ratings (model_id, rating, games) VALUES (?,?,0)",
            (model_id, DEFAULT_RATING),
        )
        self._conn.commit()
        return model_id

    # ------------------------------------------------------------------
    # Battles
    # ------------------------------------------------------------------

    def create_battle(
        self,
        battle_tag: str,
        format: str,
        p1_model_id: int,
        p2_model_id: int,
    ) -> int:
        """Insert a battle row and return its id."""
        cur = self._conn.execute(
            """INSERT INTO battles (battle_tag, format, p1_model_id, p2_model_id)
               VALUES (?,?,?,?)""",
            (battle_tag, format, p1_model_id, p2_model_id),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_battle(
        self,
        battle_id: int,
        winner: int | None,
        total_turns: int,
    ) -> None:
        """Mark battle as finished, record winner, update ELO."""
        self._conn.execute(
            """UPDATE battles
               SET winner=?, total_turns=?,
                   finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE id=?""",
            (winner, total_turns, battle_id),
        )
        self._conn.commit()
        self._update_elo(battle_id, winner)

    def _update_elo(self, battle_id: int, winner: int | None) -> None:
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
        self._conn.commit()

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    def log_turn(
        self,
        battle_id: int,
        turn_number: int,
        player_role: str,
        prompt_version: str,
        action_chosen: Optional[str],
        parse_success: bool,
        llm_response: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO turns
               (battle_id, turn_number, player_role, prompt_version,
                action_chosen, parse_success, llm_response)
               VALUES (?,?,?,?,?,?,?)""",
            (
                battle_id, turn_number, player_role, prompt_version,
                action_chosen, int(parse_success), llm_response,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Leaderboard queries
    # ------------------------------------------------------------------

    def leaderboard(self) -> list[dict]:
        """Return all models sorted by ELO descending."""
        cur = self._conn.execute(
            """SELECT m.provider, m.model_name, m.prompt_version,
                      e.rating, e.games,
                      COALESCE(wins.n, 0)  AS wins,
                      COALESCE(losses.n,0) AS losses,
                      COALESCE(ties.n, 0)  AS ties
               FROM models m
               JOIN elo_ratings e ON e.model_id = m.id
               LEFT JOIN (
                   SELECT p1_model_id AS mid, COUNT(*) AS n FROM battles WHERE winner=1 GROUP BY 1
                   UNION ALL
                   SELECT p2_model_id, COUNT(*) FROM battles WHERE winner=2 GROUP BY 1
               ) wins   ON wins.mid = m.id
               LEFT JOIN (
                   SELECT p1_model_id AS mid, COUNT(*) AS n FROM battles WHERE winner=2 GROUP BY 1
                   UNION ALL
                   SELECT p2_model_id, COUNT(*) FROM battles WHERE winner=1 GROUP BY 1
               ) losses ON losses.mid = m.id
               LEFT JOIN (
                   SELECT p1_model_id AS mid, COUNT(*) AS n FROM battles WHERE winner IS NULL GROUP BY 1
                   UNION ALL
                   SELECT p2_model_id, COUNT(*) FROM battles WHERE winner IS NULL GROUP BY 1
               ) ties   ON ties.mid = m.id
               ORDER BY e.rating DESC""",
        )
        return [dict(r) for r in cur.fetchall()]

    def recent_battles(self, limit: int = 10) -> list[dict]:
        cur = self._conn.execute(
            """SELECT b.battle_tag, b.format, b.total_turns, b.winner, b.finished_at,
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

    def close(self) -> None:
        self._conn.close()
