"""
Post-game battle analyzer.

For each logged turn (where state_json was captured), compares the model's
chosen action to the heuristic rankings to produce a decision quality label:

  optimal    — chose the heuristic top-ranked move
  good       — chose the 2nd or 3rd ranked move
  suboptimal — chose a lower-ranked move
  fallback   — parse failed; poke-env chose randomly
  switch     — chose to switch (scored separately, not ranked here)
  no_data    — state_json missing or action unparseable

Wave 2C additions:
  - is_blunder flag (suboptimal + score gap > BLUNDER_GAP_THRESHOLD)
  - score_gap field (0–1 fraction of best score "left on the table")
  - rng_flag field (possible_crit / possible_miss / None — inferred heuristically)
  - analyze_battle now returns win_probability_timeline, turning_point, blunders

Richer analysis additions:
  - variance_report: structured tally of all RNG events (crits, misses) with
    per-player benefit counts and a plain-English verdict.
  - critique_draft: team composition analysis for drafted battles — offensive
    type spread (STAB), shared defensive weaknesses, and execution quality.
  - analyze_battle accepts optional p1/p2 team_ids to populate both fields.

Action format note:
  Production stores actions as poke-env BattleOrder.message strings, e.g.
  "/choose move fireblast" or "/choose switch Metagross". The resolver
  _resolve_move_slot() handles both this name-based format and the legacy
  numeric form ("move 2") used in some tests.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_ORDER_RE = re.compile(r"(move|switch)\s+(\S+)", re.IGNORECASE)
_NORMALIZE_RE = re.compile(r"[^a-z0-9]")

# Fraction of best heuristic score lost before we call it a blunder.
# 0.4 == the chosen move was worth ≤60% of the best move's composite score.
BLUNDER_GAP_THRESHOLD = 0.40

# If actual HP drop / expected HP drop exceeds this, flag possible crit.
CRIT_MULTIPLIER_THRESHOLD = 1.45

# ---------------------------------------------------------------------------
# Draft critique — type chart + species data
# ---------------------------------------------------------------------------

# Gen 3 type chart: defending type → attacking types that deal 2× damage.
# Fairy type does not exist in Gen 3.
_TYPE_WEAKNESSES: dict[str, list[str]] = {
    "FIRE":     ["WATER", "GROUND", "ROCK"],
    "WATER":    ["ELECTRIC", "GRASS"],
    "GRASS":    ["FIRE", "ICE", "POISON", "FLYING", "BUG"],
    "ELECTRIC": ["GROUND"],
    "ICE":      ["FIRE", "FIGHTING", "ROCK", "STEEL"],
    "FIGHTING": ["FLYING", "PSYCHIC"],
    "POISON":   ["GROUND", "PSYCHIC"],
    "GROUND":   ["WATER", "GRASS", "ICE"],
    "FLYING":   ["ELECTRIC", "ICE", "ROCK"],
    "PSYCHIC":  ["BUG", "GHOST", "DARK"],
    "BUG":      ["FIRE", "FLYING", "ROCK"],
    "ROCK":     ["WATER", "GRASS", "FIGHTING", "GROUND", "STEEL"],
    "GHOST":    ["GHOST", "DARK"],
    "DRAGON":   ["ICE", "DRAGON"],
    "DARK":     ["FIGHTING", "BUG"],
    "STEEL":    ["FIRE", "FIGHTING", "GROUND"],
    "NORMAL":   ["FIGHTING"],
}

# Attacking types that deal 0× to a defending type (immunities).
_TYPE_IMMUNITIES: dict[str, list[str]] = {
    "NORMAL":   ["GHOST"],
    "GHOST":    ["NORMAL", "FIGHTING"],
    "STEEL":    ["POISON"],
    "GROUND":   ["ELECTRIC"],
    "DARK":     ["PSYCHIC"],
    "FLYING":   ["GROUND"],
}


def _load_species_data() -> dict[str, dict[str, Any]]:
    """Load gen3_movesets.json keyed by species ID, returning {} on error."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
    path = os.path.join(data_dir, "gen3_movesets.json")
    try:
        with open(path) as f:
            data: dict[str, dict[str, Any]] = json.load(f)
            return data
    except (OSError, json.JSONDecodeError):
        return {}


