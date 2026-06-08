"""
Battle state serializer.

Converts a poke-env Battle into a structured dict suitable for rendering into
an LLM prompt. Hidden-information rules are enforced here:

  - Own Pokémon: full detail (moves + PP, exact HP, stats, item, ability, boosts, status).
  - Opponent Pokémon: only what has been legitimately revealed in this battle
    (moves used, HP%, status, visible boosts, types from Pokédex). Never exact
    HP, never unrevealed moves/items/ability.

Treat any leak of opponent hidden info as a correctness bug.
"""

from __future__ import annotations

from typing import Any

from poke_env.battle import AbstractBattle, Move, Pokemon

from nidozo.battle.heuristics import score_actions

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def serialize_battle(battle: AbstractBattle) -> dict[str, Any]:
    """Return a structured dict representing the current battle state.

    The returned dict is safe to render into either player's prompt — it
    encodes perspective-correct information for the player whose turn it is.
    """
    return {
        "turn": battle.turn,
        "format": battle.format,
        "weather": _serialize_weather(battle),
        "fields": _serialize_fields(battle),
        "my_side_conditions": _serialize_side_conditions(battle.side_conditions),
        "opponent_side_conditions": _serialize_side_conditions(
            battle.opponent_side_conditions
        ),
        "my_active": _serialize_own_pokemon(battle.active_pokemon),
        "my_team": [
            _serialize_own_pokemon(p)
            for p in battle.team.values()
            if not p.active
        ],
        "opponent_active": _serialize_opponent_pokemon(battle.opponent_active_pokemon),
        "opponent_team": [
            _serialize_opponent_pokemon(p)
            for p in battle.opponent_team.values()
            if not p.active
        ],
        "opponent_team_size_seen": len(battle.opponent_team),
        "available_moves": [_serialize_move(m) for m in battle.available_moves],
        "available_switches": [p.species for p in battle.available_switches],
        "force_switch": battle.force_switch,
        "heuristics": score_actions(battle),
        "opponent_threat_map": _compute_threat_map(battle),
        # recent_events is injected by LLMPlayer (stateful, not derivable from
        # a single battle snapshot). Absent here; always present in prompts.
        "recent_events": [],
    }


# ---------------------------------------------------------------------------
# Own Pokémon — full information
# ---------------------------------------------------------------------------

def _serialize_own_pokemon(mon: Pokemon | None) -> dict[str, Any] | None:
    if mon is None:
        return None
    moves = {
        name: _serialize_move(m) for name, m in mon.moves.items()
    }
    return {
        "species": mon.species,
        "level": mon.level,
        "types": [t.name for t in mon.types],
        "hp_fraction": round(mon.current_hp_fraction, 3),
        "fainted": mon.fainted,
        "status": mon.status.name if mon.status else None,
        "boosts": {k: v for k, v in mon.boosts.items() if v != 0},
        "item": mon.item,
        "ability": mon.ability,
        "base_stats": mon.base_stats,
        "moves": moves,
        "effects": [e.name for e in mon.effects],
    }


# ---------------------------------------------------------------------------
# Opponent Pokémon — revealed information only
# ---------------------------------------------------------------------------

def _serialize_opponent_pokemon(mon: Pokemon | None) -> dict[str, Any] | None:
    if mon is None:
        return None
    # mon.moves only contains moves the opponent has *used* — poke-env tracks
    # this for us. We do NOT include possible_abilities or estimated stats.
    revealed_moves = {name: _serialize_move_basic(m) for name, m in mon.moves.items()}
    return {
        "species": mon.species,
        "level": mon.level,
        "types": [t.name for t in mon.types],
        "hp_fraction": round(mon.current_hp_fraction, 3),
        "fainted": mon.fainted,
        "status": mon.status.name if mon.status else None,
        "boosts": {k: v for k, v in mon.boosts.items() if v != 0},
        # item/ability: None until poke-env registers them as legitimately revealed.
        # poke-env can return "unknown" as a sentinel — treat that as unrevealed.
        "item": mon.item if mon.item not in (None, "unknown") else None,
        "ability": mon.ability if mon.ability not in (None, "unknown") else None,
        "revealed_moves": revealed_moves,
        # Explicit count so the prompt can show "N/4 moves revealed" without
        # the model having to count dictionary entries itself.
        "moves_revealed": len(mon.moves),
    }


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

