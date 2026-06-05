"""
Tests for the battle state serializer.

These tests enforce the hidden-information contract:
  - Own Pokémon expose full detail.
  - Opponent Pokémon expose ONLY legitimately revealed information.

We use mocks to construct precise battle states without needing a live server.
"""

from unittest.mock import MagicMock, PropertyMock

from nidozo.battle.serializer import (
    _serialize_opponent_pokemon,
    _serialize_own_pokemon,
    serialize_battle,
)

# ---------------------------------------------------------------------------
# Helpers to build mock Pokémon and Move objects
# ---------------------------------------------------------------------------

def _mock_move(id_: str, base_power: int = 80, pp: int = 15, max_pp: int = 15) -> MagicMock:
    move = MagicMock()
    move.id = id_
    move.type.name = "NORMAL"
    move.category.name = "PHYSICAL"
    move.base_power = base_power
    move.accuracy = 1.0
    move.current_pp = pp
    move.max_pp = max_pp
    move.priority = 0
    return move


def _mock_own_pokemon(
    species: str = "pikachu",
    hp_fraction: float = 1.0,
    status=None,
    moves: dict | None = None,
    item: str | None = "lightball",
    ability: str = "static",
) -> MagicMock:
    mon = MagicMock()
    mon.species = species
    mon.level = 50
    mon.types = [MagicMock(name="ELECTRIC")]
    type(mon).types = PropertyMock(return_value=[MagicMock(name="ELECTRIC")])
    mon.current_hp_fraction = hp_fraction
    mon.fainted = hp_fraction == 0.0
    mon.status = status
    mon.boosts = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
    mon.item = item
    mon.ability = ability
    mon.base_stats = {"hp": 35, "atk": 55, "def": 40, "spa": 50, "spd": 50, "spe": 90}
    mon.moves = moves or {"thunderbolt": _mock_move("thunderbolt")}
    mon.effects = {}
    mon.active = True
    return mon


def _mock_opponent_pokemon(
    species: str = "charmander",
    hp_fraction: float = 0.75,
    status=None,
    revealed_moves: dict | None = None,
) -> MagicMock:
    """Opponent mon: moves dict contains only moves actually used in battle."""
    mon = MagicMock()
    mon.species = species
    mon.level = 50
    type(mon).types = PropertyMock(return_value=[MagicMock(name="FIRE")])
    mon.current_hp_fraction = hp_fraction
    mon.fainted = False
    mon.status = status
    mon.boosts = {}
    mon.item = None
    mon.ability = None
    # poke-env only populates moves for opponent when they've been used
    mon.moves = revealed_moves or {}
    mon.active = True
    return mon


# ---------------------------------------------------------------------------
# Own Pokémon serialization
# ---------------------------------------------------------------------------

def test_own_pokemon_includes_moves_with_pp() -> None:
    move = _mock_move("thunderbolt", pp=10, max_pp=15)
    mon = _mock_own_pokemon(moves={"thunderbolt": move})
    result = _serialize_own_pokemon(mon)
    assert "moves" in result
    assert "thunderbolt" in result["moves"]
    assert result["moves"]["thunderbolt"]["pp"] == 10
    assert result["moves"]["thunderbolt"]["max_pp"] == 15


def test_own_pokemon_includes_item_and_ability() -> None:
    mon = _mock_own_pokemon(item="choiceband", ability="intimidate")
    result = _serialize_own_pokemon(mon)
    assert result["item"] == "choiceband"
    assert result["ability"] == "intimidate"


def test_own_pokemon_includes_exact_hp_fraction() -> None:
    mon = _mock_own_pokemon(hp_fraction=0.333)
    result = _serialize_own_pokemon(mon)
    assert result["hp_fraction"] == 0.333


def test_own_pokemon_includes_base_stats() -> None:
    mon = _mock_own_pokemon()
    result = _serialize_own_pokemon(mon)
    assert "base_stats" in result
    assert result["base_stats"]["spe"] == 90


def test_own_pokemon_none_returns_none() -> None:
    assert _serialize_own_pokemon(None) is None


# ---------------------------------------------------------------------------
# Opponent Pokémon — hidden-information enforcement
# ---------------------------------------------------------------------------

def test_opponent_pokemon_has_no_pp_on_moves() -> None:
    """Revealed moves must NOT include PP (we don't track opponent PP)."""
    used_move = _mock_move("flamethrower")
    mon = _mock_opponent_pokemon(revealed_moves={"flamethrower": used_move})
    result = _serialize_opponent_pokemon(mon)
    assert "flamethrower" in result["revealed_moves"]
    assert "pp" not in result["revealed_moves"]["flamethrower"]
    assert "max_pp" not in result["revealed_moves"]["flamethrower"]


def test_opponent_pokemon_no_unrevealed_moves() -> None:
    """If the opponent has used zero moves, revealed_moves must be empty."""
    mon = _mock_opponent_pokemon(revealed_moves={})
    result = _serialize_opponent_pokemon(mon)
    assert result["revealed_moves"] == {}


def test_opponent_pokemon_has_no_exact_hp() -> None:
    """Opponent HP must be a fraction (%), not an exact integer."""
    mon = _mock_opponent_pokemon(hp_fraction=0.6)
    result = _serialize_opponent_pokemon(mon)
    assert "hp_fraction" in result
    assert isinstance(result["hp_fraction"], float)
    # Must NOT have current_hp (exact value)
    assert "current_hp" not in result


def test_opponent_pokemon_has_no_base_stats() -> None:
    """Base stats (Pokédex data) are public, but we deliberately omit them
    from the opponent serialization to keep the prompt focused on observed state."""
    mon = _mock_opponent_pokemon()
    result = _serialize_opponent_pokemon(mon)
    assert "base_stats" not in result


def test_opponent_pokemon_unrevealed_item_is_none() -> None:
    """Item must not appear unless poke-env has registered it as revealed."""
    mon = _mock_opponent_pokemon()
    mon.item = None
    result = _serialize_opponent_pokemon(mon)
    assert result["item"] is None


def test_opponent_pokemon_revealed_item_appears() -> None:
    mon = _mock_opponent_pokemon()
    mon.item = "choicescarf"
    result = _serialize_opponent_pokemon(mon)
    assert result["item"] == "choicescarf"


def test_opponent_pokemon_none_returns_none() -> None:
    assert _serialize_opponent_pokemon(None) is None


# ---------------------------------------------------------------------------
# Full battle serialization smoke test
# ---------------------------------------------------------------------------

def test_serialize_battle_structure() -> None:
    """serialize_battle returns all expected top-level keys."""
    battle = MagicMock()
    battle.turn = 3
    battle.format = "gen3randombattle"
    battle.weather = {}
    battle.fields = {}
    battle.side_conditions = {}
    battle.opponent_side_conditions = {}
    own = _mock_own_pokemon()
    opp = _mock_opponent_pokemon()
    opp.damage_multiplier.return_value = 1.0
    own.damage_multiplier.return_value = 1.0
    battle.active_pokemon = own
    battle.opponent_active_pokemon = opp
    battle.team = {"pikachu": _mock_own_pokemon()}
    battle.opponent_team = {"charmander": _mock_opponent_pokemon()}
    battle.available_moves = []
    battle.available_switches = []
    battle.force_switch = False

    result = serialize_battle(battle)

    expected_keys = {
        "turn", "format", "weather", "fields",
        "my_side_conditions", "opponent_side_conditions",
        "my_active", "my_team",
        "opponent_active", "opponent_team",
        "available_moves", "available_switches", "force_switch",
        "heuristics",
    }
    assert expected_keys == set(result.keys())
    assert result["turn"] == 3