def _mon_weaknesses(types: list[str]) -> set[str]:
    """Return attacking types that hit this Pokémon for ≥2× damage.

    Handles dual-typing and immunities correctly for Gen 3.
    """
    mult: dict[str, float] = {}
    immunities: set[str] = set()
    for t in types:
        t_up = t.upper()
        for imm in _TYPE_IMMUNITIES.get(t_up, []):
            immunities.add(imm)
        for atk in _TYPE_WEAKNESSES.get(t_up, []):
            mult[atk] = mult.get(atk, 1.0) * 2.0
    return {atk for atk, m in mult.items() if m >= 2.0 and atk not in immunities}


# ---------------------------------------------------------------------------
# Heuristic ranking helpers
# ---------------------------------------------------------------------------

def _composite_score(move_score: dict[str, Any]) -> float:
    """Numeric score for comparing heuristic options. Higher = better."""
    if move_score.get("is_status"):
        return 2.0  # treat status moves as situationally neutral

    raw_mult = move_score.get("type_multiplier")
    mult = 1.0 if raw_mult is None else raw_mult  # 0.0 is falsy so can't use "or"
    if mult == 0.0:
        return -1.0  # immune — any other move is better

    dmg_str = move_score.get("estimated_damage_pct") or "0%"
    try:
        dmg = float(dmg_str.replace("~", "").replace("%", ""))
    except ValueError:
        dmg = 0.0

    score = mult * dmg
    if move_score.get("priority", 0) > 0:
        score *= 1.1

    return score


def _rank_moves(move_scores: list[dict[str, Any]]) -> list[int]:
    """Return a list of 1-based ranks, one per entry, in original order.

    rank[i] == 1 means move i is the heuristic top recommendation.
    """
    if not move_scores:
        return []
    pairs = sorted(enumerate(move_scores), key=lambda x: _composite_score(x[1]), reverse=True)
    ranks = [0] * len(move_scores)
    for rank, (idx, _) in enumerate(pairs, 1):
        ranks[idx] = rank
    return ranks


def _norm(s: str) -> str:
    """Lowercase and strip all non-alphanumeric characters for loose matching."""
    return _NORMALIZE_RE.sub("", s.lower())


def _resolve_move_slot(action: str, move_scores: list[dict[str, Any]]) -> int | None:
    """Return the 1-based slot for the chosen move, or None for switch/empty.

    Accepts two formats:
      - Numeric slot:  "move 2" or "/choose move 2"  → 2
      - Move name:     "/choose move fireblast"       → slot whose move_id matches

    The name match is normalised (lowercase, strip punctuation/spaces) so
    "fire-blast", "fireblast", "Fire Blast" all resolve correctly.
    """
    m = _ORDER_RE.search(action or "")
    if not m or m.group(1).lower() != "move":
        return None
    token = m.group(2)

    # Numeric slot (legacy / test format)
    if token.isdigit():
        return int(token)

    # Name-based lookup against heuristic move_scores
    norm_token = _norm(token)
    for i, ms in enumerate(move_scores, start=1):
        if _norm(str(ms.get("move_id", ""))) == norm_token:
            return i

    return None


def _parse_move_slot(action: str) -> int | None:
    """Extract 1-based slot number from a numeric action string like 'move 2'.

    Kept for backward compatibility with callers that don't have move_scores.
    Prefer _resolve_move_slot() when move_scores are available.
    """
    m = _ORDER_RE.search(action or "")
    if m and m.group(1).lower() == "move":
        try:
            return int(m.group(2))
        except ValueError:
            return None
    return None


def _is_switch(action: str) -> bool:
    m = _ORDER_RE.search(action or "")
    return bool(m and m.group(1).lower() == "switch")


def _score_gap(move_scores: list[dict[str, Any]], slot: int) -> float | None:
    """Fraction of best score not realised by the chosen slot (0–1).

    Returns None when there are no move scores or the scores are degenerate.
    A gap of 0.0 means the model chose the best option.
    A gap of 1.0 means the chosen move has zero value relative to the best.
    """
    if not move_scores or slot < 1 or slot > len(move_scores):
        return None
    scores = [_composite_score(ms) for ms in move_scores]
    best = max(scores)
    if best <= 0:
        return None
    chosen = scores[slot - 1]
    return max(0.0, (best - chosen) / best)


# ---------------------------------------------------------------------------
# Per-turn annotation
# ---------------------------------------------------------------------------

