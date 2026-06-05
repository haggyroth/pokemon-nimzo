"""FastAPI application — REST endpoints and WebSocket battle stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nidozo.api.events import EventBus
from nidozo.db.store import BattleStore

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.environ.get("NIMZO_DB", "nimzo.db"))
_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StartBattleRequest(BaseModel):
    p1_provider: str = "random"
    p2_provider: str = "random"
    model: Optional[str] = None
    prompt_version: str = "v1"
    n_battles: int = 1


class StartBattleResponse(BaseModel):
    battle_ids: list[int]
    message: str


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(db_path: Path = _DB_PATH) -> FastAPI:
    bus = EventBus()
    store = BattleStore(db_path)

    app = FastAPI(title="Nidozo", version="0.6.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # REST: Leaderboard & battles
    # -----------------------------------------------------------------------

    @app.get("/api/leaderboard")
    def get_leaderboard() -> list[dict]:
        return store.leaderboard()

    @app.get("/api/battles")
    def get_battles(limit: int = 20) -> list[dict]:
        return store.recent_battles(limit=limit)

    @app.get("/api/battles/{battle_id}/turns")
    def get_turns(battle_id: int) -> list[dict]:
        rows = store._conn.execute(
            """SELECT turn_number, player_role, prompt_version,
                      action_chosen, parse_success
               FROM turns WHERE battle_id=? ORDER BY turn_number""",
            (battle_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/battles/{battle_id}/analysis")
    def get_analysis(battle_id: int) -> dict:
        from nidozo.analysis import analyze_battle
        turns = store.get_turns_with_state(battle_id)
        return analyze_battle(turns)

    # -----------------------------------------------------------------------
    # REST: Start a battle (runs in background, streams via WS)
    # -----------------------------------------------------------------------

    @app.post("/api/battles/start", response_model=StartBattleResponse)
    async def start_battle(
        req: StartBattleRequest,
        background_tasks: BackgroundTasks,
    ) -> StartBattleResponse:
        battle_ids = []
        for i in range(req.n_battles):
            p1_model = _model_name(req.p1_provider, req.model)
            p2_model = _model_name(req.p2_provider, req.model)
            p1_id = store.get_or_create_model(req.p1_provider, p1_model, req.prompt_version)
            p2_id = store.get_or_create_model(req.p2_provider, p2_model, req.prompt_version)
            bid = store.create_battle(
                f"pending-{req.p1_provider}-{req.p2_provider}-{i}",
                "gen3randombattle",
                p1_id,
                p2_id,
            )
            battle_ids.append(bid)

        background_tasks.add_task(
            _run_battles, req, battle_ids, store, bus
        )
        return StartBattleResponse(
            battle_ids=battle_ids,
            message=f"Started {req.n_battles} battle(s). Connect to /ws/battles to watch.",
        )

    # -----------------------------------------------------------------------
    # WebSocket: live battle stream
    # -----------------------------------------------------------------------

    @app.websocket("/ws/battles")
    async def battle_stream(ws: WebSocket) -> None:
        await ws.accept()
        q = bus.subscribe()
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                await ws.send_text(json.dumps(event))
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            bus.unsubscribe(q)

    # -----------------------------------------------------------------------
    # Serve React frontend (if built)
    # -----------------------------------------------------------------------

    if _FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")

    return app


# ---------------------------------------------------------------------------
# Background battle runner
# ---------------------------------------------------------------------------

async def _run_battles(
    req: StartBattleRequest,
    battle_ids: list[int],
    store: BattleStore,
    bus: EventBus,
) -> None:
    from poke_env import LocalhostServerConfiguration
    from nidozo.battle.streaming_player import StreamingLLMPlayer, StreamingRandomBot
    from nidozo.llm import AnthropicBackend, OpenAIBackend

    _FORMAT = "gen3randombattle"
    cfg = LocalhostServerConfiguration

    for battle_id in battle_ids:
        try:
            p1 = _build_streaming_player(
                req.p1_provider, req.model, "p1",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )
            p2 = _build_streaming_player(
                req.p2_provider, req.model, "p2",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )

            await bus.publish({
                "type": "battle_start",
                "battle_id": battle_id,
                "p1": f"{req.p1_provider}/{_model_name(req.p1_provider, req.model)}",
                "p2": f"{req.p2_provider}/{_model_name(req.p2_provider, req.model)}",
                "format": _FORMAT,
            })

            await p1.battle_against(p2, n_battles=1)

            winner = 1 if p1.n_won_battles > 0 else (2 if p2.n_won_battles > 0 else None)
            real_tag = next(iter(p1.battles), f"battle-{battle_id}")
            battle_obj = p1.battles.get(real_tag)
            total_turns = battle_obj.turn if battle_obj else 0

            store._conn.execute(
                "UPDATE battles SET battle_tag=? WHERE id=?", (real_tag, battle_id)
            )
            store.finish_battle(battle_id, winner, total_turns)

            await bus.publish({
                "type": "battle_end",
                "battle_id": battle_id,
                "battle_tag": real_tag,
                "winner": winner,
                "total_turns": total_turns,
            })

        except Exception as exc:
            logger.error("Battle %d failed: %s", battle_id, exc)
            await bus.publish({"type": "error", "battle_id": battle_id, "message": str(exc)})


def _build_streaming_player(
    provider: str,
    model: str | None,
    role: str,
    prompt_version: str,
    store: BattleStore,
    battle_id: int,
    bus: EventBus,
    cfg,
    fmt: str,
):
    from nidozo.battle.streaming_player import StreamingLLMPlayer, StreamingRandomBot
    from nidozo.llm import AnthropicBackend, OpenAIBackend

    if provider == "random":
        return StreamingRandomBot(
            event_bus=bus,
            player_role=role,
            battle_format=fmt,
            server_configuration=cfg,
        )

    if provider == "anthropic":
        backend = AnthropicBackend(
            model=model or "claude-sonnet-4-6",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    elif provider == "openai":
        backend = OpenAIBackend(
            model=model or "gpt-4o",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    else:  # lmstudio
        backend = OpenAIBackend(
            model=model or os.environ.get("LM_STUDIO_MODEL", "local-model"),
            api_key="lm-studio",
            base_url=os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
        )

    return StreamingLLMPlayer(
        backend=backend,
        event_bus=bus,
        player_role=role,
        prompt_version=prompt_version,
        store=store,
        battle_id=battle_id,
        battle_format=fmt,
        server_configuration=cfg,
    )


def _model_name(provider: str, model: str | None) -> str:
    defaults = {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "lmstudio": os.environ.get("LM_STUDIO_MODEL", "local-model"),
        "random": "random",
    }
    return model or defaults.get(provider, provider)
