"""Tests for the post-game battle analyzer."""

import json

import pytest

from nidozo.analysis.analyzer import (
    BLUNDER_GAP_THRESHOLD,
    _build_key_moments,
    _build_variance_report,
    _composite_score,
    _detect_turning_point,
    _merge_turns,
    _mon_weaknesses,
    _parse_move_slot,
    _rank_moves,
    _resolve_move_slot,
    _score_gap,
    _team_hp_score,
    _win_prob,
    analyze_battle,
    annotate_turn,
    critique_draft,
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


# ---------------------------------------------------------------------------
# _resolve_move_slot  (H1 fix)
# ---------------------------------------------------------------------------

_TWO_MOVES = [
    {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
    {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
]

def test_resolve_move_slot_by_name():
    """Production format: '/choose move <move_id>' resolves by name lookup."""
    assert _resolve_move_slot("/choose move thunderbolt", _TWO_MOVES) == 1
    assert _resolve_move_slot("/choose move tackle", _TWO_MOVES) == 2


def test_resolve_move_slot_name_normalised():
    """Names with hyphens or mixed case should still resolve.

    poke-env normalises move IDs to lowercase without spaces (e.g. 'fire_blast'
    or 'fireblast'), so space-separated multi-word names are not a realistic
    production format and are not tested here.
    """
    moves = [{"move_id": "fire_blast"}, {"move_id": "ice_beam"}]
    assert _resolve_move_slot("/choose move fire-blast", moves) == 1
    assert _resolve_move_slot("/choose move fireblast", moves) == 1
    assert _resolve_move_slot("/choose move FIREBLAST", moves) == 1
    assert _resolve_move_slot("/choose move ice_beam", moves) == 2


def test_resolve_move_slot_numeric_backcompat():
    """Legacy 'move N' and '/choose move N' still resolve by slot number."""
    assert _resolve_move_slot("move 1", _TWO_MOVES) == 1
    assert _resolve_move_slot("/choose move 2", _TWO_MOVES) == 2
    assert _resolve_move_slot("move 2", _TWO_MOVES) == 2


def test_resolve_move_slot_switch_returns_none():
    assert _resolve_move_slot("/choose switch metagross", _TWO_MOVES) is None


def test_resolve_move_slot_unknown_name_returns_none():
    assert _resolve_move_slot("/choose move unknownmove", _TWO_MOVES) is None


def test_resolve_move_slot_empty_returns_none():
    assert _resolve_move_slot("", _TWO_MOVES) is None
    assert _resolve_move_slot(None, _TWO_MOVES) is None


# ---------------------------------------------------------------------------
# annotate_turn — fixtures now use the real '/choose move <id>' format
# ---------------------------------------------------------------------------

def test_annotate_optimal_choice():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 3,
        "player_role": "p1",
        "action_chosen": "/choose move thunderbolt",   # best choice, name format
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "optimal"
    assert result["heuristic_rank"] == 1


def test_annotate_good_choice():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "surf",        "type_multiplier": 1.5, "estimated_damage_pct": "~40%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 1,
        "player_role": "p1",
        "action_chosen": "/choose move surf",   # rank 2 of 3 → good
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "good"
    assert result["heuristic_rank"] == 2


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
        "action_chosen": "/choose move splash",   # immune, rank 4 — name format
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
        "action_chosen": "/choose move thunderbolt",
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
        "action_chosen": "/choose switch charizard",
        "parse_success": 1,
        "state_json": state,
    }
    result = annotate_turn(turn)
    assert result["decision_quality"] == "switch"


def test_annotate_real_format_not_no_data():
    """Regression: the real '/choose move <id>' format must NOT produce no_data."""
    state = _make_state([
        {"move_id": "fireblast", "type_multiplier": 2.0, "estimated_damage_pct": "~60%", "is_status": False, "priority": 0},
        {"move_id": "earthquake", "type_multiplier": 1.0, "estimated_damage_pct": "~30%", "is_status": False, "priority": 0},
    ])
    for action in ("/choose move fireblast", "/choose move earthquake"):
        result = annotate_turn({
            "turn_number": 1, "player_role": "p1",
            "action_chosen": action, "parse_success": 1, "state_json": state,
        })
        assert result["decision_quality"] != "no_data", (
            f"action '{action}' produced no_data — name resolver not working"
        )


# ---------------------------------------------------------------------------
# analyze_battle
# ---------------------------------------------------------------------------

def test_analyze_battle_summary():
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~20%", "is_status": False, "priority": 0},
    ])
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "/choose move thunderbolt", "parse_success": 1, "state_json": state},
        {"turn_number": 1, "player_role": "p2", "action_chosen": "/choose move tackle",      "parse_success": 1, "state_json": state},
        {"turn_number": 2, "player_role": "p1", "action_chosen": None,                       "parse_success": 0, "state_json": None},
        {"turn_number": 2, "player_role": "p2", "action_chosen": "/choose move thunderbolt", "parse_success": 1, "state_json": state},
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
    # Craft a state where splash is immune (score -1) vs thunderbolt (score 110).
    # The gap will be > BLUNDER_GAP_THRESHOLD.
    state = _make_state([
        {"move_id": "thunderbolt", "type_multiplier": 2.0, "estimated_damage_pct": "~55%", "is_status": False, "priority": 0},
        {"move_id": "surf",        "type_multiplier": 1.0, "estimated_damage_pct": "~40%", "is_status": False, "priority": 0},
        {"move_id": "tackle",      "type_multiplier": 1.0, "estimated_damage_pct": "~25%", "is_status": False, "priority": 0},
        {"move_id": "splash",      "type_multiplier": 0.0, "estimated_damage_pct": "0%",   "is_status": False, "priority": 0},
    ])
    turn = {
        "turn_number": 1, "player_role": "p1",
        "action_chosen": "/choose move splash", "parse_success": 1, "state_json": state,
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
        "action_chosen": "/choose move surf", "parse_success": 1, "state_json": state,
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
        {"turn_number": 1, "player_role": "p1", "action_chosen": "/choose move thunderbolt", "parse_success": 1,
         "state_json": _make_full_state(1.0, opp_hp=1.0)},
        {"turn_number": 1, "player_role": "p2", "action_chosen": "/choose move thunderbolt", "parse_success": 1,
         "state_json": _make_full_state(1.0, opp_hp=1.0)},
        {"turn_number": 2, "player_role": "p1", "action_chosen": "/choose move thunderbolt", "parse_success": 1,
         "state_json": _make_full_state(0.6, opp_hp=0.4)},
        {"turn_number": 2, "player_role": "p2", "action_chosen": "/choose move thunderbolt", "parse_success": 1,
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
        {"turn_number": 1, "player_role": "p1", "action_chosen": "/choose move splash",
         "parse_success": 1, "state_json": subopt_state},
    ]
    result = analyze_battle(turns)
    assert len(result["blunders"]) >= 1
    blunder = result["blunders"][0]
    assert blunder["player_role"] == "p1"
    assert blunder["turn_number"] == 1
    assert blunder["score_gap"] is not None


# ---------------------------------------------------------------------------
# key_moments — new in feat/richer-analysis
# ---------------------------------------------------------------------------


def test_key_moments_turning_point_only():
    """Turning point alone produces one 'turning_point' moment with no player_role."""
    annotations: list[dict] = []
    moments = _build_key_moments(annotations, turning_point=5)
    assert len(moments) == 1
    assert moments[0]["type"] == "turning_point"
    assert moments[0]["turn_number"] == 5
    assert moments[0]["player_role"] is None


def test_key_moments_blunder_included():
    """A blunder annotation surfaces as a 'blunder' moment."""
    annotations = [
        {
            "turn_number": 3,
            "player_role": "p1",
            "is_blunder": True,
            "score_gap": 0.6,
            "rng_flag": None,
            "notes": "chose tackle (rank 4/4, 60% below best); heuristic top: thunderbolt",
        }
    ]
    moments = _build_key_moments(annotations, turning_point=None)
    blunders = [m for m in moments if m["type"] == "blunder"]
    assert len(blunders) == 1
    assert blunders[0]["turn_number"] == 3
    assert blunders[0]["player_role"] == "p1"
    assert "tackle" in blunders[0]["description"]


def test_key_moments_rng_included():
    """An rng_flag annotation surfaces as an 'rng' moment."""
    annotations = [
        {
            "turn_number": 7,
            "player_role": "p2",
            "is_blunder": False,
            "score_gap": None,
            "rng_flag": "possible_crit",
            "notes": None,
        }
    ]
    moments = _build_key_moments(annotations, turning_point=None)
    rng_moments = [m for m in moments if m["type"] == "rng"]
    assert len(rng_moments) == 1
    assert rng_moments[0]["turn_number"] == 7
    assert rng_moments[0]["player_role"] == "p2"
    assert "Crit" in rng_moments[0]["description"]


def test_key_moments_sorted_by_turn():
    """Moments appear in ascending turn order."""
    annotations = [
        {"turn_number": 8, "player_role": "p1", "is_blunder": True, "score_gap": 0.5, "rng_flag": None, "notes": "blunder"},
        {"turn_number": 2, "player_role": "p2", "is_blunder": False, "score_gap": None, "rng_flag": "possible_miss", "notes": None},
    ]
    moments = _build_key_moments(annotations, turning_point=5)
    turn_nums = [m["turn_number"] for m in moments]
    assert turn_nums == sorted(turn_nums)


def test_key_moments_deduplicated():
    """Identical (turn, player_role, type) pairs appear only once."""
    annotations = [
        {"turn_number": 4, "player_role": "p1", "is_blunder": True, "score_gap": 0.5, "rng_flag": None, "notes": "a"},
        {"turn_number": 4, "player_role": "p1", "is_blunder": True, "score_gap": 0.5, "rng_flag": None, "notes": "a"},
    ]
    moments = _build_key_moments(annotations, turning_point=None)
    blunders = [m for m in moments if m["type"] == "blunder" and m["player_role"] == "p1" and m["turn_number"] == 4]
    assert len(blunders) == 1


def test_analyze_battle_includes_key_moments():
    """analyze_battle result dict includes key_moments list.

    Uses 4 moves so the last-place choice is 'suboptimal' (rank 4/4),
    which triggers the blunder flag when score_gap >= BLUNDER_GAP_THRESHOLD.
    """
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
        },
    })
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "/choose move splash",
         "parse_success": 1, "state_json": subopt_state},
    ]
    result = analyze_battle(turns)
    assert "key_moments" in result
    assert isinstance(result["key_moments"], list)
    # Choosing immune splash (rank 4/4) is a clear blunder — should appear in key_moments
    blunders = [m for m in result["key_moments"] if m["type"] == "blunder"]
    assert len(blunders) >= 1


