"""Regression test for season narrative generation (issue #137).

Season battles must schedule a post-battle narrative like every other runner.
This drives one season battle with a fake player (no live Showdown) and stubbed
generators, asserting both lessons and narrative are scheduled.
"""

from __future__ import annotations

import asyncio

import pytest

from nidozo.api import orchestration
from nidozo.api.models import PlayerSpec, StartSeasonRequest
from nidozo.api.orchestration import run_season
from nidozo.db.store import BattleStore


@pytest.fixture
def store(tmp_path):
    s = BattleStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)


class _FakeBattleObj:
    turn = 7


class _FakePlayer:
    """Minimal stand-in for a StreamingLLMPlayer — no Showdown connection."""

    def __init__(self, role: str) -> None:
        # p1 wins so the runner records a decisive result.
        self.n_won_battles = 1 if role == "p1" else 0
        self.battles = {"battle-fake-1": _FakeBattleObj()}

    async def battle_against(self, _other, n_battles: int = 1) -> None:
        return None


@pytest.mark.asyncio
async def test_run_season_schedules_narrative(store, monkeypatch) -> None:
    p1 = store.get_or_create_model("random", "r1", "v5")
    p2 = store.get_or_create_model("random", "r2", "v5")
    sid = store.create_season(
        name="s", tier="random", fmt="gen9randombattle",
        participants=[
            {"provider": "random", "model_name": "r1"},
            {"provider": "random", "model_name": "r2"},
        ],
        rounds=1, prompt_version="v5", total_battles=1,
    )
    bid = store.create_battle("s-narr-1", "gen9randombattle", p1, p2, season_id=sid)

    # Fake player construction (role is the 3rd positional arg).
    def _fake_build(*args, **_kwargs):
        return _FakePlayer(args[2])

    monkeypatch.setattr(orchestration, "_build_streaming_player", _fake_build)

    # Stub the generators so we record scheduling without running LLM/analysis.
    lessons_calls: list[int] = []
    narrative_calls: list[int] = []

    async def _fake_lessons(_store, battle_id, *a, **k):
        lessons_calls.append(battle_id)

    async def _fake_narrative(_store, battle_id, *a, **k):
        narrative_calls.append(battle_id)

    monkeypatch.setattr(orchestration, "generate_and_store_lessons", _fake_lessons)
    monkeypatch.setattr(orchestration, "generate_and_store_narrative", _fake_narrative)

    bus = _RecordingBus()
    await run_season(_season_req(), sid, [bid], _two_players(), store, bus, {})
    # Let the spawned background tasks run.
    await asyncio.sleep(0)

    assert narrative_calls == [bid]   # the fix: season now schedules a narrative
    assert lessons_calls == [bid]     # lessons still scheduled too


def _two_players() -> list[dict]:
    return [
        {"provider": "random", "model_name": "r1"},
        {"provider": "random", "model_name": "r2"},
    ]


def _season_req() -> StartSeasonRequest:
    return StartSeasonRequest(
        name="s",
        players=[PlayerSpec(provider="random"), PlayerSpec(provider="random")],
        rounds=1,
        prompt_version="v5",
        tier="random",
        draft=False,
    )