def annotate_turn(turn: dict[str, Any]) -> dict[str, Any]:
    """Produce a decision-quality annotation for one DB turn row."""
    base: dict[str, Any] = {
        "turn_number": turn["turn_number"],
        "player_role": turn["player_role"],
        "action_chosen": turn.get("action_chosen"),
        "heuristic_rank": None,
        "decision_quality": "no_data",
        "best_action": None,
        "notes": None,
        "is_blunder": False,
        "score_gap": None,
        "rng_flag": None,
    }

    # Parse failures: poke-env chose randomly
    parse_success = turn.get("parse_success", 1)
    if parse_success == 0 or parse_success is False:
        base["decision_quality"] = "fallback"
        base["notes"] = "LLM response unparseable — poke-env chose randomly"
        return base

    state_json = turn.get("state_json")
    if not state_json:
        return base

    try:
        state = json.loads(state_json)
    except (json.JSONDecodeError, TypeError):
        return base

    move_scores: list[dict[str, Any]] = state.get("heuristics", {}).get("move_scores", [])
    action = turn.get("action_chosen") or ""

    if _is_switch(action):
        base["decision_quality"] = "switch"
        base["notes"] = "chose to switch"
        return base

    slot = _resolve_move_slot(action, move_scores)
    if slot is None or not move_scores:
        return base

    idx = slot - 1  # convert to 0-based
    if idx < 0 or idx >= len(move_scores):
        return base

    # Status moves are not comparable against damaging moves on a damage scale —
    # exclude them from ranking entirely (same treatment as switches).
    if move_scores[idx].get("is_status"):
        base["decision_quality"] = "status"
        base["notes"] = f"{move_scores[idx].get('move_id', '?')} — status move (un-ranked)"
        return base

    ranks = _rank_moves(move_scores)
    chosen_rank = ranks[idx]
    n_moves = len(move_scores)

    # Score gap
    gap = _score_gap(move_scores, slot)
    base["score_gap"] = round(gap, 3) if gap is not None else None

    # Identify best move
    best_idx = ranks.index(1)
    best = move_scores[best_idx]
    best_label = f"move {best_idx + 1} ({best.get('move_id', '?')})"
    base["best_action"] = best_label

    base["heuristic_rank"] = chosen_rank
    if chosen_rank == 1:
        base["decision_quality"] = "optimal"
    elif chosen_rank <= min(3, n_moves):
        base["decision_quality"] = "good"
    else:
        base["decision_quality"] = "suboptimal"

    # Blunder flag
    if base["decision_quality"] == "suboptimal" and gap is not None and gap >= BLUNDER_GAP_THRESHOLD:
        base["is_blunder"] = True

    # Human-readable note
    chosen = move_scores[idx]
    if chosen_rank == 1:
        eff = chosen.get("effectiveness_label", "")
        dmg = chosen.get("estimated_damage_pct", "")
        base["notes"] = (
            f"{chosen.get('move_id','?')} — heuristic top choice"
            + (f" ({eff}, {dmg})" if eff else "")
        )
    else:
        gap_pct = f"{round((gap or 0) * 100)}%" if gap else ""
        blunder_tag = " [BLUNDER]" if base["is_blunder"] else ""
        base["notes"] = (
            f"chose {chosen.get('move_id','?')} (rank {chosen_rank}/{n_moves}"
            + (f", {gap_pct} below best" if gap_pct else "")
            + f"){blunder_tag}; "
            f"heuristic top: {best.get('move_id','?')} "
            f"({best.get('effectiveness_label','')})"
        )

    return base


# ---------------------------------------------------------------------------
# Win probability helpers  (Wave 2C)
# ---------------------------------------------------------------------------

def _team_hp_score(state: dict[str, Any]) -> float:
    """Sum of hp_fraction across the active Pokémon plus all bench members.

    my_team contains bench only (active is excluded by the serializer), so we
    must explicitly include my_active to get the true total team HP.
    """
    active = state.get("my_active")
    bench: list[dict[str, Any]] = state.get("my_team") or []
    all_mons: list[dict[str, Any]] = ([active] if active else []) + bench
    if not all_mons:
        return 0.5  # no state available
    return float(sum(max(0.0, m.get("hp_fraction", 0.0)) for m in all_mons))


