"""Lifespan context manager for the Nidozo FastAPI app.

Handles startup logging and graceful shutdown: cancels any in-flight battle
tasks and closes the database connection.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from nidozo.db.store import BattleStore

logger = logging.getLogger(__name__)


def create_lifespan(
    store: BattleStore,
    active_tasks: dict[int, asyncio.Task[None]],
    db_path: Path,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return a lifespan context manager bound to *store* and *active_tasks*."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Nidozo starting up", extra={"db": str(db_path)})
        stale = store.abort_stale_records()
        if any(stale.values()):
            logger.warning(
                "Cleaned up stale records from previous run",
                extra=stale,
            )
        yield
        if active_tasks:
            logger.info(
                "Shutdown: cancelling %d active battle task(s)", len(active_tasks)
            )
            for task in list(active_tasks.values()):
                task.cancel()
            await asyncio.gather(*active_tasks.values(), return_exceptions=True)
        store.close()
        logger.info("Nidozo shut down cleanly")

    return lifespan
