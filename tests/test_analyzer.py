"""Tests for the post-game battle analyzer."""

import json

import pytest

from nidozo.analysis.analyzer import (
    BLUNDER_GAP_THRESHOLD,
    _composite_score,
    _detect_turning_point,
    _merge_turns,
    _parse_move_slot,
    _rank_moves,
    _score_gap,
    _team_hp_score,
    _win_prob,
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


# ---------------------------------------------------------------------------
# Wave 2C — _score_gap
# ---------------------------------------------------------------------------

def test_score_gap_optimal_is_zero():
    moves = [
        {"type_multiplier": 2.0, "estimated_damage_pct": "~50%", "is_status": False},
        {"type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False},
    ]
    gap = _score_gap(moves, slot=1)   # slot 1 is the best move
    assert gap == pytest.approx(0.0)


def test_score_gap_nonzero_for_worse_move():
    moves = [
        {"type_multiplier": 2.0, "estimated_damage_pct": "~50%", "is_status": False},
        {"type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False},
    ]
    gap = _score_gap(moves, slot=2)   # worse move
    assert gap is not None
    assert 0 < gap <= 1.0


def test_score_gap_none_for_immune_best():
    # If the best move has score <= 0 (all immune), gap is None
    moves = [
        {"type_multiplier": 0.0, "estimated_damage_pct": "~30%", "is_status": False},
    ]
    assert _score_gap(moves, slot=1) is None


# ---------------------------------------------------------------------------
# Wave 2C — blunder flag in annotate_turn
# ---------------------------------------------------------------------------

def test_blunder_flagged_when_gap_exceeds_threshold():
    # Craft a state where move 4 is immune (score -1) vs move 1 (score 100).
    # The gap will be > BLUNDER_GAP_THRESHOLD.
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "surf",        "type_multiplier": 1.0, "estimated_damage_pct": "~40%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~25%", "is_status": False, "priority": 0},
        {"move_id": "splash",      "type_multiplier": 0.0, "estimated_damage_pct": "0%",   "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 1, "player_role": "p1",
        "action_chosen": "move 4", "parse_success": 1, "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "suboptimal"
    assert result["is_blunder"] is True
    assert result["score_gap"] is not None
    assert result["score_gap"] >= BLUNDER_GAP_THRESHOLD


def test_blunder_not_flagged_for_good_move():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "surf",        "type_multiplier": 1.5, "estimated_damage_pct": "~50%", "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 1, "player_role": "p1",
        "action_chosen": "move 2", "parse_success": 1, "state_json": state,
    }
    result = annotate_turn(turn)
    # rank 2 of 2 → good (≤ min(3, 2)), never a blunder
    assert result["is_blunder"] is False


# ---------------------------------------------------------------------------
# Wave 2C — win probability helpers
# ---------------------------------------------------------------------------

def test_team_hp_score_from_my_team():
    state = {
        "my_team": [
            {"species": "Pikachu", "hp_fraction": 0.8},
            {"species": "Charmander", "hp_fraction": 0.0},  # fainted
            {"species": "Squirtle", "hp_fraction": 0.6},
        ]
    }
    score = _team_hp_score(state)
    assert score == pytest.approx(1.4)


def test_team_hp_score_fallback_to_active():
    state = {"my_active": {"species": "Pikachu", "hp_fraction": 0.5}}
    score = _team_hp_score(state)
    assert score == pytest.approx(0.5)


def test_win_prob_equal_teams():
    p1 = {"my_team": [{"hp_fraction": 1.0}]}
    p2 = {"my_team": [{"hp_fraction": 1.0}]}
    assert _win_prob(p1, p2) == pytest.approx(0.5)


def test_win_prob_p1_advantage():
    p1 = {"my_team": [{"hp_fraction": 1.0}, {"hp_fraction": 1.0}]}
    p2 = {"my_team": [{"hp_fraction": 0.5}, {"hp_fraction": 0.0}]}
    prob = _win_prob(p1, p2)
    assert prob is not None
    assert prob > 0.7   # p1 clearly ahead


def test_win_prob_returns_none_without_both_states():
    assert _win_prob(None, {"my_team": []}) is None
    assert _win_prob({"my_team": []}, None) is None


# ---------------------------------------------------------------------------
# Wave 2C — merge, timeline, turning point
# ---------------------------------------------------------------------------

def test_merge_turns_groups_by_number():
    raw = [
        {"turn_number": 1, "player_role": "p1", "state_json": None, "action_chosen": "move 1", "parse_success": 1},
        {"turn_number": 1, "player_role": "p2", "state_json": None, "action_chosen": "move 2", "parse_success": 1},
        {"turn_number": 2, "player_role": "p1", "state_json": None, "action_chosen": "move 1", "parse_success": 1},
    ]
    merged = _merge_turns(raw)
    assert len(merged) == 2
    assert "p1" in merged[0] and "p2" in merged[0]
    assert merged[1]["turn_number"] == 2
    assert "p2" not in merged[1]   # p2 missing from turn 2


def test_detect_turning_point_finds_largest_swing():
    timeline = [
        {"turn_number": 1, "p1_win_prob": 0.50},
        {"turn_number": 2, "p1_win_prob": 0.52},
        {"turn_number": 3, "p1_win_prob": 0.30},   # large drop
        {"turn_number": 4, "p1_win_prob": 0.28},
    ]
    tp = _detect_turning_point(timeline)
    assert tp == 3   # turn 3 has the biggest delta


def test_detect_turning_point_returns_none_on_insufficient_data():
    assert _detect_turning_point([]) is None
    assert _detect_turning_point([{"turn_number": 1, "p1_win_prob": 0.5}]) is None


# ---------------------------------------------------------------------------
# Wave 2C — analyze_battle returns new fields
# ---------------------------------------------------------------------------

def _make_full_state(hp_fraction: float, opp_hp: float = 0.5) -> str:
    return json.dumps({
        "my_team": [{"species": "Pikachu", "hp_fraction": hp_fraction}],
        "my_active": {"species": "Pikachu", "hp_fraction": hp_fraction},
        "opponent_active": {"species": "Charmander", "hp_fraction": opp_hp},
        "heuristics": {
            "move_scores": [
                {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
                {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
            ],
            "switch_scores": [],
        },
    })


def test_analyze_battle_win_prob_timeline():
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "move 1", "parse_success": 1,
         "state_json": _make_full_state(1.0, opp_hp=1.0)},
        {"turn_number": 1, "player_role": "p2", "action_chosen": "move 2", "parse_success": 1,
         "state_json": _make_full_state(1.0, opp_hp=1.0)},
        {"turn_number": 2, "player_role": "p1", "action_chosen": "move 1", "parse_success": 1,
         "state_json": _make_full_state(0.6, opp_hp=0.4)},
        {"turn_number": 2, "player_role": "p2", "action_chosen": "move 1", "parse_success": 1,
         "state_json": _make_full_state(0.4, opp_hp=0.6)},
    ]
    result = analyze_battle(turns)

    assert "win_probability_timeline" in result
    assert isinstance(result["win_probability_timeline"], list)
    assert len(result["win_probability_timeline"]) >= 1
    for entry in result["win_probability_timeline"]:
        assert "turn_number" in entry
        assert "p1_win_prob" in entry

    assert "turning_point" in result
    assert "blunders" in result
    assert isinstance(result["blunders"], list)


def test_analyze_battle_blunders_list_populated():
    """A battle with a clear blunder should have a non-empty blunders list."""
    subopt_state = json.dumps({
        "my_team": [{"species": "Pikachu", "hp_fraction": 1.0}],
        "my_active": {"species": "Pikachu", "hp_fraction": 1.0},
        "heuristics": {
            "move_scores": [
                {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
                {"move_id": "surf",        "type_multiplier": 1.0, "estimated_damage_pct": "~40%", "is_status": False, "priority": 0},
                {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~25%", "is_status": False, "priority": 0},
                {"move_id": "splash",      "type_multiplier": 0.0, "estimated_damage_pct": "0%",   "is_status": False, "priority": 0},
            ],
            "switch_scores": [],
        },
    })
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "move 4",
         "parse_success": 1, "state_json": subopt_state},
    ]
    result = analyze_battle(turns)
    assert len(result["blunders"]) >= 1
    blunder = result["blunders"][0]
    assert blunder["player_role"] == "p1"
    assert blunder["turn_number"] == 1
    assert blunder["score_gap"] is not None
