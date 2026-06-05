"""Tests for PromptBuilder — template loading, rendering, and version handling."""

import pytest

from pokemon_nimzo.llm.prompt_builder import PromptBuilder


# Minimal battle state that satisfies all template variables
_MINIMAL_STATE: dict = {
    "turn": 1,
    "format": "gen3randombattle",
    "weather": None,
    "fields": [],
    "my_side_conditions": [],
    "opponent_side_conditions": [],
    "my_active": {
        "species": "pikachu",
        "types": ["ELECTRIC"],
        "hp_fraction": 1.0,
        "status": None,
        "boosts": {},
        "item": "lightball",
        "ability": "static",
        "moves": {
            "thunderbolt": {
                "id": "thunderbolt",
                "type": "ELECTRIC",
                "category": "SPECIAL",
                "base_power": 90,
                "pp": 15,
                "max_pp": 15,
                "priority": 0,
            }
        },
        "effects": [],
        "fainted": False,
    },
    "my_team": [],
    "opponent_active": {
        "species": "charmander",
        "types": ["FIRE"],
        "hp_fraction": 0.75,
        "status": None,
        "boosts": {},
        "item": None,
        "ability": None,
        "revealed_moves": {},
        "fainted": False,
    },
    "opponent_team": [],
    "available_moves": [
        {
            "id": "thunderbolt",
            "type": "ELECTRIC",
            "category": "SPECIAL",
            "base_power": 90,
            "accuracy": 1.0,
            "pp": 15,
            "max_pp": 15,
            "priority": 0,
        }
    ],
    "available_switches": [],
    "force_switch": False,
    "heuristics": {
        "move_scores": [
            {
                "move_id": "thunderbolt",
                "type_multiplier": 1.0,
                "effectiveness_label": "neutral (1×)",
                "estimated_damage_pct": "~30%",
                "priority": 0,
                "is_status": False,
                "notes": ["STAB"],
            }
        ],
        "switch_scores": [],
    },
}


def test_v1_loads_without_error() -> None:
    builder = PromptBuilder(version="v1")
    assert builder.version == "v1"


def test_build_system_returns_system_role() -> None:
    builder = PromptBuilder()
    msg = builder.build_system()
    assert msg["role"] == "system"
    assert len(msg["content"]) > 100


def test_system_prompt_contains_action_format() -> None:
    builder = PromptBuilder()
    system = builder.build_system()["content"]
    assert "ACTION: move" in system
    assert "ACTION: switch" in system


def test_build_turn_returns_user_role() -> None:
    builder = PromptBuilder()
    msg = builder.build_turn(_MINIMAL_STATE)
    assert msg["role"] == "user"


def test_turn_renders_species_and_turn_number() -> None:
    builder = PromptBuilder()
    content = builder.build_turn(_MINIMAL_STATE)["content"]
    assert "Turn 1" in content
    assert "Pikachu" in content
    assert "Charmander" in content


def test_turn_renders_move_name_and_bp() -> None:
    builder = PromptBuilder()
    content = builder.build_turn(_MINIMAL_STATE)["content"]
    assert "Thunderbolt" in content
    assert "90" in content


def test_turn_shows_no_revealed_moves_when_empty() -> None:
    builder = PromptBuilder()
    content = builder.build_turn(_MINIMAL_STATE)["content"]
    assert "Revealed moves: none yet" in content


def test_turn_shows_revealed_move_when_present() -> None:
    state = dict(_MINIMAL_STATE)
    state["opponent_active"] = dict(_MINIMAL_STATE["opponent_active"])
    state["opponent_active"]["revealed_moves"] = {
        "flamethrower": {
            "id": "flamethrower",
            "type": "FIRE",
            "category": "SPECIAL",
            "base_power": 90,
            "priority": 0,
        }
    }
    builder = PromptBuilder()
    content = builder.build_turn(state)["content"]
    assert "Flamethrower" in content
    assert "Revealed moves: none yet" not in content


def test_build_messages_returns_two_messages() -> None:
    builder = PromptBuilder()
    messages = builder.build_messages(_MINIMAL_STATE)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_unknown_version_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        PromptBuilder(version="v99")


def test_heuristic_advisory_section_rendered() -> None:
    builder = PromptBuilder()
    content = builder.build_turn(_MINIMAL_STATE)["content"]
    assert "HEURISTIC ADVISORY" in content
    assert "neutral (1×)" in content


def test_force_switch_text_appears() -> None:
    state = dict(_MINIMAL_STATE, force_switch=True, available_moves=[])
    builder = PromptBuilder()
    content = builder.build_turn(state)["content"]
    assert "must switch" in content
