"""Tests for ActionParser — valid formats, edge cases, and fallback behaviour."""

from unittest.mock import MagicMock

import pytest

from nidozo.battle.action_parser import parse_action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_move(id_: str) -> MagicMock:
    m = MagicMock()
    m.id = id_
    return m


def _mock_pokemon(species: str) -> MagicMock:
    p = MagicMock()
    p.species = species
    return p


def _make_battle(moves=None, switches=None) -> MagicMock:
    battle = MagicMock()
    battle.turn = 1
    battle.available_moves = moves or []
    battle.available_switches = switches or []
    return battle


def _make_player(move=None, switch=None) -> MagicMock:
    """Player whose create_order returns a sentinel based on what it receives."""
    player = MagicMock()
    player.create_order.side_effect = lambda obj, **_: ("move", obj) if hasattr(obj, "id") else ("switch", obj)
    return player


# ---------------------------------------------------------------------------
# Happy-path parsing
# ---------------------------------------------------------------------------

def test_parses_move_action() -> None:
    moves = [_mock_move("thunderbolt"), _mock_move("quickattack")]
    battle = _make_battle(moves=moves)
    player = _make_player()

    result = parse_action("I'll go with move 1.\nACTION: move 1", battle, player)

    player.create_order.assert_called_once_with(moves[0])
    assert result is not None


def test_parses_switch_action() -> None:
    switches = [_mock_pokemon("blastoise"), _mock_pokemon("venusaur")]
    battle = _make_battle(switches=switches)
    player = _make_player()

    result = parse_action("Better to switch.\nACTION: switch 2", battle, player)

    player.create_order.assert_called_once_with(switches[1])
    assert result is not None


def test_action_case_insensitive() -> None:
    moves = [_mock_move("surf")]
    battle = _make_battle(moves=moves)
    player = _make_player()

    result = parse_action("action: MOVE 1", battle, player)
    assert result is not None


def test_uses_last_action_line_when_multiple() -> None:
    """If model reasons 'maybe move 1' but ends with 'ACTION: move 2', use slot 2."""
    moves = [_mock_move("flamethrower"), _mock_move("fireblast")]
    battle = _make_battle(moves=moves)
    player = _make_player()

    response = "ACTION: move 1\nActually...\nACTION: move 2"
    parse_action(response, battle, player)

    player.create_order.assert_called_once_with(moves[1])


def test_extra_whitespace_in_action_line() -> None:
    moves = [_mock_move("icebeam")]
    battle = _make_battle(moves=moves)
    player = _make_player()
    result = parse_action("ACTION:   move   1", battle, player)
    assert result is not None


# ---------------------------------------------------------------------------
# Failure cases — all return None
# ---------------------------------------------------------------------------

def test_no_action_line_returns_none() -> None:
    battle = _make_battle(moves=[_mock_move("tackle")])
    player = _make_player()
    result = parse_action("I think Tackle is good here.", battle, player)
    assert result is None


def test_move_slot_out_of_range_returns_none() -> None:
    battle = _make_battle(moves=[_mock_move("tackle")])
    player = _make_player()
    result = parse_action("ACTION: move 5", battle, player)
    assert result is None


def test_switch_slot_out_of_range_returns_none() -> None:
    switches = [_mock_pokemon("pikachu")]
    battle = _make_battle(switches=switches)
    player = _make_player()
    result = parse_action("ACTION: switch 9", battle, player)
    assert result is None


def test_move_when_no_moves_available_returns_none() -> None:
    battle = _make_battle(moves=[])
    player = _make_player()
    result = parse_action("ACTION: move 1", battle, player)
    assert result is None


def test_switch_when_no_switches_available_returns_none() -> None:
    battle = _make_battle(switches=[])
    player = _make_player()
    result = parse_action("ACTION: switch 1", battle, player)
    assert result is None


def test_slot_zero_returns_none() -> None:
    battle = _make_battle(moves=[_mock_move("tackle")])
    player = _make_player()
    result = parse_action("ACTION: move 0", battle, player)
    assert result is None
