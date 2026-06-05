"""
Heuristic scorer — produces advisory context for each legal action each turn.

This is NOT a decision function. It computes signals that the LLM can reason
over: type matchups, rough damage estimates, priority, status effects, and
switch type matchups. The model chooses freely; this just surfaces structure.

Damage estimates use base stats (public Pokédex data) for both sides and
assume level 100. They are deliberately rough — enough to flag obvious
advantages, not a precise damage calculator.
"""

from __future__ import annotations

from typing import Any

from poke_env.battle import AbstractBattle, Pokemon
from poke_env.battle.move import Move
from poke_env.battle.move_category import MoveCategory

# Stat stage multipliers: stage -6..+6
_STAGE_MULT = {
    -6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
    0: 1.0,
    1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2,
}


def score_actions(battle: AbstractBattle) -> dict[str, Any]:
    """Return scored move and switch options for the current battle state."""
    own = battle.active_pokemon
    opp = battle.opponent_active_pokemon

    move_scores = [
        _score_move(move, own, opp, battle)
        for move in battle.available_moves
    ]
    switch_scores = [
        _score_switch(mon, opp, battle)
        for mon in battle.available_switches
    ]

    return {"move_scores": move_scores, "switch_scores": switch_scores}


# ---------------------------------------------------------------------------
# Move scoring
# ---------------------------------------------------------------------------

def _score_move(
    move: Move,
    own: Pokemon | None,
    opp: Pokemon | None,
    battle: AbstractBattle,
) -> dict[str, Any]:
    try:
        priority = move.priority
    except KeyError:
        priority = 0  # pseudo-moves like 'recharge' have no priority entry

    score: dict[str, Any] = {
        "move_id": move.id,
        "type_multiplier": None,
        "effectiveness_label": "unknown",
        "estimated_damage_pct": None,
        "priority": priority,
        "is_status": move.category == MoveCategory.STATUS,
        "notes": [],
    }

    if move.category == MoveCategory.STATUS:
        score["effectiveness_label"] = "status"
        _annotate_status_move(move, score)
        return score

    if opp is None:
        return score

    # Type effectiveness
    mult = opp.damage_multiplier(move)
    score["type_multiplier"] = mult
    score["effectiveness_label"] = _effectiveness_label(mult)

    if mult == 0.0:
        score["notes"].append("immune — will deal no damage")
        score["estimated_damage_pct"] = "0%"
        return score

    # Rough damage estimate: Gen 3 damage formula simplified for advisory use.
    # actual_stat uses our real stats when available, base_stats as fallback.
    if own is not None:
        own_stats = own.stats or {}
        is_physical = move.category == MoveCategory.PHYSICAL
        atk_key = "atk" if is_physical else "spa"
        def_key = "def" if is_physical else "spd"

        own_atk_base = own_stats.get(atk_key) or own.base_stats.get(atk_key, 80)
        opp_def_base = opp.base_stats.get(def_key, 80)

        # Apply visible stat stages
        own_atk_stage = own.boosts.get(atk_key, 0)
        opp_def_stage = opp.boosts.get(def_key, 0)
        own_atk = own_atk_base * _STAGE_MULT.get(own_atk_stage, 1.0)
        opp_def = opp_def_base * _STAGE_MULT.get(opp_def_stage, 1.0)

        # Simplified Gen 3 formula (level 100, no crit, no random roll)
        raw = ((42 * move.base_power * own_atk / opp_def) / 50 + 2) * mult

        # Express as % of a typical opponent HP pool (base HP × ~2 for level 100 approx)
        opp_hp_approx = opp.base_stats.get("hp", 80) * 2 + 110
        pct = min(raw / opp_hp_approx * 100, 999)
        score["estimated_damage_pct"] = f"~{pct:.0f}%"

        if pct >= 100:
            score["notes"].append("likely OHKO")
        elif pct >= 50:
            score["notes"].append("likely 2HKO")

    if priority > 0:
        score["notes"].append(f"priority +{priority} — moves before most attacks")

    # STAB
    if own is not None and move.type in own.types:
        score["notes"].append("STAB")

    return score


def _annotate_status_move(move: Move, score: dict[str, Any]) -> None:
    move_id = move.id.lower()
    if any(x in move_id for x in ("sleep", "spore", "hypnosis", "sing", "yawn", "lovecaster", "darkv")):
        score["notes"].append("inflicts Sleep")
    elif any(x in move_id for x in ("toxic", "poison", "poisonpowder")):
        score["notes"].append("inflicts Poison/Toxic")
    elif any(x in move_id for x in ("thunderwave", "stun", "glare", "nuzzle")):
        score["notes"].append("inflicts Paralysis")
    elif any(x in move_id for x in ("willowisp", "burnup")):
        score["notes"].append("inflicts Burn")
    elif any(x in move_id for x in ("swordsdance", "nastyplot", "calmmind", "dragondance", "bulkup", "workup")):
        score["notes"].append("boosts own stats")
    elif any(x in move_id for x in ("screech", "charm", "growl", "leer", "tickle")):
        score["notes"].append("drops opponent stats")


def _effectiveness_label(mult: float) -> str:
    if mult == 0.0:
        return "immune (0×)"
    if mult >= 4.0:
        return "super effective (4×)"
    if mult >= 2.0:
        return "super effective (2×)"
    if mult == 1.0:
        return "neutral (1×)"
    if mult <= 0.25:
        return "not very effective (0.25×)"
    return "not very effective (0.5×)"


# ---------------------------------------------------------------------------
# Switch scoring
# ---------------------------------------------------------------------------

def _score_switch(
    incoming: Pokemon,
    opp: Pokemon | None,
    battle: AbstractBattle,
) -> dict[str, Any]:
    score: dict[str, Any] = {
        "species": incoming.species,
        "hp_fraction": round(incoming.current_hp_fraction, 3),
        "notes": [],
    }

    if opp is None:
        return score

    # How well does the incoming mon's typing hold up against the opponent?
    # Check resistance to opponent's revealed move types and STAB types.
    opp_threat_types = {m.type for m in opp.moves.values() if m.category != MoveCategory.STATUS}
    # Also include opponent STAB types as likely threats even if not yet revealed
    opp_threat_types.update(opp.types)

    resists, weak_to, immune_to = [], [], []
    for t in opp_threat_types:
        mult = incoming.damage_multiplier(t)
        if mult == 0.0:
            immune_to.append(t.name)
        elif mult < 1.0:
            resists.append(t.name)
        elif mult > 1.0:
            weak_to.append(t.name)

    if immune_to:
        score["notes"].append(f"immune to {', '.join(immune_to)}")
    if resists:
        score["notes"].append(f"resists {', '.join(resists)}")
    if weak_to:
        score["notes"].append(f"weak to {', '.join(weak_to)}")

    # Does the incoming mon have a type advantage offensively?
    for t in incoming.types:
        opp_mult = opp.damage_multiplier(t)
        if opp_mult >= 2.0:
            score["notes"].append(f"{t.name} is super effective vs opponent")

    return score
