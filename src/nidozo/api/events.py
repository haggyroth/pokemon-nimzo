"""EventBus — asyncio broadcast queue for live battle state streaming."""

from __future__ import annotations

import asyncio
from typing import Any

# Maximum events buffered per subscriber before oldest are dropped.
_QUEUE_MAX = 256


class EventBus:
    """Publish battle events; each subscriber gets its own bounded queue.

    If a subscriber's queue is full (e.g. a slow or dead WebSocket), the
    oldest buffered event is silently dropped to make room for the new one.
    This prevents a stuck client from growing memory without bound.
    """

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._queues):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest to make room
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # race between full-check and put; give up rather than block

    def publish_sync(self, event: dict[str, Any]) -> None:
        """Fire-and-forget from sync context (creates a task on the running loop)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            pass
