"""Background battle and tournament runners."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nidozo.api.helpers import _build_backend, _build_streaming_player, _model_name
from nidozo.api.models import StartBattleRequest, StartTournamentRequest

logger = logging.getLogger(__name__)


async def run_battles(
    req: StartBattleRequest,
    battle_ids: list[int],
    store: Any,
    bus: Any,
    active_tasks: dict[int, asyncio.Task[None]],
) -> None:
    """Run one or more battles sequentially as a background task."""
    from poke_env import LocalhostServerConfiguration

    from nidozo.battle.tiers import TIER_TO_FORMAT

    do_draft = req.tier != "random" and req.draft
    showdown_format = (
        "gen3randombattle" if req.tier == "random"
        else TIER_TO_FORMAT.get(req.tier, "gen3ou")
    )
    effective_prompt = "v3" if do_draft else req.prompt_version
    cfg = LocalhostServerConfiguration

    for battle_id in battle_ids:
        task = asyncio.current_task()
        if task:
            active_tasks[battle_id] = task

        try:
            p1_model = req.p1_model or req.model
            p2_model = req.p2_model or req.model

            model_ids = store.get_player_model_ids(battle_id)
            p1_id, p2_id = model_ids if model_ids else (None, None)
            p1_lessons = (
                [r["content"] for r in store.get_lessons(p1_id)]
                if p1_id and req.p1_provider != "random" else None
            )
            p2_lessons = (
                [r["content"] for r in store.get_lessons(p2_id)]
                if p2_id and req.p2_provider != "random" else None
            )

            p1_team: str | None = None
            p2_team: str | None = None
            p1_team_id: int | None = None
            p2_team_id: int | None = None

            if do_draft and p1_id is not None and req.p1_provider != "random":
                await bus.publish({
                    "type": "draft_start",
                    "player_role": "p1",
                    "tier": req.tier,
                    "battle_id": battle_id,
                })
                p1_backend = _build_backend(req.p1_provider, p1_model)
                p1_draft = await run_draft_phase(p1_backend, p1_id, req.tier, store, bus, "p1")
                p1_team = p1_draft["team_string"]
                p1_team_id = p1_draft["team_id"]

            if do_draft and p2_id is not None and req.p2_provider != "random":
                await bus.publish({
                    "type": "draft_start",
                    "player_role": "p2",
                    "tier": req.tier,
                    "battle_id": battle_id,
                })
                p2_backend = _build_backend(req.p2_provider, p2_model)
                p2_draft = await run_draft_phase(p2_backend, p2_id, req.tier, store, bus, "p2")
                p2_team = p2_draft["team_string"]
                p2_team_id = p2_draft["team_id"]

            if do_draft:
                store.set_battle_teams(battle_id, p1_team_id, p2_team_id, req.tier)

            p1 = _build_streaming_player(
                req.p1_provider, p1_model, "p1",
                effective_prompt, store, battle_id, bus, cfg, showdown_format,
                lessons=p1_lessons,
                team=p1_team,
                coach_provider=req.p1_coach_provider,
                coach_model=req.p1_coach_model,
            )
            p2 = _build_streaming_player(
                req.p2_provider, p2_model, "p2",
                effective_prompt, store, battle_id, bus, cfg, showdown_format,
                lessons=p2_lessons,
                team=p2_team,
                coach_provider=req.p2_coach_provider,
                coach_model=req.p2_coach_model,
            )

            store.set_battle_status(battle_id, "running")
            await bus.publish({
                "type": "battle_start",
                "battle_id": battle_id,
                "p1": f"{req.p1_provider}/{_model_name(req.p1_provider, p1_model)}",
                "p2": f"{req.p2_provider}/{_model_name(req.p2_provider, p2_model)}",
                "format": showdown_format,
                "tier": req.tier,
                "drafted": do_draft,
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

            turns = store.get_turns_basic(battle_id)
            p2_label = f"{req.p2_provider}/{_model_name(req.p2_provider, p2_model)}"
            p1_label = f"{req.p1_provider}/{_model_name(req.p1_provider, p1_model)}"
            _: asyncio.Task[None] = asyncio.create_task(generate_and_store_lessons(
                store, battle_id, winner, total_turns, turns,
                p1_provider=req.p1_provider, p1_model=p1_model, p1_id=p1_id, p1_opponent=p2_label,
                p2_provider=req.p2_provider, p2_model=p2_model, p2_id=p2_id, p2_opponent=p1_label,
            ))

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


async def run_tournament(
    req: StartTournamentRequest,
    tournament_id: int,
    battle_ids: list[int],
    player_specs: list[dict[str, Any]],
    store: Any,
    bus: Any,
    active_tasks: dict[int, asyncio.Task[None]],
) -> None:
    """Run all battles in a tournament sequentially as a background task."""
    from poke_env import LocalhostServerConfiguration

    from nidozo.battle.tiers import TIER_TO_FORMAT

    do_draft = req.tier != "random" and req.draft
    showdown_format = (
        "gen3randombattle" if req.tier == "random"
        else TIER_TO_FORMAT.get(req.tier, "gen3ou")
    )
    effective_prompt = "v3" if do_draft else req.prompt_version
    cfg = LocalhostServerConfiguration

    total = len(battle_ids)
    await bus.publish({
        "type": "tournament_start",
        "tournament_id": tournament_id,
        "players": player_specs,
        "total_battles": total,
        "rounds": req.rounds,
        "tier": req.tier,
    })

    # Build a lookup so each battle's p1/p2 can find their coach config.
    coach_lookup: dict[tuple[str, str], tuple[str | None, str | None]] = {
        (ps["provider"], ps["model_name"]): (
            ps.get("coach_provider"), ps.get("coach_model")
        )
        for ps in player_specs
    }

    for battle_num, battle_id in enumerate(battle_ids, start=1):
        battle_row = store.get_battle(battle_id)
        if not battle_row or battle_row["status"] == "cancelled":
            continue

        task = asyncio.current_task()
        if task:
            active_tasks[battle_id] = task

        battle_info = store.get_battle_players(battle_id)
        if battle_info is None:
            logger.error(
                "Tournament %d: no player info for battle %d — skipping",
                tournament_id, battle_id,
            )
            continue

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
            model_ids = store.get_player_model_ids(battle_id)
            t_p1_id, t_p2_id = model_ids if model_ids else (None, None)
            t_p1_prov, t_p2_prov = battle_info["p1_provider"], battle_info["p2_provider"]
            t_p1_lessons = (
                [r["content"] for r in store.get_lessons(t_p1_id)]
                if t_p1_id and t_p1_prov != "random" else None
            )
            t_p2_lessons = (
                [r["content"] for r in store.get_lessons(t_p2_id)]
                if t_p2_id and t_p2_prov != "random" else None
            )

            t_p1_team: str | None = None
            t_p2_team: str | None = None
            t_p1_team_id: int | None = None
            t_p2_team_id: int | None = None

            if do_draft and t_p1_id is not None and t_p1_prov != "random":
                await bus.publish({
                    "type": "draft_start",
                    "player_role": "p1",
                    "tier": req.tier,
                    "battle_id": battle_id,
                    "tournament_id": tournament_id,
                })
                p1_backend = _build_backend(t_p1_prov, battle_info["p1_model"])
                p1_draft_r = await run_draft_phase(
                    p1_backend, t_p1_id, req.tier, store, bus, "p1"
                )
                t_p1_team = p1_draft_r["team_string"]
                t_p1_team_id = p1_draft_r["team_id"]

            if do_draft and t_p2_id is not None and t_p2_prov != "random":
                await bus.publish({
                    "type": "draft_start",
                    "player_role": "p2",
                    "tier": req.tier,
                    "battle_id": battle_id,
                    "tournament_id": tournament_id,
                })
                p2_backend = _build_backend(t_p2_prov, battle_info["p2_model"])
                p2_draft_r = await run_draft_phase(
                    p2_backend, t_p2_id, req.tier, store, bus, "p2"
                )
                t_p2_team = p2_draft_r["team_string"]
                t_p2_team_id = p2_draft_r["team_id"]

            if do_draft:
                store.set_battle_teams(battle_id, t_p1_team_id, t_p2_team_id, req.tier)

            t_p1_coach_prov, t_p1_coach_model = coach_lookup.get(
                (t_p1_prov, battle_info["p1_model"]), (None, None)
            )
            t_p2_coach_prov, t_p2_coach_model = coach_lookup.get(
                (t_p2_prov, battle_info["p2_model"]), (None, None)
            )

            p1 = _build_streaming_player(
                t_p1_prov, battle_info["p1_model"], "p1",
                effective_prompt, store, battle_id, bus, cfg, showdown_format,
                lessons=t_p1_lessons,
                team=t_p1_team,
                coach_provider=t_p1_coach_prov,
                coach_model=t_p1_coach_model,
            )
            p2 = _build_streaming_player(
                t_p2_prov, battle_info["p2_model"], "p2",
                effective_prompt, store, battle_id, bus, cfg, showdown_format,
                lessons=t_p2_lessons,
                team=t_p2_team,
                coach_provider=t_p2_coach_prov,
                coach_model=t_p2_coach_model,
            )

            store.set_battle_status(battle_id, "running")
            await bus.publish({
                "type": "battle_start",
                "battle_id": battle_id,
                "tournament_id": tournament_id,
                "p1": p1_label,
                "p2": p2_label,
                "format": showdown_format,
                "tier": req.tier,
                "drafted": do_draft,
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

            standings = store.get_tournament_standings(tournament_id)
            await bus.publish({
                "type": "tournament_standings",
                "tournament_id": tournament_id,
                "standings": standings,
                "battle_num": battle_num,
                "total_battles": total,
            })

            turns = store.get_turns_basic(battle_id)
            _t: asyncio.Task[None] = asyncio.create_task(generate_and_store_lessons(
                store, battle_id, winner, total_turns, turns,
                p1_provider=t_p1_prov, p1_model=battle_info["p1_model"],
                p1_id=t_p1_id, p1_opponent=p2_label,
                p2_provider=t_p2_prov, p2_model=battle_info["p2_model"],
                p2_id=t_p2_id, p2_opponent=p1_label,
            ))

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


async def run_draft_phase(
    backend: Any,
    model_id: int,
    tier: str,
    store: Any,
    bus: Any,
    player_role: str,
) -> dict[str, Any]:
    """Run the draft for one player and return {team_string, team_id}."""
    from nidozo.battle.draft import run_draft

    result = await run_draft(
        backend=backend,
        model_id=model_id,
        tier=tier,
        store=store,
        bus=bus,
        player_role=player_role,
        prompt_version="v3",
    )
    return {"team_string": result.team_string, "team_id": result.team_id}


async def generate_and_store_lessons(
    store: Any,
    battle_id: int,
    winner: int | None,
    total_turns: int,
    turns: list[dict[str, Any]],
    *,
    p1_provider: str,
    p1_model: str | None,
    p1_id: int | None,
    p1_opponent: str,
    p2_provider: str,
    p2_model: str | None,
    p2_id: int | None,
    p2_opponent: str,
) -> None:
    """Generate and persist post-battle lessons for both LLM players.

    Runs as a fire-and-forget asyncio task.  Errors are logged but never
    propagate — the battle pipeline must not be affected.
    """
    from nidozo.analysis import analyze_battle
    from nidozo.analysis.analyzer import _load_species_data
    from nidozo.llm.lesson_generator import generate_lesson

    turns_with_state = store.get_turns_with_state(battle_id)
    p1_team, p2_team = store.get_battle_teams(battle_id)
    p1_ids: list[str] | None = p1_team.get("pokemon") if p1_team else None
    p2_ids: list[str] | None = p2_team.get("pokemon") if p2_team else None
    sd = _load_species_data() if (p1_ids or p2_ids) else None
    try:
        analysis: dict[str, Any] | None = (
            analyze_battle(turns_with_state, p1_team_ids=p1_ids, p2_team_ids=p2_ids, species_data=sd)
            if turns_with_state else None
        )
    except Exception as exc:
        logger.warning(
            "Analysis failed for battle %d (lessons will proceed without it): %s",
            battle_id, exc,
        )
        analysis = None

    for provider, model, model_id, role, opponent in (
        (p1_provider, p1_model, p1_id, "p1", p1_opponent),
        (p2_provider, p2_model, p2_id, "p2", p2_opponent),
    ):
        if provider == "random" or model_id is None:
            continue
        try:
            lesson_backend = _build_backend(provider, model, json_mode=False)
            lesson = await generate_lesson(
                backend=lesson_backend,
                player_role=role,
                winner=winner,
                total_turns=total_turns,
                opponent_label=opponent,
                turns=turns,
                analysis=analysis,
            )
            if lesson:
                store.create_lesson(model_id, battle_id, lesson)
                logger.info(
                    "Lesson stored for model %d (battle %d, role=%s): %s…",
                    model_id, battle_id, role, lesson[:80],
                )
        except Exception as exc:
            logger.error(
                "Failed to generate/store lesson for model %d battle %d: %s",
                model_id, battle_id, exc,
            )


async def run_bracket_tournament(
    req: StartTournamentRequest,
    tournament_id: int,
    player_specs: list[dict[str, Any]],
    store: Any,
    bus: Any,
    active_tasks: dict[int, asyncio.Task[None]],
) -> None:
    """Run a single-elim or double-elim tournament round by round.

    Unlike round-robin (where all battles are pre-created), bracket
    tournaments create battles lazily — we only know future matchups
    after earlier rounds resolve.
    """
    from poke_env import LocalhostServerConfiguration

    from nidozo.battle.tiers import TIER_TO_FORMAT
    from nidozo.tournament.bracket import (
        build_bracket,
        get_pending_matches,
        record_result,
        resolve_seed,
    )

    do_draft = req.tier != "random" and req.draft
    showdown_format = (
        "gen3randombattle" if req.tier == "random"
        else TIER_TO_FORMAT.get(req.tier, "gen3ou")
    )
    effective_prompt = "v3" if do_draft else req.prompt_version
    cfg = LocalhostServerConfiguration

    # Build initial bracket state
    bracket_state = build_bracket(player_specs, req.tournament_format)
    store.update_bracket_state(tournament_id, bracket_state)

    # Estimate total battles: SE = n-1, DE = 2n-2 or 2n-1 (approx)
    n = len(player_specs)
    if req.tournament_format == "single_elim":
        estimated_total = n - 1
    else:
        estimated_total = 2 * n - 1  # may vary with bracket reset

    await bus.publish({
        "type": "tournament_start",
        "tournament_id": tournament_id,
        "players": player_specs,
        "total_battles": estimated_total,
        "rounds": 0,
        "tier": req.tier,
        "tournament_format": req.tournament_format,
    })
    await bus.publish({
        "type": "bracket_update",
        "tournament_id": tournament_id,
        "bracket": bracket_state,
    })

    battle_num = 0
    cancelled = False
    match_failed = False

    try:
        while True:
            pending = get_pending_matches(bracket_state)
            if not pending:
                break

            for match in pending:
                match_id = match["match_id"]
                p1_seed  = match["p1_seed"]
                p2_seed  = match["p2_seed"]
                p1_info  = resolve_seed(bracket_state, p1_seed)
                p2_info  = resolve_seed(bracket_state, p2_seed)

                if p1_info is None or p2_info is None:
                    # Bracket invariant violated — a pending match has unresolvable
                    # seeds. Continuing would spin forever; abort the tournament.
                    logger.error(
                        "Bracket %d: match %s seed lookup failed (p1=%s p2=%s) — "
                        "aborting tournament",
                        tournament_id, match_id, p1_seed, p2_seed,
                    )
                    match_failed = True
                    break

                p1_prov  = p1_info["provider"]
                p1_model = p1_info["model_name"]
                p2_prov  = p2_info["provider"]
                p2_model = p2_info["model_name"]

                p1_label = f"{p1_prov}/{p1_model}"
                p2_label = f"{p2_prov}/{p2_model}"
                battle_num += 1

                # Create battle row
                p1_db_id = store.get_or_create_model(p1_prov, p1_model, effective_prompt)
                p2_db_id = store.get_or_create_model(p2_prov, p2_model, effective_prompt)
                battle_id = store.create_battle(
                    f"bracket-{tournament_id}-{match_id}",
                    showdown_format, p1_db_id, p2_db_id,
                    tournament_id=tournament_id,
                )
                match["battle_id"] = battle_id
                match["status"] = "running"
                store.update_bracket_state(tournament_id, bracket_state)

                task = asyncio.current_task()
                if task:
                    active_tasks[battle_id] = task

                await bus.publish({
                    "type": "tournament_progress",
                    "tournament_id": tournament_id,
                    "battle_num": battle_num,
                    "total_battles": estimated_total,
                    "battle_id": battle_id,
                    "p1": p1_label,
                    "p2": p2_label,
                    "match_id": match_id,
                })

                try:
                    t_p1_id = p1_db_id
                    t_p2_id = p2_db_id
                    t_p1_lessons = (
                        [r["content"] for r in store.get_lessons(t_p1_id)]
                        if p1_prov != "random" else None
                    )
                    t_p2_lessons = (
                        [r["content"] for r in store.get_lessons(t_p2_id)]
                        if p2_prov != "random" else None
                    )

                    p1 = _build_streaming_player(
                        p1_prov, p1_model, "p1",
                        effective_prompt, store, battle_id, bus, cfg, showdown_format,
                        lessons=t_p1_lessons,
                    )
                    p2 = _build_streaming_player(
                        p2_prov, p2_model, "p2",
                        effective_prompt, store, battle_id, bus, cfg, showdown_format,
                        lessons=t_p2_lessons,
                    )

                    store.set_battle_status(battle_id, "running")
                    await bus.publish({
                        "type": "battle_start",
                        "battle_id": battle_id,
                        "tournament_id": tournament_id,
                        "p1": p1_label,
                        "p2": p2_label,
                        "format": showdown_format,
                        "tier": req.tier,
                        "drafted": do_draft,
                        "match_id": match_id,
                    })

                    await p1.battle_against(p2, n_battles=1)

                    winner_slot = 1 if p1.n_won_battles > 0 else 2
                    real_tag = next(iter(p1.battles), f"battle-{battle_id}")
                    battle_obj = p1.battles.get(real_tag)
                    total_turns = battle_obj.turn if battle_obj else 0

                    store.update_battle_tag(battle_id, real_tag)
                    store.finish_battle(battle_id, winner_slot, total_turns)
                    store.set_battle_status(battle_id, "completed")

                    await bus.publish({
                        "type": "battle_end",
                        "battle_id": battle_id,
                        "tournament_id": tournament_id,
                        "winner": winner_slot,
                        "total_turns": total_turns,
                        "match_id": match_id,
                    })

                    # Advance bracket
                    record_result(bracket_state, match_id, winner_slot, battle_id)
                    store.update_bracket_state(tournament_id, bracket_state)

                    await bus.publish({
                        "type": "bracket_update",
                        "tournament_id": tournament_id,
                        "bracket": bracket_state,
                    })

                    turns = store.get_turns_basic(battle_id)
                    _t: asyncio.Task[None] = asyncio.create_task(
                        generate_and_store_lessons(
                            store, battle_id, winner_slot, total_turns, turns,
                            p1_provider=p1_prov, p1_model=p1_model,
                            p1_id=t_p1_id, p1_opponent=p2_label,
                            p2_provider=p2_prov, p2_model=p2_model,
                            p2_id=t_p2_id, p2_opponent=p1_label,
                        )
                    )

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Bracket %d match %s failed: %s", tournament_id, match_id, exc
                    )
                    # Update in-memory bracket state so the match isn't left as
                    # "running" — that would make get_pending_matches return nothing,
                    # and the while loop would break and call finish_tournament with
                    # champion_seed=None (silently completing a broken tournament).
                    match["status"] = "failed"
                    store.set_battle_status(battle_id, "failed")
                    store.update_bracket_state(tournament_id, bracket_state)
                    await bus.publish({
                        "type": "error", "battle_id": battle_id, "message": str(exc),
                    })
                    match_failed = True
                finally:
                    active_tasks.pop(battle_id, None)

                if match_failed:
                    break  # exit inner for-loop immediately

            if match_failed:
                break  # exit while True

            # Check if champion is known
            if bracket_state.get("champion_seed") is not None:
                break

    except asyncio.CancelledError:
        logger.info("Bracket tournament %d cancelled at battle %d", tournament_id, battle_num)
        store.finish_tournament(tournament_id, status="cancelled")
        await bus.publish({
            "type": "tournament_cancelled",
            "tournament_id": tournament_id,
            "battles_completed": battle_num,
        })
        cancelled = True
        raise

    if not cancelled:
        if match_failed:
            store.finish_tournament(tournament_id, status="failed")
            await bus.publish({
                "type": "tournament_failed",
                "tournament_id": tournament_id,
                "battles_completed": battle_num,
                "bracket": bracket_state,
            })
        else:
            store.finish_tournament(tournament_id, status="completed")
            champion_seed = bracket_state.get("champion_seed")
            champion_info = resolve_seed(bracket_state, champion_seed) if champion_seed else None
            leaderboard = store.leaderboard()
            await bus.publish({
                "type": "tournament_end",
                "tournament_id": tournament_id,
                "leaderboard": leaderboard,
                "bracket": bracket_state,
                "champion": champion_info,
            })
