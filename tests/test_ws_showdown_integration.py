"""Integration tests — Showdown spectator proxy (OP-02 Stage 5).

These tests verify the proxy against a **real** Pokémon Showdown server.
They are excluded from the default test run and should be executed manually
or in a dedicated CI job that starts the server first.

Requirements
------------
* Showdown running with ``--no-security``:  ``./scripts/start_showdown.sh``

Run with::

    pytest -m integration tests/test_ws_showdown_integration.py
"""

from __future__ import annotations

import asyncio
import socket

import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nidozo.api.ws_showdown import create_showdown_ws_router

SHOWDOWN_WS = "ws://localhost:8000/showdown/websocket"
_TIMEOUT = 20.0

pytestmark = pytest.mark.integration


def _showdown_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 8000), timeout=1):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _login(ws: websockets.WebSocketClientProtocol, name: str) -> None:
    """Guest login on a ``--no-security`` Showdown server."""
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=_TIMEOUT)
        text = raw.decode() if isinstance(raw, bytes) else raw
        for line in text.split("\n"):
            if line.startswith("|challstr|"):
                await ws.send(f"|/trn {name},0,")
            elif line.startswith("|updateuser|"):
                parts = line.split("|")
                # parts: ['', 'updateuser', ' NAME', NAMED, AVATAR, ...]
                if len(parts) > 3 and parts[3] == "1":
                    return


async def _make_battle_room() -> str:
    """Create a live Gen 3 Random Battle; return the room id once |turn|1 fires.

    In Gen 3 Random Battle, leads are auto-assigned so |turn|1 appears
    immediately after the battle starts — no move choices are needed.
    """
    room: list[str] = []
    ready = asyncio.Event()

    async with (
        websockets.connect(SHOWDOWN_WS) as ws1,
        websockets.connect(SHOWDOWN_WS) as ws2,
    ):
        await asyncio.gather(
            _login(ws1, "NidozoIntA"),
            _login(ws2, "NidozoIntB"),
        )

        # Bot 1 challenges Bot 2 (global command — leading | = global room).
        await ws1.send("|/challenge NidozoIntB gen3randombattle")

        async def drive(ws: websockets.WebSocketClientProtocol, is_challenger: bool) -> None:
            while not ready.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=_TIMEOUT)
                except asyncio.TimeoutError:
                    return
                text = raw.decode() if isinstance(raw, bytes) else raw

                for line in text.split("\n"):
                    if line.startswith(">battle-") and not room:
                        room.append(line[1:])  # strip leading '>'

                # Bot 2 accepts when it sees the challenge notification.
                if (
                    not is_challenger
                    and "|updatechallenges|" in text
                    and "NidozoIntA" in text
                ):
                    await ws.send("|/accept NidozoIntA")

                if "|turn|1" in text:
                    ready.set()

        await asyncio.gather(
            drive(ws1, is_challenger=True),
            drive(ws2, is_challenger=False),
        )

    assert room, "Battle room never created — is Showdown running with --no-security?"
    return room[0]


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

def test_proxy_relays_init_battle_and_turn_frames() -> None:
    """Proxy relays ``|init|battle`` and ``|turn|`` from a live Showdown room.

    Creates a real battle between two guest bots, then connects the in-process
    proxy to that room.  The Showdown server replays the full battle log to
    any spectator that joins, so the proxy receives the complete sequence
    (including ``|init|battle`` and ``|turn|1``) even if it connects after
    the battle has started.
    """
    if not _showdown_reachable():
        pytest.skip("Showdown not running on localhost:8000")

    room = asyncio.run(_make_battle_room())
    assert room.startswith("battle-gen3randombattle-"), f"Unexpected room id: {room!r}"

    # Use the real upstream connector — no fake injection.
    app = FastAPI()
    app.include_router(create_showdown_ws_router())
    client = TestClient(app)

    received: list[str] = []
    with client.websocket_connect(f"/ws/showdown/{room}") as ws:
        for _ in range(20):
            try:
                frame = ws.receive_text()
                if frame == "|ping":
                    continue
                received.append(frame)
                if any("|turn|1" in f for f in received):
                    break
            except Exception:  # noqa: BLE001 — connection closed, stop collecting
                break

    combined = "\n".join(received)
    assert "|init|battle" in combined, f"|init|battle missing from proxy frames:\n{combined!r}"
    assert "|turn|" in combined, f"|turn| missing from proxy frames:\n{combined!r}"
