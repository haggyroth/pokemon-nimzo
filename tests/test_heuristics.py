"""Tests for the heuristic action scorer."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from pokemon_nimzo.battle.heuristics import score_actions, _effectiveness_label


# ---------------------------------------------------------------------------
# Helpers — same mock pattern as test_serializer.py
# ---------------------------------------------------------------------------

def _mock_type(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    return t


def _mock_move(
    id_: str,
    base_power: int = 90,
    category_name: str = "SPECIAL",
    type_name: str = "ELECTRIC",
    priority: int = 0,
) -> MagicMock:
    from poke_env.battle.move_category import MoveCategory
    m = MagicMock()
    m.id = id_
    m.base_power = base_power
    m.category = MoveCategory.SPECIAL if category_name == "SPECIAL" else (
        MoveCategory.PHYSICAL if category_name == "PHYSICAL" else MoveCategory.STATUS
    )
    m.type = _mock_type(type_name)
    m.priority = priority
    m.accuracy = 1.0
    m.current_pp = 15
    m.max_pp = 15
    return m


def _mock_pokemon(
    species: str = "pikachu",
    types=("ELECTRIC",),
    base_stats: dict | None = None,
    boosts: dict | None = None,
    stats: dict | None = None,
) -> MagicMock:
    mon = MagicMock()
    mon.species = species
    type(mon).types = PropertyMock(
        return_value=[_mock_type(t) for t in types]
    )
    mon.base_stats = base_stats or {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80}
    mon.boosts = boosts or {}
    mon.stats = stats or {}
    mon.current_hp_fraction = 1.0
    mon.moves = {}
    return mon


def _mock_battle(
    available_moves=None,
    available_switches=None,
    own: MagicMock | None = None,
    opp: MagicMock | None = None,
) -> MagicMock:
    battle = MagicMock()
    battle.available_moves = available_moves or []
    battle.available_switches = available_switches or []
    battle.active_pokemon = own
    battle.opponent_active_pokemon = opp
    return battle


# ---------------------------------------------------------------------------
# _effectiveness_label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mult,expected", [
    (0.0, "immune (0×)"),
    (0.25, "not very effective (0.25×)"),
    (0.5, "not very effective (0.5×)"),
    (1.0, "neutral (1×)"),
    (2.0, "super effective (2×)"),
    (4.0, "super effective (4×)"),
])
def test_effectiveness_label(mult, expected) -> None:
    assert _effectiveness_label(mult) == expected


# ---------------------------------------------------------------------------
# Move scoring
# ---------------------------------------------------------------------------

def test_score_actions_returns_move_and_switch_keys() -> None:
    battle = _mock_battle()
    result = score_actions(battle)
    assert "move_scores" in result
    assert "switch_scores" in result


def test_super_effective_move_labeled_correctly() -> None:
    move = _mock_move("thunderbolt", type_name="ELECTRIC")
    own = _mock_pokemon()
    opp = _mock_pokemon(types=("WATER",))
    # Water is 2× weak to Electric
    opp.damage_multiplier.return_value = 2.0

    battle = _mock_battle(available_moves=[move], own=own, opp=opp)
    result = score_actions(battle)

    ms = result["move_scores"][0]
    assert ms["type_multiplier"] == 2.0
    assert "super effective" in ms["effectiveness_label"]


def test_immune_move_shows_zero_damage() -> None:
    move = _mock_move("thunderbolt", type_name="ELECTRIC")
    own = _mock_pokemon()
    opp = _mock_pokemon(types=("GROUND",))
    opp.damage_multiplier.return_value = 0.0

    battle = _mock_battle(available_moves=[move], own=own, opp=opp)
    result = score_actions(battle)

    ms = result["move_scores"][0]
    assert ms["type_multiplier"] == 0.0
    assert ms["estimated_damage_pct"] == "0%"
    assert any("immune" in n for n in ms["notes"])


def test_priority_move_noted() -> None:
    move = _mock_move("quickattack", base_power=40, category_name="PHYSICAL",
                      type_name="NORMAL", priority=1)
    own = _mock_pokemon()
    opp = _mock_pokemon()
    opp.damage_multiplier.return_value = 1.0

    battle = _mock_battle(available_moves=[move], own=own, opp=opp)
    result = score_actions(battle)

    ms = result["move_scores"][0]
    assert ms["priority"] == 1
    assert any("priority" in n for n in ms["notes"])


def test_status_move_has_no_damage_estimate() -> None:
    move = _mock_move("thunderwave", base_power=0, category_name="STATUS")
    battle = _mock_battle(available_moves=[move], own=_mock_pokemon(), opp=_mock_pokemon())
    result = score_actions(battle)

    ms = result["move_scores"][0]
    assert ms["is_status"] is True
    assert ms["estimated_damage_pct"] is None


def test_no_crash_when_opp_is_none() -> None:
    move = _mock_move("tackle")
    battle = _mock_battle(available_moves=[move], own=_mock_pokemon(), opp=None)
    result = score_actions(battle)
    assert len(result["move_scores"]) == 1


# ---------------------------------------------------------------------------
# Switch scoring
# ---------------------------------------------------------------------------

def test_switch_score_notes_resistance() -> None:
    incoming = _mock_pokemon("blastoise", types=("WATER",))
    # incoming resists Fire (defensive check); Water is not SE vs Fire (offensive check)
    incoming.damage_multiplier.side_effect = lambda t: 0.5 if t.name == "FIRE" else 1.0

    opp = _mock_pokemon(types=("FIRE",))
    opp.moves = {}
    opp.damage_multiplier.return_value = 1.0  # Water neutral vs Fire for offensive check

    battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=opp)
    result = score_actions(battle)

    ss = result["switch_scores"][0]
    assert ss["species"] == "blastoise"
    assert any("resists" in n for n in ss["notes"])


def test_switch_score_notes_weakness() -> None:
    incoming = _mock_pokemon("charizard", types=("FIRE", "FLYING"))
    # incoming is weak to Water
    incoming.damage_multiplier.side_effect = lambda t: 2.0 if t.name == "WATER" else 1.0

    opp = _mock_pokemon(types=("WATER",))
    opp.moves = {}
    opp.damage_multiplier.return_value = 1.0  # Fire neutral vs Water for offensive check

    battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=opp)
    result = score_actions(battle)

    ss = result["switch_scores"][0]
    assert any("weak" in n for n in ss["notes"])


def test_no_crash_when_opp_is_none_for_switch() -> None:
    incoming = _mock_pokemon("pikachu")
    battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=None)
    result = score_actions(battle)
    assert result["switch_scores"][0]["species"] == "pikachu"
