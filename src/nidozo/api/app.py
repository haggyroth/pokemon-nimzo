"""FastAPI application factory — wires routes, WebSocket, and middleware."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from nidozo import __version__
from nidozo.api.events import EventBus
from nidozo.api.routes import create_router
from nidozo.api.ws import create_ws_router
from nidozo.db.store import BattleStore

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.environ.get("NIDOZO_DB") or os.environ.get("NIMZO_DB", "nidozo.db"))
_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"


def create_app(db_path: Path = _DB_PATH) -> FastAPI:
    bus = EventBus()
    store = BattleStore(db_path)

    # battle_id → asyncio.Task — lets us cancel running battles
    _active_tasks: dict[int, asyncio.Task[None]] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Nidozo starting up", extra={"db": str(db_path)})
        yield
        if _active_tasks:
            logger.info(
                "Shutdown: cancelling %d active battle task(s)", len(_active_tasks)
            )
            for task in list(_active_tasks.values()):
                task.cancel()
            await asyncio.gather(*_active_tasks.values(), return_exceptions=True)
        store.close()
        logger.info("Nidozo shut down cleanly")

    app = FastAPI(title="Nidozo", version=__version__, lifespan=lifespan)
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://localhost:5001",   # serve.py production default
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.include_router(create_router(store, bus, _active_tasks))
    app.include_router(create_ws_router(bus))

    if _FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")

    return app
