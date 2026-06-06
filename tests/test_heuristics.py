"""Tests for the heuristic action scorer."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from nidozo.battle.heuristics import _effectiveness_label, score_actions

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
    status=None,
    hp_fraction: float = 1.0,
) -> MagicMock:
    mon = MagicMock()
    mon.species = species
    type(mon).types = PropertyMock(
        return_value=[_mock_type(t) for t in types]
    )
    mon.base_stats = base_stats or {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80}
    mon.boosts = boosts or {}
    mon.stats = stats or {}
    mon.current_hp_fraction = hp_fraction
    mon.fainted = hp_fraction <= 0
    mon.moves = {}
    mon.status = status
    mon.damage_multiplier.return_value = 1.0   # safe default; override per-test as needed
    return mon


def _mock_battle(
    available_moves=None,
    available_switches=None,
    own: MagicMock | None = None,
    opp: MagicMock | None = None,
    weather: dict | None = None,
) -> MagicMock:
    battle = MagicMock()
    battle.available_moves = available_moves or []
    battle.available_switches = available_switches or []
    battle.active_pokemon = own
    battle.opponent_active_pokemon = opp
    battle.weather = weather or {}
    # Give team dicts so _remaining_count doesn't blow up
    battle.team = {own.species: own} if own is not None else {}
    battle.opponent_team = {opp.species: opp} if opp is not None else {}
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
    assert any("resist" in n.lower() for n in ss["notes"])


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
    assert any("weak" in n.lower() for n in ss["notes"])


# ---------------------------------------------------------------------------
# battle_context — speed comparison
# ---------------------------------------------------------------------------

class TestBattleContext:
    def test_context_present_in_output(self) -> None:
        battle = _mock_battle(own=_mock_pokemon(), opp=_mock_pokemon())
        result = score_actions(battle)
        assert "battle_context" in result

    def test_faster_own_moves_first(self) -> None:
        own = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 130})
        opp = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert ctx["speed"]["you_move_first"] is True

    def test_slower_own_moves_second(self) -> None:
        own = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 50})
        opp = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 100})
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert ctx["speed"]["you_move_first"] is False

    def test_paralysis_reduces_own_effective_speed(self) -> None:
        """A paralyzed mon with 200 base speed should have effective speed ~50,
        which is less than an opponent at 80 base speed."""
        status_par = MagicMock()
        status_par.name = "PAR"
        own = _mock_pokemon(
            base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 200},
            status=status_par,
        )
        opp = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        # 200 * 0.25 = 50 < 80 → moves second
        assert ctx["speed"]["you_move_first"] is False

    def test_active_matchup_favorable(self) -> None:
        """Own STAB hits ×2, opponent STAB hits ×1 → favorable."""
        own = _mock_pokemon(types=("WATER",))
        opp = _mock_pokemon(types=("FIRE",))
        opp.damage_multiplier.return_value = 2.0   # Water super effective vs Fire
        own.damage_multiplier.return_value = 1.0   # Fire neutral vs Water
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert ctx["active_matchup"] == "favorable"

    def test_active_matchup_disadvantaged(self) -> None:
        """Opponent STAB hits ×2, own STAB hits ×1 → disadvantaged."""
        own = _mock_pokemon(types=("FIRE",))
        opp = _mock_pokemon(types=("WATER",))
        opp.damage_multiplier.return_value = 1.0   # Fire neutral vs Water
        own.damage_multiplier.return_value = 2.0   # Water super effective vs Fire
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert ctx["active_matchup"] == "disadvantaged"

    def test_own_status_impact_reported(self) -> None:
        status_brn = MagicMock()
        status_brn.name = "BRN"
        own = _mock_pokemon(status=status_brn)
        battle = _mock_battle(own=own, opp=_mock_pokemon())
        ctx = score_actions(battle)["battle_context"]
        assert "own_status_impact" in ctx
        assert "Burn" in ctx["own_status_impact"]

    def test_opp_status_reported(self) -> None:
        status_slp = MagicMock()
        status_slp.name = "SLP"
        opp = _mock_pokemon(status=status_slp)
        battle = _mock_battle(own=_mock_pokemon(), opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert ctx.get("opp_status") == "SLP"

    def test_weather_note_rain(self) -> None:
        weather_key = MagicMock()
        weather_key.name = "RAINDANCE"
        battle = _mock_battle(own=_mock_pokemon(), opp=_mock_pokemon(),
                              weather={weather_key: 5})
        ctx = score_actions(battle)["battle_context"]
        assert ctx.get("weather") == "RAINDANCE"
        assert "Rain" in ctx.get("weather_note", "")

    def test_remaining_counts_present(self) -> None:
        own = _mock_pokemon()
        opp = _mock_pokemon()
        battle = _mock_battle(own=own, opp=opp)
        ctx = score_actions(battle)["battle_context"]
        assert "own_remaining" in ctx
        assert "opp_remaining" in ctx


# ---------------------------------------------------------------------------
# Move scoring — new fields and notes
# ---------------------------------------------------------------------------

class TestMoveScoringEnhancements:
    def test_result_has_accuracy_adjusted_pct(self) -> None:
        move = _mock_move("stoneedge", base_power=100, category_name="PHYSICAL",
                          type_name="ROCK", priority=0)
        move.accuracy = 80
        own = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert ms["accuracy_adjusted_pct"] is not None
        assert ms["accuracy_adjusted_pct"] != ms["estimated_damage_pct"]

    def test_low_pp_flagged(self) -> None:
        move = _mock_move("thunderbolt")
        move.current_pp = 1
        move.max_pp = 16
        own = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert ms["low_pp"] is True
        assert any("LOW PP" in n for n in ms["notes"])

    def test_full_pp_not_flagged(self) -> None:
        move = _mock_move("thunderbolt")
        move.current_pp = 16
        move.max_pp = 16
        own = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert ms["low_pp"] is False

    def test_speed_note_faster(self) -> None:
        move = _mock_move("thunderbolt", priority=0)
        own = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 150})
        opp = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("first" in n.lower() for n in ms["notes"])

    def test_speed_note_slower(self) -> None:
        move = _mock_move("thunderbolt", priority=0)
        own = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 50})
        opp = _mock_pokemon(base_stats={"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 120})
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("second" in n.lower() or "opponent moves first" in n.lower() for n in ms["notes"])

    def test_burn_halves_physical_damage(self) -> None:
        """Burn should reduce estimated physical damage vs an unburned version."""
        move_phys = _mock_move("tackle", base_power=40, category_name="PHYSICAL", type_name="NORMAL")
        move_phys.accuracy = True
        status_brn = MagicMock()
        status_brn.name = "BRN"
        own_burned = _mock_pokemon(status=status_brn)
        own_clean  = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0

        battle_burned = _mock_battle(available_moves=[move_phys], own=own_burned, opp=opp)
        battle_clean  = _mock_battle(available_moves=[move_phys], own=own_clean,  opp=opp)
        pct_burned = score_actions(battle_burned)["move_scores"][0]["estimated_damage_pct"]
        pct_clean  = score_actions(battle_clean)["move_scores"][0]["estimated_damage_pct"]
        # Damage should be lower when burned
        assert int(pct_burned.strip("~%")) < int(pct_clean.strip("~%"))

    def test_burn_note_on_physical_move(self) -> None:
        status_brn = MagicMock()
        status_brn.name = "BRN"
        move = _mock_move("tackle", base_power=40, category_name="PHYSICAL", type_name="NORMAL")
        move.accuracy = True
        own = _mock_pokemon(status=status_brn)
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("burn" in n.lower() and "halve" in n.lower() for n in ms["notes"])

    def test_weather_modifier_applied_to_water_in_rain(self) -> None:
        """Water move in Rain should show higher damage than without Rain."""
        move = _mock_move("surf", base_power=95, category_name="SPECIAL", type_name="WATER")
        move.accuracy = True
        own = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0

        weather_key = MagicMock()
        weather_key.name = "RAINDANCE"

        battle_rain = _mock_battle(available_moves=[move], own=own, opp=opp,
                                   weather={weather_key: 5})
        battle_dry  = _mock_battle(available_moves=[move], own=own, opp=opp)

        pct_rain = int(score_actions(battle_rain)["move_scores"][0]["estimated_damage_pct"].strip("~%"))
        pct_dry  = int(score_actions(battle_dry)["move_scores"][0]["estimated_damage_pct"].strip("~%"))
        assert pct_rain > pct_dry

    def test_priority_note_present(self) -> None:
        move = _mock_move("extremespeed", base_power=80, category_name="PHYSICAL",
                          type_name="NORMAL", priority=2)
        own = _mock_pokemon()
        opp = _mock_pokemon()
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("priority" in n.lower() for n in ms["notes"])
        # Priority moves should NOT also have a "you move first/second" speed note
        assert not any("you move first" in n.lower() or "second" in n.lower() for n in ms["notes"])


# ---------------------------------------------------------------------------
# Status move annotation — new context
# ---------------------------------------------------------------------------

class TestStatusMoveAnnotation:
    def test_paralysis_move_already_statused(self) -> None:
        """Thunder Wave vs already-paralyzed opponent should warn about wasting it."""
        move = _mock_move("thunderwave", base_power=0, category_name="STATUS")
        own = _mock_pokemon()
        status_par = MagicMock()
        status_par.name = "PAR"
        opp = _mock_pokemon(status=status_par)
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("already" in n.lower() or "wasted" in n.lower() for n in ms["notes"])

    def test_sleep_move_fresh_opponent(self) -> None:
        """Spore vs healthy unstatused opponent — should note Sleep."""
        move = _mock_move("spore", base_power=0, category_name="STATUS")
        own = _mock_pokemon()
        opp = _mock_pokemon()
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("sleep" in n.lower() for n in ms["notes"])
        # No "wasted" warning for a fresh opponent
        assert not any("wasted" in n.lower() for n in ms["notes"])

    def test_boost_move_annotates_stage_gain(self) -> None:
        """Swords Dance should show atk stage change."""
        move = _mock_move("swordsdance", base_power=0, category_name="STATUS")
        own = _mock_pokemon(boosts={"atk": 0})
        opp = _mock_pokemon()
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        # Should mention atk and show the +2 stage change
        assert any("atk" in n.lower() for n in ms["notes"])

    def test_boost_move_at_max_stage(self) -> None:
        """Swords Dance when atk is already +6 should flag no effect."""
        move = _mock_move("swordsdance", base_power=0, category_name="STATUS")
        own = _mock_pokemon(boosts={"atk": 6})
        opp = _mock_pokemon()
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("max" in n.lower() or "+6" in n for n in ms["notes"])

    def test_heal_move_low_hp_high_value(self) -> None:
        """Recover at low HP should note high recovery value."""
        move = _mock_move("recover", base_power=0, category_name="STATUS")
        own = _mock_pokemon(hp_fraction=0.3)
        opp = _mock_pokemon()
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("high recovery" in n.lower() or "low" in n.lower() for n in ms["notes"])

    def test_heal_move_full_hp_low_value(self) -> None:
        """Recover at near-full HP should note limited value."""
        move = _mock_move("recover", base_power=0, category_name="STATUS")
        own = _mock_pokemon(hp_fraction=0.95)
        opp = _mock_pokemon()
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("limited" in n.lower() or "high" in n.lower() for n in ms["notes"])

    def test_stat_drop_move_annotates_opponent_stage(self) -> None:
        """Screech should show the opponent's defense stage change."""
        move = _mock_move("screech", base_power=0, category_name="STATUS")
        own = _mock_pokemon()
        opp = _mock_pokemon(boosts={"def": 0})
        battle = _mock_battle(available_moves=[move], own=own, opp=opp)
        ms = score_actions(battle)["move_scores"][0]
        assert any("def" in n.lower() for n in ms["notes"])