def _safe_priority(move: Move) -> int:
    """Return move priority, defaulting to 0 for pseudo-moves like 'recharge'."""
    try:
        return move.priority
    except KeyError:
        return 0


def _serialize_move(move: Move) -> dict[str, Any]:
    try:
        return {
            "id": move.id,
            "type": move.type.name,
            "category": move.category.name,
            "base_power": move.base_power,
            "accuracy": move.accuracy,
            "pp": move.current_pp,
            "max_pp": move.max_pp,
            "priority": _safe_priority(move),
        }
    except (KeyError, AttributeError):
        # Fallback for pseudo-moves (e.g. 'recharge') that lack full data
        return {
            "id": move.id,
            "type": "NORMAL",
            "category": "STATUS",
            "base_power": 0,
            "accuracy": True,
            "pp": 1,
            "max_pp": 1,
            "priority": 0,
        }


def _serialize_move_basic(move: Move) -> dict[str, Any]:
    """Opponent moves: omit PP (we don't track it for opponents)."""
    try:
        return {
            "id": move.id,
            "type": move.type.name,
            "category": move.category.name,
            "base_power": move.base_power,
            "accuracy": move.accuracy,
            "priority": _safe_priority(move),
        }
    except (KeyError, AttributeError):
        return {"id": move.id, "type": "NORMAL", "category": "STATUS",
                "base_power": 0, "accuracy": True, "priority": 0}


# ---------------------------------------------------------------------------
# Opponent threat map — which of YOUR mons each revealed opponent threatens
# ---------------------------------------------------------------------------

def _compute_threat_map(battle: AbstractBattle) -> list[dict[str, Any]]:
    """For each revealed opponent mon, list your non-fainted mons it threatens.

    "Threatens" means at least one of the opponent's types deals ≥2× damage to
    that mon.  Also records mons that resist all of the opponent's types (≤0.5×).
    This is type-chart only — it does not account for moveset (the opponent may
    not have a STAB move for every type it has).
    """
    result: list[dict[str, Any]] = []

    # All YOUR mons (active + bench, not fainted)
    your_mons = [
        m for m in battle.team.values()
        if not m.fainted
    ]
    if not your_mons:
        return result

    # All REVEALED opponent mons (active + bench), deduped.
    # opponent_team already contains the active mon, so iterating both would
    # double-count it and produce duplicate threat-map entries.
    opp_mons = [
        m for m in battle.opponent_team.values()
        if m is not None and not m.fainted
    ]

    for opp in opp_mons:
        opp_types = opp.types
        threatens: list[str] = []
        resists: list[str] = []

        for own in your_mons:
            try:
                # Max damage multiplier from any of opponent's STAB types
                max_mult = max(
                    (own.damage_multiplier(t) for t in opp_types),
                    default=1.0,
                )
                if max_mult >= 2.0:
                    threatens.append(own.species)
                elif max_mult <= 0.5:
                    resists.append(own.species)
            except Exception:  # noqa: BLE001
                pass

        result.append({
            "species": opp.species,
            "threatens": threatens,
            "resists": resists,
        })

    return result


# ---------------------------------------------------------------------------
# Field / weather / side conditions
# ---------------------------------------------------------------------------

def _serialize_weather(battle: AbstractBattle) -> str | None:
    if not battle.weather:
        return None
    # weather is a Dict[Weather, int] where int is turns remaining
    weather_item = next(iter(battle.weather.items()))
    return weather_item[0].name


def _serialize_fields(battle: AbstractBattle) -> list[str]:
    return [field.name for field in battle.fields]


def _serialize_side_conditions(conditions: dict[Any, Any]) -> list[str]:
    return [cond.name for cond in conditions]
