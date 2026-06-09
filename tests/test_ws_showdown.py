"""Tests for the Showdown spectator-stream proxy (OP-02, #84).

The upstream Showdown connection is injected as a scripted fake, so these run
with no live Showdown server.  They cover room validation, the guest handshake
sequence, verbatim frame relay, and that login frames are not leaked to the
browser.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nidozo.api.ws_showdown import create_showdown_ws_router, is_valid_room


class FakeUpstream:
    """Scripted stand-in for a Showdown WebSocket connection.

    Seeds a ``|challstr|`` on construction; replies to ``/trn`` with a NAMED
    ``|updateuser|`` and to ``/join`` by emitting the supplied battle frames.
    ``recv`` blocks once the script is exhausted, mimicking a live battle.
    """

    def __init__(self, frames_after_join: list[str]) -> None:
        self.sent: list[str] = []
        self.closed = False
        self._frames_after_join = frames_after_join
        self._inbox: asyncio.Queue[str] = asyncio.Queue()
        self._inbox.put_nowait("|challstr|4|TESTCHALLSTR")

    async def send(self, message: str) -> None:
        self.sent.append(message)
        if message.startswith("|/trn "):
            await self._inbox.put("|updateuser| NidozoSpecAbc|1|170|{}")
        elif message.startswith("|/join "):
            for frame in self._frames_after_join:
                await self._inbox.put(frame)

    async def recv(self) -> str:
        return await self._inbox.get()

    async def close(self) -> None:
        self.closed = True


def _make_app(frames_after_join: list[str], created: list[FakeUpstream]) -> FastAPI:
    async def fake_connect(uri: str) -> FakeUpstream:
        fake = FakeUpstream(frames_after_join)
        created.append(fake)
        return fake

    app = FastAPI()
    app.include_router(create_showdown_ws_router(connect_upstream=fake_connect))
    return app


# ---------------------------------------------------------------------------
# Room validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "room,ok",
    [
        ("battle-gen3randombattle-17", True),
        ("battle-gen3ou-1234-abcdef", True),
        ("lobby", False),
        ("battle-../etc", False),
        ("global", False),
        ("battle-Gen3OU-1", False),   # uppercase rejected
        ("", False),
    ],
)
def test_is_valid_room(room: str, ok: bool) -> None:
    assert is_valid_room(room) is ok


def test_invalid_room_is_rejected() -> None:
    """A non-battle room id is closed before any upstream connection is made."""
    created: list[FakeUpstream] = []
    app = _make_app([], created)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/showdown/lobby") as ws:
            ws.receive_text()

    # Upstream was never dialed for a rejected room.
    assert created == []


# ---------------------------------------------------------------------------
# Handshake + relay
# ---------------------------------------------------------------------------

def test_handshake_then_relays_battle_frames() -> None:
    """After guest login + join, post-join frames are relayed verbatim."""
    frames = [
        ">battle-gen3randombattle-1\n|init|battle\n|title|A vs B",
        "|turn|1",
    ]
    created: list[FakeUpstream] = []
    app = _make_app(frames, created)
    client = TestClient(app)

    with client.websocket_connect("/ws/showdown/battle-gen3randombattle-1") as ws:
        assert ws.receive_text() == frames[0]
        assert ws.receive_text() == frames[1]

    # The upstream saw exactly the guest-login + join sequence.
    fake = created[0]
    trn = [m for m in fake.sent if m.startswith("|/trn ")]
    join = [m for m in fake.sent if m.startswith("|/join ")]
    assert trn and trn[0].endswith(",0,")          # empty assertion
    assert join == ["|/join battle-gen3randombattle-1"]


def test_login_frames_are_not_leaked_to_browser() -> None:
    """The browser must only receive post-join battle frames, never login frames."""
    frames = ["|turn|1"]
    created: list[FakeUpstream] = []
    app = _make_app(frames, created)
    client = TestClient(app)

    with client.websocket_connect("/ws/showdown/battle-gen3ou-9") as ws:
        first = ws.receive_text()

    # The very first thing the browser sees is the battle frame, not |challstr|
    # or |updateuser|.
    assert first == "|turn|1"
    assert not first.startswith("|challstr|")
    assert not first.startswith("|updateuser|")