# ---------------------------------------------------------------------------
# Switch scoring — quality score and enhanced notes
# ---------------------------------------------------------------------------

class TestSwitchScoringEnhancements:
    def test_switch_quality_present(self) -> None:
        incoming = _mock_pokemon("blastoise", types=("WATER",))
        opp = _mock_pokemon(types=("FIRE",))
        opp.moves = {}
        battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=opp)
        ss = score_actions(battle)["switch_scores"][0]
        assert "switch_quality" in ss
        assert isinstance(ss["switch_quality"], int)
        assert -3 <= ss["switch_quality"] <= 3

    def test_quality_label_present(self) -> None:
        incoming = _mock_pokemon("blastoise", types=("WATER",))
        opp = _mock_pokemon(types=("FIRE",))
        opp.moves = {}
        battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=opp)
        ss = score_actions(battle)["switch_scores"][0]
        assert "quality_label" in ss

    def test_low_hp_incoming_penalized(self) -> None:
        """An incoming mon at 15% HP should have a lower switch_quality."""
        high_hp = _mock_pokemon("blastoise", hp_fraction=1.0)
        low_hp  = _mock_pokemon("blastoise", hp_fraction=0.15)
        opp = _mock_pokemon()
        opp.moves = {}
        battle_high = _mock_battle(available_switches=[high_hp], own=_mock_pokemon(), opp=opp)
        battle_low  = _mock_battle(available_switches=[low_hp],  own=_mock_pokemon(), opp=opp)
        sq_high = score_actions(battle_high)["switch_scores"][0]["switch_quality"]
        sq_low  = score_actions(battle_low)["switch_scores"][0]["switch_quality"]
        assert sq_low < sq_high

    def test_disadvantaged_active_raises_switch_value(self) -> None:
        """Switching out of a disadvantaged matchup should boost incoming quality."""
        incoming = _mock_pokemon("starmie", types=("WATER",))
        incoming.damage_multiplier.return_value = 1.0  # neutral defensive matchup

        own = _mock_pokemon("charizard", types=("FIRE",))
        opp = _mock_pokemon(types=("WATER",))
        # Own Fire types hit Water neutrally; opponent Water types hit own Fire SE
        own.damage_multiplier.return_value = 2.0   # Water super effective vs Fire (own takes SE hits)
        opp.damage_multiplier.return_value = 1.0   # Fire neutral vs Water

        opp.moves = {}
        battle = _mock_battle(available_switches=[incoming], own=own, opp=opp)
        ss = score_actions(battle)["switch_scores"][0]
        assert any("disadvantaged" in n.lower() or "high value" in n.lower() for n in ss["notes"])

    def test_immune_incoming_boosts_quality(self) -> None:
        """Incoming mon immune to opponent's threat type gets quality boost."""
        incoming = _mock_pokemon("gengar", types=("GHOST", "POISON"))
        # Immune to Normal
        incoming.damage_multiplier.side_effect = lambda t: 0.0 if t.name == "NORMAL" else 1.0
        opp = _mock_pokemon(types=("NORMAL",))
        opp.moves = {}
        opp.damage_multiplier.return_value = 1.0
        battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=opp)
        ss = score_actions(battle)["switch_scores"][0]
        assert any("immune" in n.lower() for n in ss["notes"])
        assert ss["switch_quality"] > 0


def test_no_crash_when_opp_is_none_for_switch() -> None:
    incoming = _mock_pokemon("pikachu")
    battle = _mock_battle(available_switches=[incoming], own=_mock_pokemon(), opp=None)
    result = score_actions(battle)
    assert result["switch_scores"][0]["species"] == "pikachu"
