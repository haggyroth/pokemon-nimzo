"""WebSocket endpoint for the live battle stream."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def create_ws_router(bus: Any) -> APIRouter:
    """Return a router containing the /ws/battles WebSocket endpoint."""
    router = APIRouter()

    @router.websocket("/ws/battles")
    async def battle_stream(ws: WebSocket) -> None:
        await ws.accept()
        q = bus.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    await ws.send_text(json.dumps(event))
                except TimeoutError:
                    await ws.send_text(json.dumps({"type": "ping"}))
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(q)

    return router