# ---------------------------------------------------------------------------
# _mon_weaknesses
# ---------------------------------------------------------------------------

def test_mon_weaknesses_single_type():
    """Water is weak to Electric and Grass only."""
    w = _mon_weaknesses(["WATER"])
    assert "ELECTRIC" in w
    assert "GRASS" in w
    assert "FIRE" not in w


def test_mon_weaknesses_dual_type_amplified():
    """Ice/Flying (Articuno) stacks weaknesses — Rock should be 4× (super weak)."""
    w = _mon_weaknesses(["ICE", "FLYING"])
    assert "ROCK" in w   # Rock is 4× — definitely in the 2× set


def test_mon_weaknesses_immunity_overrides():
    """Ground + Electric → Ground type is immune to Electric."""
    w = _mon_weaknesses(["GROUND", "ELECTRIC"])
    # Ground is immune to Electric so no Electric weakness even though Ground has it
    assert "ELECTRIC" not in w


def test_mon_weaknesses_pure_fire():
    """Fire is weak to Water, Ground, Rock."""
    w = _mon_weaknesses(["FIRE"])
    assert "WATER" in w
    assert "GROUND" in w
    assert "ROCK" in w


# ---------------------------------------------------------------------------
# _build_variance_report
# ---------------------------------------------------------------------------

