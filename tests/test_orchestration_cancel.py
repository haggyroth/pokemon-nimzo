"""Regression tests for tournament/season/battle cancel handling (issues #130, #134).

A cancel via the API only flips the DB status row. The runners must (a) notice
that between battles and stop, and (b) never overwrite a 'cancelled' status with
'completed' at the end of their loop. A cancelled multi-battle run must also mark
its still-queued battles cancelled instead of stranding them as 'pending'.

These tests exercise the cancel/finalization paths only — they bail out before
any `battle_against` call, so no live Showdown server is needed.
"""

from __future__ import annotations

import asyncio

import pytest

from nidozo.api import orchestration
from nidozo.api.models import (
    PlayerSpec,
    StartBattleRequest,
    StartSeasonRequest,
    StartTournamentRequest,
)
from nidozo.api.orchestration import run_battles, run_season, run_tournament
from nidozo.db.store import BattleStore


@pytest.fixture
def store(tmp_path):
    s = BattleStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


class _RecordingBus:
    """Collects published events for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


def _two_random_players() -> list[dict]:
    return [
        {"provider": "random", "model_name": "r1"},
        {"provider": "random", "model_name": "r2"},
    ]


def _tournament_req() -> StartTournamentRequest:
    return StartTournamentRequest(
        players=[PlayerSpec(provider="random"), PlayerSpec(provider="random")],
        rounds=1,
        prompt_version="v5",
        tier="random",
        draft=False,
        tournament_format="round_robin",
    )


def _season_req() -> StartSeasonRequest:
    return StartSeasonRequest(
        name="test-season",
        players=[PlayerSpec(provider="random"), PlayerSpec(provider="random")],
        rounds=1,
        prompt_version="v5",
        tier="random",
        draft=False,
    )


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_tournament_bails_when_cancelled(store) -> None:
    """A tournament cancelled before the runner reaches a battle must stop the
    runner and leave the queued battle unplayed."""
    p1 = store.get_or_create_model("random", "r1", "v5")
    p2 = store.get_or_create_model("random", "r2", "v5")
    tid = store.create_tournament(_two_random_players(), 1, "v5", 1, "random")
    bid = store.create_battle("t-cancel-1", "gen9randombattle", p1, p2, tournament_id=tid)

    # Simulate a cancel arriving before the runner gets to the battle.
    store._conn.execute("UPDATE tournaments SET status='cancelled' WHERE id=?", (tid,))
    store._conn.commit()

    bus = _RecordingBus()
    await run_tournament(_tournament_req(), tid, [bid], _two_random_players(), store, bus, {})

    # Status must remain cancelled — NOT overwritten with completed.
    assert store.get_tournament(tid)["status"] == "cancelled"
    # The queued battle was never played.
    assert store.get_battle(bid)["status"] == "pending"
    # A cancel event was emitted, and no tournament_end fired.
    assert "tournament_cancelled" in bus.types()
    assert "tournament_end" not in bus.types()


@pytest.mark.asyncio
async def test_run_tournament_finalization_does_not_overwrite_cancel(store) -> None:
    """If the tournament is cancelled by the time the loop ends (no battles left),
    finalization must not flip it back to completed."""
    tid = store.create_tournament(_two_random_players(), 1, "v5", 0, "random")
    store._conn.execute("UPDATE tournaments SET status='cancelled' WHERE id=?", (tid,))
    store._conn.commit()

    bus = _RecordingBus()
    # Empty battle list → loop body never runs → straight to finalization guard.
    await run_tournament(_tournament_req(), tid, [], _two_random_players(), store, bus, {})

    assert store.get_tournament(tid)["status"] == "cancelled"
    assert "tournament_end" not in bus.types()


@pytest.mark.asyncio
async def test_run_tournament_completes_normally_when_not_cancelled(store) -> None:
    """Sanity: with no battles and a running status, the runner still completes."""
    tid = store.create_tournament(_two_random_players(), 1, "v5", 0, "random")
    store._conn.execute("UPDATE tournaments SET status='running' WHERE id=?", (tid,))
    store._conn.commit()

    bus = _RecordingBus()
    await run_tournament(_tournament_req(), tid, [], _two_random_players(), store, bus, {})

    assert store.get_tournament(tid)["status"] == "completed"
    assert "tournament_end" in bus.types()


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_season_bails_when_cancelled(store, monkeypatch) -> None:
    """A season cancelled mid-run must stop the runner before the next battle."""
    p1 = store.get_or_create_model("random", "r1", "v5")
    p2 = store.get_or_create_model("random", "r2", "v5")
    sid = store.create_season(
        name="s", tier="random", fmt="gen9randombattle",
        participants=_two_random_players(), rounds=1, prompt_version="v5",
        total_battles=1,
    )
    bid = store.create_battle("s-cancel-1", "gen9randombattle", p1, p2, season_id=sid)

    # run_season normally forces status='running' at the top; neutralize that so
    # our pre-set cancel survives (simulating a cancel that already landed).
    monkeypatch.setattr(store, "set_season_running", lambda _sid: None)
    store._conn.execute("UPDATE seasons SET status='cancelled' WHERE id=?", (sid,))
    store._conn.commit()

    bus = _RecordingBus()
    await run_season(_season_req(), sid, [bid], _two_random_players(), store, bus, {})

    assert store.get_season(sid)["status"] == "cancelled"
    assert store.get_battle(bid)["status"] == "pending"
    assert "season_cancelled" in bus.types()
    assert "season_end" not in bus.types()


@pytest.mark.asyncio
async def test_run_season_finalization_does_not_overwrite_cancel(store, monkeypatch) -> None:
    """If the season is cancelled by the time the loop ends, finalization must not
    flip it back to completed."""
    sid = store.create_season(
        name="s", tier="random", fmt="gen9randombattle",
        participants=_two_random_players(), rounds=1, prompt_version="v5",
        total_battles=0,
    )
    monkeypatch.setattr(store, "set_season_running", lambda _sid: None)
    store._conn.execute("UPDATE seasons SET status='cancelled' WHERE id=?", (sid,))
    store._conn.commit()

    bus = _RecordingBus()
    await run_season(_season_req(), sid, [], _two_random_players(), store, bus, {})

    assert store.get_season(sid)["status"] == "cancelled"
    assert "season_end" not in bus.types()


# ---------------------------------------------------------------------------
# Multi-battle run (issue #134)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_battles_cancel_marks_remaining_cancelled(store, monkeypatch) -> None:
    """Cancelling a multi-battle run cancels every still-queued battle instead of
    stranding them as 'pending'."""
    p1 = store.get_or_create_model("random", "r1", "v5")
    p2 = store.get_or_create_model("random", "r2", "v5")
    bids = [
        store.create_battle(f"mb-{i}", "gen9randombattle", p1, p2)
        for i in range(3)
    ]

    # Simulate the shared task being cancelled while the first battle is being
    # set up: raise CancelledError from player construction.
    def _cancel(*_a, **_k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(orchestration, "_build_streaming_player", _cancel)

    req = StartBattleRequest(
        p1_provider="random", p2_provider="random", n_battles=3, tier="random"
    )
    bus = _RecordingBus()
    with pytest.raises(asyncio.CancelledError):
        await run_battles(req, bids, store, bus, {})

    # No battle is left pending — all three are cancelled.
    statuses = [store.get_battle(b)["status"] for b in bids]
    assert statuses == ["cancelled", "cancelled", "cancelled"]

    # battle_cancelled is published for the two still-queued battles (the first
    # one's event is the cancel endpoint's responsibility, not the runner's).
    cancelled_ids = [e["battle_id"] for e in bus.events if e["type"] == "battle_cancelled"]
    assert cancelled_ids == bids[1:]
