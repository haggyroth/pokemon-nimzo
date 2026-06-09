"""Unit tests for _StreamingMixin (OP-02 Stage 1).

Tests the showdown_room emission logic without a live poke-env / Showdown
server by injecting a minimal fake base class and a scripted EventBus.
"""

from __future__ import annotations

import pytest

from nidozo.api.events import EventBus
from nidozo.battle.streaming_player import _StreamingMixin


class _FakeBase:
    """Minimal stand-in for poke-env's Player._handle_battle_message."""

    async def _handle_battle_message(self, split_messages: list[list[str]]) -> None:
        pass


class _TestPlayer(_StreamingMixin, _FakeBase):
    """Concrete mixin under test — no poke-env dependencies needed."""

    def __init__(self, bus: EventBus, player_role: str = "p1", battle_id: int | None = None) -> None:
        self._init_streaming(bus, player_role)
        self._battles: dict = {}
        self._battle_id = battle_id


def _frame(room: str) -> list[list[str]]:
    """Minimal split_messages representation of a Showdown battle frame."""
    return [[f">{room}"], ["", "turn", "1"]]


@pytest.mark.asyncio
async def test_showdown_room_emitted_on_first_frame() -> None:
    """_StreamingMixin emits showdown_room once when a new battle room is seen."""
    bus = EventBus()
    q = bus.subscribe()
    player = _TestPlayer(bus, player_role="p1", battle_id=7)

    await player._handle_battle_message(_frame("battle-gen3randombattle-7"))

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    room_events = [e for e in events if e["type"] == "showdown_room"]
    assert len(room_events) == 1
    assert room_events[0]["room"] == "battle-gen3randombattle-7"
    assert room_events[0]["battle_id"] == 7


@pytest.mark.asyncio
async def test_showdown_room_emitted_only_once_per_battle() -> None:
    """Repeated frames for the same room do not produce duplicate showdown_room events."""
    bus = EventBus()
    q = bus.subscribe()
    player = _TestPlayer(bus)

    frame = _frame("battle-gen3randombattle-42")
    await player._handle_battle_message(frame)
    await player._handle_battle_message(frame)
    await player._handle_battle_message(frame)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    room_events = [e for e in events if e["type"] == "showdown_room"]
    assert len(room_events) == 1


@pytest.mark.asyncio
async def test_showdown_room_emitted_per_distinct_room() -> None:
    """Each new room tag gets its own showdown_room event (back-to-back battles)."""
    bus = EventBus()
    q = bus.subscribe()
    player = _TestPlayer(bus)

    await player._handle_battle_message(_frame("battle-gen3randombattle-1"))
    await player._handle_battle_message(_frame("battle-gen3randombattle-2"))

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    rooms = [e["room"] for e in events if e["type"] == "showdown_room"]
    assert rooms == ["battle-gen3randombattle-1", "battle-gen3randombattle-2"]


@pytest.mark.asyncio
async def test_showdown_room_battle_id_none_for_random_bot() -> None:
    """When no _battle_id is set (e.g. RandomBot), battle_id field is None."""
    bus = EventBus()
    q = bus.subscribe()
    player = _TestPlayer(bus)  # no battle_id

    await player._handle_battle_message(_frame("battle-gen3randombattle-99"))

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    room_events = [e for e in events if e["type"] == "showdown_room"]
    assert room_events[0]["battle_id"] is None


@pytest.mark.asyncio
async def test_showdown_room_not_emitted_for_frameless_message() -> None:
    """Frames that lack a leading >room line (global messages) don't emit showdown_room."""
    bus = EventBus()
    q = bus.subscribe()
    player = _TestPlayer(bus)

    # Global frame: no leading '>room' line
    await player._handle_battle_message([["", "challstr", "4|FAKE"]])

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    assert not any(e["type"] == "showdown_room" for e in events)
