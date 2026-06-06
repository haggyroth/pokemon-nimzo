"""Integration tests for BattleStore using an in-memory SQLite database."""

import pytest

from nidozo.db.elo import DEFAULT_RATING
from nidozo.db.store import BattleStore


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

# ------------------------------------------------------------------
# Model stats
# ------------------------------------------------------------------

def test_leaderboard_grouped_includes_model_id(store) -> None:
    """Grouped leaderboard rows include a model_id field."""
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("tag-1", "gen3randombattle", mid, opp)
    store.finish_battle(bid, winner=1, total_turns=10)
    rows = store.leaderboard(grouped=True)
    claude_row = next(r for r in rows if r["model_name"] == "claude-test")
    assert "model_id" in claude_row
    assert claude_row["model_id"] == mid


def test_get_model_stats_returns_none_for_missing(store) -> None:
    assert store.get_model_stats(99999) is None


def test_get_model_stats_identity_fields(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    stats = store.get_model_stats(mid)
    assert stats is not None
    assert stats["model"]["provider"] == "anthropic"
    assert stats["model"]["model_name"] == "claude-test"
    assert stats["model"]["prompt_version"] == "v2"
    assert "rating" in stats["model"]


def test_get_model_stats_win_loss_counts(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")

    bid1 = store.create_battle("t1", "gen3randombattle", mid, opp)
    store.finish_battle(bid1, winner=1, total_turns=10)   # win (p1)

    bid2 = store.create_battle("t2", "gen3randombattle", opp, mid)
    store.finish_battle(bid2, winner=1, total_turns=8)    # loss (p2, opp won)

    bid3 = store.create_battle("t3", "gen3randombattle", mid, opp)
    store.finish_battle(bid3, winner=None, total_turns=50) # tie

    stats = store.get_model_stats(mid)
    assert stats is not None
    m = stats["model"]
    assert m["wins"] == 1
    assert m["losses"] == 1
    assert m["ties"] == 1


def test_get_model_stats_elo_history(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")
    for i in range(3):
        bid = store.create_battle(f"h{i}", "gen3randombattle", mid, opp)
        store.finish_battle(bid, winner=1, total_turns=10)

    stats = store.get_model_stats(mid)
    assert stats is not None
    assert len(stats["elo_history"]) == 3
    row = stats["elo_history"][0]
    assert "rating_before" in row
    assert "rating_after" in row
    assert "delta" in row


def test_get_model_stats_battle_history(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("t1", "gen3randombattle", mid, opp)
    store.finish_battle(bid, winner=1, total_turns=15)

    stats = store.get_model_stats(mid)
    assert stats is not None
    assert len(stats["battle_history"]) == 1
    b = stats["battle_history"][0]
    assert b["result"] == "win"
    assert "opponent" in b
    assert b["total_turns"] == 15


def test_get_model_stats_turn_stats(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("t1", "gen3randombattle", mid, opp)
    store.log_turn(bid, 1, "p1", "v2", "surf", True)
    store.log_turn(bid, 2, "p1", "v2", None, False)
    store.log_turn(bid, 1, "p2", "v2", "flamethrower", True)  # opponent — should not count

    stats = store.get_model_stats(mid)
    assert stats is not None
    ts = stats["turn_stats"]
    assert ts["total_turns"] == 2   # only p1 turns
    assert ts["parse_ok"] == 1
    assert ts["parse_fail"] == 1
    assert ts["parse_success_rate"] == 50.0


def test_get_model_stats_lessons(store) -> None:
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    opp = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("t1", "gen3randombattle", mid, opp)
    store.create_lesson(mid, bid, "Always use Water-type moves.")

    stats = store.get_model_stats(mid)
    assert stats is not None
    assert len(stats["lessons"]) == 1
    assert stats["lessons"][0]["content"] == "Always use Water-type moves."