def _ann(turn: int, role: str, rng: str | None) -> dict:
    return {"turn_number": turn, "player_role": role, "rng_flag": rng, "is_blunder": False}


def test_variance_report_empty():
    report = _build_variance_report([])
    assert report["total_events"] == 0
    assert report["crits"] == []
    assert report["misses"] == []
    assert "No notable" in report["verdict"]


def test_variance_report_crits_help_attacker():
    """A crit by p1 is a benefit for p1."""
    anns = [_ann(3, "p1", "possible_crit")]
    report = _build_variance_report(anns)
    assert report["total_events"] == 1
    assert len(report["crits"]) == 1
    assert report["crits"][0] == {"turn_number": 3, "attacker": "p1"}
    assert report["p1_benefit_events"] == 1
    assert report["p2_benefit_events"] == 0
    assert "p1" in report["verdict"]


def test_variance_report_miss_helps_defender():
    """A miss by p1 benefits p2 (the defender)."""
    anns = [_ann(5, "p1", "possible_miss")]
    report = _build_variance_report(anns)
    assert report["p2_benefit_events"] == 1
    assert report["p1_benefit_events"] == 0


def test_variance_report_even():
    """Equal events produce 'roughly even' verdict."""
    anns = [_ann(1, "p1", "possible_crit"), _ann(2, "p2", "possible_crit")]
    report = _build_variance_report(anns)
    assert report["p1_benefit_events"] == 1
    assert report["p2_benefit_events"] == 1
    assert "even" in report["verdict"]