def _win_prob(p1_state: dict[str, Any] | None, p2_state: dict[str, Any] | None) -> float | None:
    """Estimate P1's win probability as a ratio of team HP scores.

    Returns None when either state is unavailable.
    """
    if not p1_state or not p2_state:
        return None
    s1 = _team_hp_score(p1_state)
    s2 = _team_hp_score(p2_state)
    total = s1 + s2
    if total == 0.0:
        return 0.5
    return round(s1 / total, 4)


def _merge_turns(flat_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge per-player turn rows into one dict per turn number.

    Input: list of DB rows with turn_number, player_role, state_json, …
    Output: [{turn_number, p1: {state, action, parse_success}, p2: {…}}]
    """
    by_num: dict[int, dict[str, Any]] = {}
    for row in flat_turns:
        n = row["turn_number"]
        if n not in by_num:
            by_num[n] = {}
        try:
            state = json.loads(row["state_json"]) if row.get("state_json") else None
        except (json.JSONDecodeError, TypeError):
            state = None
        by_num[n][row["player_role"]] = {
            "state": state,
            "action": row.get("action_chosen"),
            "parse_success": bool(row.get("parse_success", True)),
        }
    return [{"turn_number": n, **by_num[n]} for n in sorted(by_num.keys())]


def _build_win_prob_timeline(
    merged_turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute P1 win probability at each merged turn."""
    timeline = []
    for mt in merged_turns:
        p1_state = (mt.get("p1") or {}).get("state")
        p2_state = (mt.get("p2") or {}).get("state")
        prob = _win_prob(p1_state, p2_state)
        timeline.append({"turn_number": mt["turn_number"], "p1_win_prob": prob})
    return timeline


def _detect_turning_point(timeline: list[dict[str, Any]]) -> int | None:
    """Return the turn_number with the largest absolute swing in P1 win probability.

    'Largest swing' == the turn whose delta from the previous valid data point is
    biggest.  Returns None when there are fewer than two data points.
    """
    valid = [(t["turn_number"], t["p1_win_prob"]) for t in timeline if t["p1_win_prob"] is not None]
    if len(valid) < 2:
        return None
    best_delta = 0.0
    best_turn: int = int(valid[1][0])
    for i in range(1, len(valid)):
        delta = abs(valid[i][1] - valid[i - 1][1])
        if delta > best_delta:
            best_delta = delta
            best_turn = int(valid[i][0])
    return best_turn


# ---------------------------------------------------------------------------
# RNG inference  (Wave 2C)
# ---------------------------------------------------------------------------

def _infer_rng_event(
    merged_turn: dict[str, Any],
    prev_merged_turn: dict[str, Any] | None,
) -> dict[str, str | None]:
    """Heuristically infer crit or miss for p1 and p2 this turn.

    Compares the actual HP drop on the OPPONENT to what the heuristic estimated.
    - possible_crit  : drop > CRIT_MULTIPLIER_THRESHOLD × estimated
    - possible_miss  : heuristic expected damage > 5% but opponent's HP did not drop at all
    - None           : nothing suspicious or insufficient data

    Returns {p1: flag | None, p2: flag | None}
    """
    result: dict[str, str | None] = {"p1": None, "p2": None}

    if not prev_merged_turn:
        return result

    for attacker_role, defender_role in (("p1", "p2"), ("p2", "p1")):
        curr_atk = (merged_turn.get(attacker_role) or {}).get("state")
        prev_def = (prev_merged_turn.get(defender_role) or {}).get("state")
        curr_def = (merged_turn.get(defender_role) or {}).get("state")

        if not curr_atk or not prev_def or not curr_def:
            continue

        # Estimated damage from the attacker's heuristic scores for the move they chose
        action = (merged_turn.get(attacker_role) or {}).get("action") or ""
        move_scores = curr_atk.get("heuristics", {}).get("move_scores", [])
        slot = _resolve_move_slot(action, move_scores)
        if slot is None:
            continue  # switch or no action
        if slot < 1 or slot > len(move_scores):
            continue

        ms = move_scores[slot - 1]
        dmg_str = ms.get("estimated_damage_pct") or "0%"
        try:
            est_dmg = float(dmg_str.replace("~", "").replace("%", "")) / 100.0
        except ValueError:
            continue

        if est_dmg <= 0:
            continue  # status move — skip

        # Actual HP drop on the defender's active Pokémon.
        # Use the defender's own state (my_active) on both turns — NOT
        # opponent_active from the defender's previous-turn state, which is the
        # attacker's Pokémon and produces garbage deltas.
        prev_species = (prev_def.get("my_active") or {}).get("species")
        curr_species = (curr_def.get("my_active") or {}).get("species")
        if prev_species != curr_species:
            continue  # defender switched between turns — HP delta is invalid

        prev_hp = (prev_def.get("my_active") or {}).get("hp_fraction")
        curr_hp = (curr_def.get("my_active") or {}).get("hp_fraction")

        if prev_hp is None or curr_hp is None:
            continue

        actual_drop = prev_hp - curr_hp

        if actual_drop < 0:
            continue  # they healed — not our case

        if actual_drop == 0 and est_dmg >= 0.05:
            result[attacker_role] = "possible_miss"
        elif actual_drop > 0 and est_dmg > 0 and actual_drop / est_dmg > CRIT_MULTIPLIER_THRESHOLD:
            result[attacker_role] = "possible_crit"

    return result


# ---------------------------------------------------------------------------
# Draft critique
# ---------------------------------------------------------------------------

def critique_draft(
    team_pokemon_ids: list[str] | None,
    role: str,
    annotations: list[dict[str, Any]],
    species_data: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Analyse a drafted team's composition and execution quality.

    Args:
        team_pokemon_ids: Species IDs from the teams table (e.g. ["pikachu"]).
        role: "p1" or "p2" — used to filter annotations.
        annotations: All annotated turns from annotate_turn().
        species_data: Optional pre-loaded moveset dict. Loaded from file if None.

    Returns a dict or None when no team data is available:
        team             : list of display names
        offensive_types  : STAB types the team fields (one per Pokémon type)
        shared_weaknesses: attacking types that hit ≥2 team members for 2×
        coverage_gaps    : types the team has no STAB representation for
        execution        : blunders, decision_quality_pct, deviation_turns
    """
    if not team_pokemon_ids:
        return None

    if species_data is None:
        species_data = _load_species_data()

    # Resolve each species ID to display name + types
    team_info: list[dict[str, Any]] = []
    for sid in team_pokemon_ids:
        entry = species_data.get(sid, {})
        if not entry:
            continue
        team_info.append({
            "species_id": sid,
            "species": entry.get("species", sid.title()),
            "types": [t.upper() for t in entry.get("types", [])],
        })

    if not team_info:
        return None

    # Offensive type spread (STAB proxy — Pokémon's own types)
    offensive_types: set[str] = set()
    for info in team_info:
        for t in info["types"]:
            offensive_types.add(t)

    # Weakness tally: how many team members are weak to each attacking type
    weakness_counts: dict[str, int] = {}
    for info in team_info:
        for atk_type in _mon_weaknesses(info["types"]):
            weakness_counts[atk_type] = weakness_counts.get(atk_type, 0) + 1

    shared_weaknesses = sorted(t for t, cnt in weakness_counts.items() if cnt >= 2)

    # Coverage gaps: Gen 3 types with no STAB on the team
    all_types = set(_TYPE_WEAKNESSES.keys())
    coverage_gaps = sorted(all_types - offensive_types)

    # Execution analysis — filter to this player's annotated turns
    player_anns = [a for a in annotations if a["player_role"] == role]
    ranked_turns = [a for a in player_anns if a.get("heuristic_rank") is not None]
    ranked_total = len(ranked_turns)
    blunder_turns = [a for a in player_anns if a.get("is_blunder")]
    optimal_count = sum(1 for a in player_anns if a.get("decision_quality") == "optimal")
    good_count    = sum(1 for a in player_anns if a.get("decision_quality") == "good")

    quality_pct: float | None = (
        round((optimal_count + good_count) / ranked_total * 100, 1)
        if ranked_total > 0 else None
    )
    optimal_rate: float | None = (
        round(optimal_count / ranked_total * 100, 1)
        if ranked_total > 0 else None
    )

    # Turns where model deviated from heuristic top (rank > 1) — up to 10
    deviation_turns = [
        {
            "turn_number": a["turn_number"],
            "chose": a.get("action_chosen"),
            "best":  a.get("best_action"),
            "gap_pct": round((a.get("score_gap") or 0.0) * 100),
            "was_blunder": bool(a.get("is_blunder")),
        }
        for a in player_anns
        if (a.get("heuristic_rank") or 0) > 1
    ][:10]

    return {
        "team": [info["species"] for info in team_info],
        "offensive_types": sorted(offensive_types),
        "shared_weaknesses": shared_weaknesses,
        "coverage_gaps": coverage_gaps,
        "execution": {
            "total_turns": len(player_anns),
            "blunders": len(blunder_turns),
            "decision_quality_pct": quality_pct,
            "optimal_rate": optimal_rate,
            "deviation_turns": deviation_turns,
        },
    }


# ---------------------------------------------------------------------------
# Variance report
# ---------------------------------------------------------------------------

def _build_variance_report(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Tally all inferred RNG events (crits, misses) and summarize net impact.

    Crits benefit the attacker; misses benefit the defender (hurt the attacker).
    Returns:
        total_events      : int
        crits             : list of {turn_number, attacker}
        misses            : list of {turn_number, attacker}
        p1_benefit_events : count of events that favored p1
        p2_benefit_events : count of events that favored p2
        verdict           : plain-English summary
    """
    crits:  list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []

    for ann in annotations:
        flag = ann.get("rng_flag")
        if flag == "possible_crit":
            crits.append({"turn_number": ann["turn_number"], "attacker": ann["player_role"]})
        elif flag == "possible_miss":
            misses.append({"turn_number": ann["turn_number"], "attacker": ann["player_role"]})

    total = len(crits) + len(misses)

    # A crit helps the attacker; a miss helps the defender (opposite role)
    p1_benefit = (
        sum(1 for c in crits  if c["attacker"] == "p1") +
        sum(1 for m in misses if m["attacker"] == "p2")
    )
    p2_benefit = (
        sum(1 for c in crits  if c["attacker"] == "p2") +
        sum(1 for m in misses if m["attacker"] == "p1")
    )

    if total == 0:
        verdict = "No notable RNG events detected"
    elif p1_benefit == p2_benefit:
        verdict = "Variance was roughly even between both players"
    elif p1_benefit > p2_benefit:
        verdict = f"Variance slightly favored p1 ({p1_benefit} vs {p2_benefit} beneficial events)"
    else:
        verdict = f"Variance slightly favored p2 ({p2_benefit} vs {p1_benefit} beneficial events)"

    return {
        "total_events": total,
        "crits": crits,
        "misses": misses,
        "p1_benefit_events": p1_benefit,
        "p2_benefit_events": p2_benefit,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Battle-level summary
# ---------------------------------------------------------------------------

def _player_summary(annotations: list[dict[str, Any]], role: str) -> dict[str, Any]:
    turns = [a for a in annotations if a["player_role"] == role]
    total = len(turns)
    if total == 0:
        return {"player_role": role, "total_turns": 0}

    counts: dict[str, int] = {}
    for a in turns:
        q = a.get("decision_quality", "no_data")
        counts[q] = counts.get(q, 0) + 1

    ranked = [a["heuristic_rank"] for a in turns if a.get("heuristic_rank") is not None]
    ranked_total = counts.get("optimal", 0) + counts.get("good", 0) + counts.get("suboptimal", 0)

    blunders = sum(1 for a in turns if a.get("is_blunder"))

    return {
        "player_role": role,
        "total_turns": total,
        "optimal": counts.get("optimal", 0),
        "good": counts.get("good", 0),
        "suboptimal": counts.get("suboptimal", 0),
        "fallback": counts.get("fallback", 0),
        "switch_turns": counts.get("switch", 0),
        "no_data_turns": counts.get("no_data", 0),
        "blunders": blunders,
        "avg_heuristic_rank": round(sum(ranked) / len(ranked), 2) if ranked else None,
        "decision_quality_pct": (
            round((counts.get("optimal", 0) + counts.get("good", 0)) / ranked_total * 100, 1)
            if ranked_total > 0 else None
        ),
    }


# ---------------------------------------------------------------------------
# Key moments synthesis
# ---------------------------------------------------------------------------

def _build_key_moments(
    annotations: list[dict[str, Any]],
    turning_point: int | None,
) -> list[dict[str, Any]]:
    """Build a chronological list of the most significant events in the battle.

    Each item has:
      turn_number  : int
      player_role  : "p1" | "p2" | None   (None for neutral events like turning_point)
      type         : "turning_point" | "blunder" | "rng"
      description  : human-readable one-liner
    """
    moments: list[dict[str, Any]] = []

    # Turning point is neutral — neither player's "fault"
    if turning_point is not None:
        moments.append({
            "turn_number": turning_point,
            "player_role": None,
            "type": "turning_point",
            "description": "Largest win-probability swing of the battle",
        })

    for ann in annotations:
        # Blunders
        if ann.get("is_blunder"):
            gap_pct = f"{round((ann.get('score_gap') or 0.0) * 100)}%"
            moments.append({
                "turn_number": ann["turn_number"],
                "player_role": ann["player_role"],
                "type": "blunder",
                "description": ann.get("notes") or f"Suboptimal move ({gap_pct} below best)",
            })

        # RNG events — separate moment for each player flagged on this turn
        if ann.get("rng_flag"):
            flag = ann["rng_flag"]
            label = flag.replace("_", " ").title()
            moments.append({
                "turn_number": ann["turn_number"],
                "player_role": ann["player_role"],
                "type": "rng",
                "description": f"{label} — may have shifted battle outcome",
            })

    # Sort by turn number; for equal turns order: turning_point < blunder < rng
    _TYPE_ORDER = {"turning_point": 0, "blunder": 1, "rng": 2}
    moments.sort(key=lambda m: (m["turn_number"], _TYPE_ORDER.get(m["type"], 9)))

    # Deduplicate identical (turn, player_role, type) triples
    seen: set[tuple[int, str | None, str]] = set()
    deduped: list[dict[str, Any]] = []
    for m in moments:
        key = (m["turn_number"], m.get("player_role"), m["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    return deduped


# ---------------------------------------------------------------------------
# Battle-level analysis
# ---------------------------------------------------------------------------

def analyze_battle(
    turns: list[dict[str, Any]],
    p1_team_ids: list[str] | None = None,
    p2_team_ids: list[str] | None = None,
    species_data: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Annotate all turns and produce per-player summaries.

    Args:
        turns: List of DB row dicts from get_turns_with_state().
        p1_team_ids: Optional list of species IDs for p1's drafted team.
        p2_team_ids: Optional list of species IDs for p2's drafted team.
        species_data: Optional pre-loaded moveset dict (avoids re-loading file).

    Returns dict with:
      - p1_summary, p2_summary
      - turns (annotated per-player list)
      - win_probability_timeline [{turn_number, p1_win_prob}]
      - turning_point (turn_number int or None)
      - blunders [{turn_number, player_role, action, score_gap, notes}]
      - key_moments [{turn_number, player_role, type, description}]
      - variance_report: structured RNG tally (always present)
      - p1_draft_critique, p2_draft_critique: team analysis (None when no draft)
    """
    annotations = [annotate_turn(t) for t in turns]

    # Win probability timeline — needs both sides merged per turn
    merged = _merge_turns(turns)
    win_prob_timeline = _build_win_prob_timeline(merged)
    turning_point = _detect_turning_point(win_prob_timeline)

    # RNG annotation — attach to merged turn, then fold back into annotations
    rng_by_turn: dict[int, dict[str, str | None]] = {}
    for i, mt in enumerate(merged):
        prev = merged[i - 1] if i > 0 else None
        rng_by_turn[mt["turn_number"]] = _infer_rng_event(mt, prev)

    for ann in annotations:
        rng = rng_by_turn.get(ann["turn_number"], {})
        ann["rng_flag"] = rng.get(ann["player_role"])

    # Blunders list (turn-number, player, score_gap)
    blunders = [
        {
            "turn_number": a["turn_number"],
            "player_role": a["player_role"],
            "action": a["action_chosen"],
            "score_gap": a["score_gap"],
            "notes": a["notes"],
        }
        for a in annotations
        if a.get("is_blunder")
    ]

    key_moments = _build_key_moments(annotations, turning_point)

    # Variance report — always computed from RNG-annotated turns
    variance_report = _build_variance_report(annotations)

    # Draft critique — only when team IDs are provided
    sd = species_data  # allow caller to pass pre-loaded data
    p1_critique = critique_draft(p1_team_ids, "p1", annotations, sd)
    p2_critique = critique_draft(p2_team_ids, "p2", annotations, sd)

    return {
        "p1_summary": _player_summary(annotations, "p1"),
        "p2_summary": _player_summary(annotations, "p2"),
        "turns": annotations,
        "win_probability_timeline": win_prob_timeline,
        "turning_point": turning_point,
        "blunders": blunders,
        "key_moments": key_moments,
        "variance_report": variance_report,
        "p1_draft_critique": p1_critique,
        "p2_draft_critique": p2_critique,
    }
