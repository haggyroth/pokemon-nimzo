"""Integration tests for BattleStore using an in-memory SQLite database."""

import pytest

from nidozo.db.store import BattleStore
from nidozo.db.elo import DEFAULT_RATING


@pytest.fixture
def store(tmp_path):
    s = BattleStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


# ------------------------------------------------------------------
# Model registration
# ------------------------------------------------------------------

def test_get_or_create_model_creates_new(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    assert isinstance(mid, int)


def test_get_or_create_model_idempotent(store) -> None:
    mid1 = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    mid2 = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    assert mid1 == mid2


def test_different_prompt_version_is_different_model(store) -> None:
    mid1 = store.get_or_create_model("anthropic", "claude-sonnet-4-6", prompt_version="v1")
    mid2 = store.get_or_create_model("anthropic", "claude-sonnet-4-6", prompt_version="v2")
    assert mid1 != mid2


def test_new_model_gets_default_elo(store) -> None:
    mid = store.get_or_create_model("random", "random")
    row = store._conn.execute(
        "SELECT rating FROM elo_ratings WHERE model_id=?", (mid,)
    ).fetchone()
    assert row["rating"] == DEFAULT_RATING


# ------------------------------------------------------------------
# Battle lifecycle
# ------------------------------------------------------------------

def test_create_battle_returns_id(store) -> None:
    p1 = store.get_or_create_model("random", "random")
    p2 = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    bid = store.create_battle("battle-1", "gen3randombattle", p1, p2)
    assert isinstance(bid, int)


def test_finish_battle_records_winner(store) -> None:
    p1 = store.get_or_create_model("random", "random")
    p2 = store.get_or_create_model("random", "random-2")
    bid = store.create_battle("battle-2", "gen3randombattle", p1, p2)
    store.finish_battle(bid, winner=1, total_turns=25)

    row = store._conn.execute(
        "SELECT winner, total_turns FROM battles WHERE id=?", (bid,)
    ).fetchone()
    assert row["winner"] == 1
    assert row["total_turns"] == 25


def test_finish_battle_updates_elo(store) -> None:
    p1 = store.get_or_create_model("random", "a")
    p2 = store.get_or_create_model("random", "b")
    bid = store.create_battle("battle-3", "gen3randombattle", p1, p2)
    store.finish_battle(bid, winner=1, total_turns=10)

    r1 = store._conn.execute("SELECT rating FROM elo_ratings WHERE model_id=?", (p1,)).fetchone()["rating"]
    r2 = store._conn.execute("SELECT rating FROM elo_ratings WHERE model_id=?", (p2,)).fetchone()["rating"]

    assert r1 > DEFAULT_RATING
    assert r2 < DEFAULT_RATING


def test_elo_history_row_created(store) -> None:
    p1 = store.get_or_create_model("random", "c")
    p2 = store.get_or_create_model("random", "d")
    bid = store.create_battle("battle-4", "gen3randombattle", p1, p2)
    store.finish_battle(bid, winner=2, total_turns=15)

    count = store._conn.execute(
        "SELECT COUNT(*) FROM elo_history WHERE battle_id=?", (bid,)
    ).fetchone()[0]
    assert count == 2  # one row per player


def test_tie_elo_unchanged(store) -> None:
    p1 = store.get_or_create_model("random", "e")
    p2 = store.get_or_create_model("random", "f")
    bid = store.create_battle("battle-5", "gen3randombattle", p1, p2)
    store.finish_battle(bid, winner=None, total_turns=50)

    r1 = store._conn.execute("SELECT rating FROM elo_ratings WHERE model_id=?", (p1,)).fetchone()["rating"]
    r2 = store._conn.execute("SELECT rating FROM elo_ratings WHERE model_id=?", (p2,)).fetchone()["rating"]

    assert r1 == pytest.approx(DEFAULT_RATING)
    assert r2 == pytest.approx(DEFAULT_RATING)


# ------------------------------------------------------------------
# Turn logging
# ------------------------------------------------------------------

def test_log_turn_inserts_row(store) -> None:
    p1 = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    p2 = store.get_or_create_model("random", "random")
    bid = store.create_battle("battle-6", "gen3randombattle", p1, p2)

    store.log_turn(bid, 1, "p1", "v1", "move 2", True, "I'll use Thunderbolt.\nACTION: move 2")

    row = store._conn.execute("SELECT * FROM turns WHERE battle_id=?", (bid,)).fetchone()
    assert row["action_chosen"] == "move 2"
    assert row["parse_success"] == 1


def test_log_turn_parse_failure(store) -> None:
    p1 = store.get_or_create_model("anthropic", "claude-sonnet-4-6")
    p2 = store.get_or_create_model("random", "random")
    bid = store.create_battle("battle-7", "gen3randombattle", p1, p2)

    store.log_turn(bid, 3, "p1", "v1", None, False, "I'm not sure...")

    row = store._conn.execute("SELECT * FROM turns WHERE battle_id=?", (bid,)).fetchone()
    assert row["parse_success"] == 0
    assert row["action_chosen"] is None


# ------------------------------------------------------------------
# Leaderboard
# ------------------------------------------------------------------

def test_leaderboard_sorted_by_elo(store) -> None:
    strong = store.get_or_create_model("anthropic", "strong-model")
    weak = store.get_or_create_model("anthropic", "weak-model")

    # strong wins 3 battles in a row
    for i in range(3):
        bid = store.create_battle(f"lb-battle-{i}", "gen3randombattle", strong, weak)
        store.finish_battle(bid, winner=1, total_turns=20)

    rows = store.leaderboard()
    assert rows[0]["model_name"] == "strong-model"
    assert rows[1]["model_name"] == "weak-model"
    assert rows[0]["rating"] > rows[1]["rating"]
