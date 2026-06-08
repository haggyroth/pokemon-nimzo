"""Tests for the /ws/battles WebSocket endpoint."""

from __future__ import annotations

import asyncio
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient  # noqa: F401 — httpx2 installed to silence deprecation

import nidozo.api.ws as ws_mod
from nidozo.api.ws import create_ws_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(q: asyncio.Queue) -> tuple[FastAPI, MagicMock]:
    """Return a minimal FastAPI app wired to the WS router via a mock bus."""
    mock_bus = MagicMock()
    mock_bus.subscribe.return_value = q
    app = FastAPI()
    app.include_router(create_ws_router(mock_bus))
    return app, mock_bus


# ---------------------------------------------------------------------------
# Connect / subscribe / unsubscribe
# ---------------------------------------------------------------------------


def test_ws_subscribe_called_on_connect() -> None:
    """The bus is subscribed when a client connects."""
    q: asyncio.Queue = asyncio.Queue()
    app, mock_bus = _make_app(q)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/battles"):
            pass

    mock_bus.subscribe.assert_called_once()


def test_ws_unsubscribes_on_disconnect() -> None:
    """The queue is removed from the bus when the client disconnects."""
    q: asyncio.Queue = asyncio.Queue()
    app, mock_bus = _make_app(q)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/battles"):
            pass  # close immediately

    mock_bus.unsubscribe.assert_called_once_with(q)


# ---------------------------------------------------------------------------
# Event delivery
# ---------------------------------------------------------------------------


def test_ws_delivers_published_event() -> None:
    """An event pre-queued before connection is forwarded to the WS client."""
    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait({"type": "battle_start", "battle_id": 42})

    app, _ = _make_app(q)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/battles") as ws:
            data = ws.receive_json()

    assert data == {"type": "battle_start", "battle_id": 42}


def test_ws_delivers_multiple_events_in_order() -> None:
    """Multiple queued events arrive in FIFO order."""
    q: asyncio.Queue = asyncio.Queue()
    events = [{"n": i} for i in range(3)]
    for ev in events:
        q.put_nowait(ev)

    app, _ = _make_app(q)

    received = []
    with TestClient(app) as client:
        with client.websocket_connect("/ws/battles") as ws:
            for _ in events:
                received.append(ws.receive_json())

    assert received == events


# ---------------------------------------------------------------------------
# Timeout → ping
# ---------------------------------------------------------------------------


def test_ws_sends_ping_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """When wait_for times out, the handler sends a ping and keeps going."""
    q: asyncio.Queue = asyncio.Queue()
    app, _ = _make_app(q)

    # Replace asyncio in ws_mod's namespace with a proxy that raises TimeoutError
    # exactly once, then falls through to the real implementation.
    call_count = 0
    real_asyncio = asyncio

    async def mock_wait_for(coro, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Cleanly discard the coroutine before raising to avoid ResourceWarning
            coro.close()
            raise TimeoutError()
        # Second call: put an item so the handler can proceed and we can read it
        q.put_nowait({"type": "after_ping"})
        return await real_asyncio.wait_for(coro, timeout=timeout)

    # Patch only the ws module's reference to asyncio — safe, scoped to this test
    proxy = types.SimpleNamespace(
        **{k: getattr(real_asyncio, k) for k in dir(real_asyncio) if not k.startswith("__")}
    )
    proxy.wait_for = mock_wait_for  # type: ignore[attr-defined]
    monkeypatch.setattr(ws_mod, "asyncio", proxy)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/battles") as ws:
            ping = ws.receive_json()
            assert ping == {"type": "ping"}
            # Confirm the handler resumed normally after the ping
            after = ws.receive_json()
            assert after == {"type": "after_ping"}
