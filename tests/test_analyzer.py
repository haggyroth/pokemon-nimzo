"""Tests for the post-game battle analyzer."""

import json

import pytest

from nidozo.analysis.analyzer import (
    _composite_score,
    _parse_move_slot,
    _rank_moves,
    analyze_battle,
    annotate_turn,
)

# ---------------------------------------------------------------------------
# _composite_score
# ---------------------------------------------------------------------------

def test_composite_score_immune():
    score = _composite_score({"type_multiplier": 0.0, "estimated_damage_pct": "~40%"})
    assert score == -1.0


def test_composite_score_super_effective():
    score = _composite_score({"type_multiplier": 2.0, "estimated_damage_pct": "~50%"})
    assert score == pytest.approx(100.0)


def test_composite_score_status_flat():
    score = _composite_score({"is_status": True})
    assert score == 2.0


def test_composite_score_priority_bonus():
    base = _composite_score({"type_multiplier": 1.0, "estimated_damage_pct": "~30%", "priority": 0})
    prio = _composite_score({"type_multiplier": 1.0, "estimated_damage_pct": "~30%", "priority": 1})
    assert prio > base


# ---------------------------------------------------------------------------
# _rank_moves
# ---------------------------------------------------------------------------

def test_rank_moves_order():
    moves = [
        {"type_multiplier": 0.5, "estimated_damage_pct": "~20%", "is_status": False},
        {"type_multiplier": 2.0, "estimated_damage_pct": "~60%", "is_status": False},
        {"type_multiplier": 1.0, "estimated_damage_pct": "~30%", "is_status": False},
    ]
    ranks = _rank_moves(moves)
    # Move 1 (2× 60%) should be rank 1
    assert ranks[1] == 1
    assert ranks[2] == 2
    assert ranks[0] == 3


def test_rank_moves_immune_last():
    moves = [
        {"type_multiplier": 0.0, "estimated_damage_pct": "~30%", "is_status": False},
        {"type_multiplier": 1.0, "estimated_damage_pct": "~30%", "is_status": False},
    ]
    ranks = _rank_moves(moves)
    assert ranks[0] == 2  # immune is ranked last
    assert ranks[1] == 1


def test_rank_moves_empty():
    assert _rank_moves([]) == []


# ---------------------------------------------------------------------------
# _parse_move_slot
# ---------------------------------------------------------------------------

def test_parse_move_slot_basic():
    assert _parse_move_slot("move 2") == 2
    assert _parse_move_slot("move 1") == 1


def test_parse_move_slot_switch():
    assert _parse_move_slot("switch pikachu") is None


def test_parse_move_slot_none():
    assert _parse_move_slot(None) is None
    assert _parse_move_slot("") is None


# ---------------------------------------------------------------------------
# annotate_turn
# ---------------------------------------------------------------------------

def _make_state(move_scores):
    return json.dumps({"heuristics": {"move_scores": move_scores, "switch_scores": []}})


def test_annotate_optimal_choice():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "tackle", "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 3,
        "player_role": "p1",
        "action_chosen": "move 1",  # thunderbolt — best choice
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "optimal"
    assert result["heuristic_rank"] == 1


def test_annotate_suboptimal_choice():
    # Need 4 moves so rank 4 falls outside top-3 → suboptimal
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "surf",        "type_multiplier": 1.0, "estimated_damage_pct": "~40%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~25%", "is_status": False, "priority": 0},
        {"move_id": "splash",      "type_multiplier": 0.0, "estimated_damage_pct": "0%",   "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 3,
        "player_role": "p1",
        "action_chosen": "move 4",  # splash — immune, rank 4
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "suboptimal"
    assert result["heuristic_rank"] == 4


def test_annotate_fallback():
    turn = {
        "turn_number": 5,
        "player_role": "p2",
        "action_chosen": None,
        "parse_success": 0,
        "state_json": None,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "fallback"


def test_annotate_no_state_json():
    turn = {
        "turn_number": 1,
        "player_role": "p1",
        "action_chosen": "move 1",
        "parse_success": 1,
        "state_json": None,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "no_data"


def test_annotate_switch():
    state = _make_state([
        {"move_id": "tackle", "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 2,
        "player_role": "p1",
        "action_chosen": "switch charizard",
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "switch"


# ---------------------------------------------------------------------------
# analyze_battle
# ---------------------------------------------------------------------------

def test_analyze_battle_summary():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "tackle", "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "move 1", "parse_success": 1, "state_json": state},
        {"turn_number": 1, "player_role": "p2", "action_chosen": "move 2", "parse_success": 1, "state_json": state},
        {"turn_number": 2, "player_role": "p1", "action_chosen": None,    "parse_success": 0, "state_json": None},
        {"turn_number": 2, "player_role": "p2", "action_chosen": "move 1", "parse_success": 1, "state_json": state},
    ]
    result = analyze_battle(turns)

    p1 = result["p1_summary"]
    assert p1["optimal"] == 1
    assert p1["fallback"] == 1
    assert p1["total_turns"] == 2

    p2 = result["p2_summary"]
    # p2 turn 1: move 2 = rank 2 of 2 = "good"; turn 2: move 1 = rank 1 = "optimal"
    assert p2["optimal"] == 1
    assert p2["good"] == 1
    assert p2["suboptimal"] == 0

    assert len(result["turns"]) == 4


def test_analyze_battle_empty():
    result = analyze_battle([])
    assert result["p1_summary"]["total_turns"] == 0
    assert result["p2_summary"]["total_turns"] == 0
    assert result["turns"] == []
