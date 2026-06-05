"""EventBus — asyncio broadcast queue for live battle state streaming."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    """Publish battle events; subscribers get their own queue."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._queues):
            await q.put(event)

    def publish_sync(self, event: dict[str, Any]) -> None:
        """Fire-and-forget from sync context (creates a task on the running loop)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            pass


# Module-level singleton — shared between the API and battle runner
bus = EventBus()
