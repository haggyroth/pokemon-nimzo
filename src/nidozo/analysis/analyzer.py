"""
Post-game battle analyzer.

For each logged turn (where state_json was captured), compares the model's
chosen action to the heuristic rankings to produce a decision quality label:

  optimal   — chose the heuristic top-ranked move
  good      — chose the 2nd or 3rd ranked move
  suboptimal — chose a lower-ranked move
  fallback  — parse failed; poke-env chose randomly
  switch    — chose to switch (scored separately, not ranked here)
  no_data   — state_json missing or action unparseable
"""

from __future__ import annotations

import json
import re
from typing import Any

_ORDER_RE = re.compile(r"(move|switch)\s+(\S+)", re.IGNORECASE)


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


def _parse_move_slot(action: str) -> int | None:
    """Extract 1-based slot number from an action string like 'move 2'."""
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

    move_scores: list[dict] = state.get("heuristics", {}).get("move_scores", [])
    action = turn.get("action_chosen") or ""

    if _is_switch(action):
        base["decision_quality"] = "switch"
        base["notes"] = "chose to switch"
        return base

    slot = _parse_move_slot(action)
    if slot is None or not move_scores:
        return base

    idx = slot - 1  # convert to 0-based
    if idx < 0 or idx >= len(move_scores):
        return base

    ranks = _rank_moves(move_scores)
    chosen_rank = ranks[idx]
    n_moves = len(move_scores)

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
        base["notes"] = (
            f"chose {chosen.get('move_id','?')} (rank {chosen_rank}/{n_moves}); "
            f"heuristic top: {best.get('move_id','?')} "
            f"({best.get('effectiveness_label','')})"
        )

    return base


# ---------------------------------------------------------------------------
# Battle-level summary
# ---------------------------------------------------------------------------

def _player_summary(annotations: list[dict], role: str) -> dict[str, Any]:
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

    return {
        "player_role": role,
        "total_turns": total,
        "optimal": counts.get("optimal", 0),
        "good": counts.get("good", 0),
        "suboptimal": counts.get("suboptimal", 0),
        "fallback": counts.get("fallback", 0),
        "switch_turns": counts.get("switch", 0),
        "no_data_turns": counts.get("no_data", 0),
        "avg_heuristic_rank": round(sum(ranked) / len(ranked), 2) if ranked else None,
        "decision_quality_pct": (
            round((counts.get("optimal", 0) + counts.get("good", 0)) / ranked_total * 100, 1)
            if ranked_total > 0 else None
        ),
    }


def analyze_battle(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Annotate all turns and produce per-player summaries.

    Args:
        turns: List of DB row dicts from get_turns_with_state().

    Returns:
        Dict with 'p1_summary', 'p2_summary', and 'turns' (annotated list).
    """
    annotations = [annotate_turn(t) for t in turns]
    return {
        "p1_summary": _player_summary(annotations, "p1"),
        "p2_summary": _player_summary(annotations, "p2"),
        "turns": annotations,
    }