def test_variance_report_analyze_battle_includes_it():
    """analyze_battle result always has variance_report key."""
    result = analyze_battle([])
    assert "variance_report" in result
    assert result["variance_report"]["total_events"] == 0


# ---------------------------------------------------------------------------
# critique_draft
# ---------------------------------------------------------------------------

_FAKE_SPECIES: dict = {
    "pikachu":   {"species": "Pikachu",   "types": ["Electric"]},
    "charizard": {"species": "Charizard", "types": ["Fire", "Flying"]},
    "blastoise": {"species": "Blastoise", "types": ["Water"]},
}


def test_critique_draft_none_when_no_ids():
    """Returns None when team_pokemon_ids is None or empty."""
    assert critique_draft(None, "p1", []) is None
    assert critique_draft([], "p1", []) is None


def test_critique_draft_team_names():
    """'team' field lists display names from species_data."""
    result = critique_draft(["pikachu", "charizard"], "p1", [], species_data=_FAKE_SPECIES)
    assert result is not None
    assert result["team"] == ["Pikachu", "Charizard"]


def test_critique_draft_offensive_types():
    """Offensive types are the union of all team member types."""
    result = critique_draft(["pikachu", "blastoise"], "p1", [], species_data=_FAKE_SPECIES)
    assert result is not None
    assert "ELECTRIC" in result["offensive_types"]
    assert "WATER" in result["offensive_types"]


def test_critique_draft_shared_weaknesses():
    """Shared weaknesses appear for types that hit ≥2 team members."""
    # Charizard (Fire/Flying) is weak to Rock; Blastoise (Water) is not.
    # Pikachu (Electric) is weak to Ground; Blastoise (Water) is not.
    # No shared weakness in this trio.
    result = critique_draft(
        ["pikachu", "charizard", "blastoise"], "p1", [], species_data=_FAKE_SPECIES
    )
    assert result is not None
    # Rock hits Charizard (Fire×2, Flying×2 → 4×). Only Charizard is ×2+ to Rock.
    # (Pikachu: Electric type, no Rock weakness. Blastoise: Water, no Rock weakness.)
    assert "ROCK" not in result["shared_weaknesses"]


def test_critique_draft_execution_blunders():
    """Execution field reflects blunders in the filtered annotation list."""
    anns = [
        {"turn_number": 1, "player_role": "p1", "is_blunder": True, "heuristic_rank": 4,
         "decision_quality": "suboptimal", "score_gap": 0.8, "action_chosen": "/choose move splash",
         "best_action": "move 1 (thunderbolt)"},
        {"turn_number": 2, "player_role": "p1", "is_blunder": False, "heuristic_rank": 1,
         "decision_quality": "optimal", "score_gap": 0.0, "action_chosen": "/choose move thunderbolt",
         "best_action": "move 1 (thunderbolt)"},
        {"turn_number": 1, "player_role": "p2", "is_blunder": False, "heuristic_rank": 1,
         "decision_quality": "optimal", "score_gap": 0.0, "action_chosen": "/choose move thunderbolt",
         "best_action": "move 1 (thunderbolt)"},
    ]
    result = critique_draft(["pikachu"], "p1", anns, species_data=_FAKE_SPECIES)
    assert result is not None
    assert result["execution"]["blunders"] == 1
    assert result["execution"]["total_turns"] == 2


def test_critique_draft_analyze_battle_includes_it():
    """analyze_battle returns p1_draft_critique / p2_draft_critique keys always."""
    result = analyze_battle([])
    assert "p1_draft_critique" in result
    assert "p2_draft_critique" in result
    # No team IDs → both None
    assert result["p1_draft_critique"] is None
    assert result["p2_draft_critique"] is None


def test_critique_draft_with_team_ids_in_analyze_battle():
    """analyze_battle passes team IDs to critique_draft."""
    result = analyze_battle(
        [],
        p1_team_ids=["pikachu"],
        species_data=_FAKE_SPECIES,
    )
    assert result["p1_draft_critique"] is not None
    assert result["p1_draft_critique"]["team"] == ["Pikachu"]
    assert result["p2_draft_critique"] is None  # no p2 team supplied
