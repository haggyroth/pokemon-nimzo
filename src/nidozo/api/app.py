"""FastAPI application — REST endpoints and WebSocket battle stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nidozo.api.events import EventBus
from nidozo.db.store import BattleStore

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.environ.get("NIDOZO_DB") or os.environ.get("NIMZO_DB", "nidozo.db"))
_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StartBattleRequest(BaseModel):
    p1_provider: str = "random"
    p2_provider: str = "random"
    p1_model: str | None = None
    p2_model: str | None = None
    model: str | None = None
    prompt_version: str = "v2"
    n_battles: int = Field(1, ge=1, le=50)


class StartBattleResponse(BaseModel):
    battle_ids: list[int]
    message: str


class PlayerSpec(BaseModel):
    provider: str
    model: str | None = None


class StartTournamentRequest(BaseModel):
    players: list[PlayerSpec] = Field(..., min_length=2, max_length=12)
    rounds: int = Field(1, ge=1, le=10)
    prompt_version: str = "v2"


class StartTournamentResponse(BaseModel):
    tournament_id: int
    battle_ids: list[int]
    total_battles: int
    message: str


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(db_path: Path = _DB_PATH) -> FastAPI:
    bus = EventBus()
    store = BattleStore(db_path)

    # battle_id → asyncio.Task — lets us cancel running battles
    _active_tasks: dict[int, asyncio.Task] = {}

    app = FastAPI(title="Nidozo", version="0.9.0")
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

    # -----------------------------------------------------------------------
    # REST: Leaderboard & battles
    # -----------------------------------------------------------------------

    @app.get("/api/leaderboard")
    def get_leaderboard(grouped: bool = True) -> list[dict]:
        return store.leaderboard(grouped=grouped)

    @app.get("/api/battles")
    def get_battles(limit: int = 20) -> list[dict]:
        return store.recent_battles(limit=limit)

    @app.get("/api/battles/{battle_id}")
    def get_battle(battle_id: int) -> dict:
        battle = store.get_battle(battle_id)
        if not battle:
            raise HTTPException(status_code=404, detail="Battle not found")
        return battle

    @app.post("/api/battles/{battle_id}/cancel")
    async def cancel_battle(battle_id: int) -> dict:
        """Cancel a pending or running battle."""
        # Signal the running task to stop
        task = _active_tasks.get(battle_id)
        if task and not task.done():
            task.cancel()

        cancelled = store.cancel_battle(battle_id)
        if not cancelled:
            battle = store.get_battle(battle_id)
            if not battle:
                raise HTTPException(status_code=404, detail="Battle not found")
            return {"ok": False, "message": f"Battle already {battle['status']}"}

        await bus.publish({"type": "battle_cancelled", "battle_id": battle_id})
        return {"ok": True, "message": "Battle cancelled"}

    @app.get("/api/lmstudio/models")
    async def get_lmstudio_models() -> list[str]:
        """Proxy to LM Studio's /v1/models."""
        base_url = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": "Bearer lm-studio"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as exc:
            logger.debug("LM Studio not reachable at %s: %s", base_url, exc)
            return []

    @app.get("/api/battles/{battle_id}/replay")
    def get_replay(battle_id: int) -> dict:
        """Full turn-by-turn merged state for battle replay."""
        battle = store.get_battle(battle_id)
        if not battle:
            raise HTTPException(status_code=404, detail="Battle not found")

        turns_raw = store.get_turns_with_state(battle_id)

        # Merge p1 + p2 rows into one entry per turn number
        turns_by_num: dict[int, dict] = {}
        for row in turns_raw:
            n = row["turn_number"]
            if n not in turns_by_num:
                turns_by_num[n] = {}
            state = json.loads(row["state_json"]) if row["state_json"] else None
            turns_by_num[n][row["player_role"]] = {
                "state":         state,
                "action":        row["action_chosen"],
                "parse_success": bool(row["parse_success"]),
            }

        turns = [
            {"turn": n, **turns_by_num[n]}
            for n in sorted(turns_by_num.keys())
        ]
        return {"battle": battle, "turns": turns}

    @app.get("/api/battles/{battle_id}/turns")
    def get_turns(battle_id: int) -> list[dict]:
        return store.get_turns_basic(battle_id)

    @app.get("/api/battles/{battle_id}/analysis")
    def get_analysis(battle_id: int) -> dict:
        from nidozo.analysis import analyze_battle
        turns = store.get_turns_with_state(battle_id)
        return analyze_battle(turns)

    @app.get("/api/tournaments/{tournament_id}")
    def get_tournament(tournament_id: int) -> dict:
        t = store.get_tournament(tournament_id)
        if not t:
            raise HTTPException(status_code=404, detail="Tournament not found")
        return t

    # -----------------------------------------------------------------------
    # REST: Start a single battle
    # -----------------------------------------------------------------------

    @app.post("/api/battles/start", response_model=StartBattleResponse)
    async def start_battle(
        req: StartBattleRequest,
        background_tasks: BackgroundTasks,
    ) -> StartBattleResponse:
        battle_ids = []
        for i in range(req.n_battles):
            p1_model_name = _model_name(req.p1_provider, req.p1_model or req.model)
            p2_model_name = _model_name(req.p2_provider, req.p2_model or req.model)
            p1_id = store.get_or_create_model(req.p1_provider, p1_model_name, req.prompt_version)
            p2_id = store.get_or_create_model(req.p2_provider, p2_model_name, req.prompt_version)
            bid = store.create_battle(
                f"pending-{req.p1_provider}-{req.p2_provider}-{i}",
                "gen3randombattle",
                p1_id,
                p2_id,
            )
            battle_ids.append(bid)

        background_tasks.add_task(
            _run_battles, req, battle_ids, store, bus, _active_tasks
        )
        return StartBattleResponse(
            battle_ids=battle_ids,
            message=f"Started {req.n_battles} battle(s). Connect to /ws/battles to watch.",
        )

    # -----------------------------------------------------------------------
    # REST: Start a tournament
    # -----------------------------------------------------------------------

    @app.post("/api/tournament/start", response_model=StartTournamentResponse)
    async def start_tournament(
        req: StartTournamentRequest,
        background_tasks: BackgroundTasks,
    ) -> StartTournamentResponse:
        if len(req.players) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 players")

        import itertools
        pairs = list(itertools.combinations(range(len(req.players)), 2))
        total = len(pairs) * req.rounds * 2  # each pair plays both sides per round

        # Resolve model names upfront
        player_specs = []
        for p in req.players:
            mn = _model_name(p.provider, p.model)
            player_specs.append({"provider": p.provider, "model_name": mn})

        tournament_id = store.create_tournament(
            players=player_specs,
            rounds=req.rounds,
            prompt_version=req.prompt_version,
            total_battles=total,
        )

        # Pre-create all battle records so we can return IDs immediately
        battle_ids = []
        battle_num = 0
        for (i, j) in pairs:
            for _ in range(req.rounds):
                for (a_idx, b_idx) in [(i, j), (j, i)]:
                    a = player_specs[a_idx]
                    b = player_specs[b_idx]
                    a_id = store.get_or_create_model(a["provider"], a["model_name"], req.prompt_version)
                    b_id = store.get_or_create_model(b["provider"], b["model_name"], req.prompt_version)
                    bid = store.create_battle(
                        f"tournament-{tournament_id}-{battle_num}",
                        "gen3randombattle",
                        a_id, b_id,
                        tournament_id=tournament_id,
                    )
                    battle_ids.append(bid)
                    battle_num += 1

        background_tasks.add_task(
            _run_tournament, req, tournament_id, battle_ids, player_specs, store, bus, _active_tasks
        )

        return StartTournamentResponse(
            tournament_id=tournament_id,
            battle_ids=battle_ids,
            total_battles=total,
            message=f"Tournament started: {len(req.players)} players, {req.rounds} round(s), {total} battles.",
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
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    await ws.send_text(json.dumps(event))
                except TimeoutError:
                    await ws.send_text(json.dumps({"type": "ping"}))
        except WebSocketDisconnect:
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
# Background: single-battle runner
# ---------------------------------------------------------------------------

async def _run_battles(
    req: StartBattleRequest,
    battle_ids: list[int],
    store: BattleStore,
    bus: EventBus,
    active_tasks: dict[int, asyncio.Task],
) -> None:
    from poke_env import LocalhostServerConfiguration
    _FORMAT = "gen3randombattle"
    cfg = LocalhostServerConfiguration

    for battle_id in battle_ids:
        task = asyncio.current_task()
        if task:
            active_tasks[battle_id] = task

        try:
            p1_model = req.p1_model or req.model
            p2_model = req.p2_model or req.model
            p1 = _build_streaming_player(
                req.p1_provider, p1_model, "p1",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )
            p2 = _build_streaming_player(
                req.p2_provider, p2_model, "p2",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )

            store.set_battle_status(battle_id, "running")
            await bus.publish({
                "type": "battle_start",
                "battle_id": battle_id,
                "p1": f"{req.p1_provider}/{_model_name(req.p1_provider, p1_model)}",
                "p2": f"{req.p2_provider}/{_model_name(req.p2_provider, p2_model)}",
                "format": _FORMAT,
            })

            await p1.battle_against(p2, n_battles=1)

            winner = 1 if p1.n_won_battles > 0 else (2 if p2.n_won_battles > 0 else None)
            real_tag = next(iter(p1.battles), f"battle-{battle_id}")
            battle_obj = p1.battles.get(real_tag)
            total_turns = battle_obj.turn if battle_obj else 0

            store.update_battle_tag(battle_id, real_tag)
            store.finish_battle(battle_id, winner, total_turns)
            store.set_battle_status(battle_id, "completed")

            await bus.publish({
                "type": "battle_end",
                "battle_id": battle_id,
                "battle_tag": real_tag,
                "winner": winner,
                "total_turns": total_turns,
            })

        except asyncio.CancelledError:
            logger.info("Battle %d cancelled", battle_id)
            store.cancel_battle(battle_id)
            raise
        except Exception as exc:
            logger.error("Battle %d failed: %s", battle_id, exc)
            store.set_battle_status(battle_id, "failed")
            await bus.publish({"type": "error", "battle_id": battle_id, "message": str(exc)})
        finally:
            active_tasks.pop(battle_id, None)


# ---------------------------------------------------------------------------
# Background: tournament runner
# ---------------------------------------------------------------------------

async def _run_tournament(
    req: StartTournamentRequest,
    tournament_id: int,
    battle_ids: list[int],
    player_specs: list[dict],
    store: BattleStore,
    bus: EventBus,
    active_tasks: dict[int, asyncio.Task],
) -> None:
    from poke_env import LocalhostServerConfiguration
    _FORMAT = "gen3randombattle"
    cfg = LocalhostServerConfiguration

    total = len(battle_ids)
    await bus.publish({
        "type": "tournament_start",
        "tournament_id": tournament_id,
        "players": player_specs,
        "total_battles": total,
        "rounds": req.rounds,
    })

    for battle_num, battle_id in enumerate(battle_ids, start=1):
        # Check if tournament was cancelled (any remaining battle is cancelled)
        battle_row = store.get_battle(battle_id)
        if not battle_row or battle_row["status"] == "cancelled":
            continue

        task = asyncio.current_task()
        if task:
            active_tasks[battle_id] = task

        # Resolve p1/p2 from the battle record
        battle_info = store.get_battle_players(battle_id)

        p1_label = f"{battle_info['p1_provider']}/{battle_info['p1_model']}"
        p2_label = f"{battle_info['p2_provider']}/{battle_info['p2_model']}"

        await bus.publish({
            "type": "tournament_progress",
            "tournament_id": tournament_id,
            "battle_num": battle_num,
            "total_battles": total,
            "battle_id": battle_id,
            "p1": p1_label,
            "p2": p2_label,
        })

        try:
            p1 = _build_streaming_player(
                battle_info["p1_provider"], battle_info["p1_model"], "p1",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )
            p2 = _build_streaming_player(
                battle_info["p2_provider"], battle_info["p2_model"], "p2",
                req.prompt_version, store, battle_id, bus, cfg, _FORMAT,
            )

            store.set_battle_status(battle_id, "running")
            await bus.publish({
                "type": "battle_start",
                "battle_id": battle_id,
                "tournament_id": tournament_id,
                "p1": p1_label,
                "p2": p2_label,
                "format": _FORMAT,
            })

            await p1.battle_against(p2, n_battles=1)

            winner = 1 if p1.n_won_battles > 0 else (2 if p2.n_won_battles > 0 else None)
            real_tag = next(iter(p1.battles), f"battle-{battle_id}")
            battle_obj = p1.battles.get(real_tag)
            total_turns = battle_obj.turn if battle_obj else 0

            store.update_battle_tag(battle_id, real_tag)
            store.finish_battle(battle_id, winner, total_turns)
            store.set_battle_status(battle_id, "completed")

            await bus.publish({
                "type": "battle_end",
                "battle_id": battle_id,
                "tournament_id": tournament_id,
                "winner": winner,
                "total_turns": total_turns,
            })

        except asyncio.CancelledError:
            logger.info("Tournament %d cancelled at battle %d", tournament_id, battle_id)
            store.cancel_battle(battle_id)
            store.finish_tournament(tournament_id, status="cancelled")
            await bus.publish({
                "type": "tournament_cancelled",
                "tournament_id": tournament_id,
                "battles_completed": battle_num - 1,
            })
            raise
        except Exception as exc:
            logger.error("Tournament %d battle %d failed: %s", tournament_id, battle_id, exc)
            store.set_battle_status(battle_id, "failed")
            await bus.publish({"type": "error", "battle_id": battle_id, "message": str(exc)})
        finally:
            active_tasks.pop(battle_id, None)

    store.finish_tournament(tournament_id, status="completed")
    leaderboard = store.leaderboard()
    await bus.publish({
        "type": "tournament_end",
        "tournament_id": tournament_id,
        "leaderboard": leaderboard,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

    use_json_mode = prompt_version == "v2" and provider in ("lmstudio", "openai")

    if provider == "anthropic":
        backend = AnthropicBackend(
            model=model or "claude-sonnet-4-6",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    elif provider == "openai":
        backend = OpenAIBackend(
            model=model or "gpt-4o",
            api_key=os.environ.get("OPENAI_API_KEY"),
            json_mode=use_json_mode,
        )
    else:  # lmstudio
        backend = OpenAIBackend(
            model=model or os.environ.get("LM_STUDIO_MODEL", "local-model"),
            api_key="lm-studio",
            base_url=os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
            json_mode=use_json_mode,
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
