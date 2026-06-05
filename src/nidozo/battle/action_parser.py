"""
ActionParser — extracts a BattleOrder from an LLM response.

Supports two response formats:

1. JSON (v2 prompt) — tried first:
   {"reasoning": "...", "action_type": "move", "identifier": "thunderbolt"}
   {"reasoning": "...", "action_type": "switch", "identifier": "masquerain"}

2. Text (v1 prompt) — fallback regex parser:
    ACTION: move 2              — 1-based slot number
    ACTION: move thunderbolt    — move name
    ACTION: switch 3            — 1-based slot number
    ACTION: switch masquerain   — Pokémon species name
    ACTION: thunderbolt         — bare move name (no keyword)

Multiple ACTION lines are allowed in text mode; the last valid one is used.
Returns None on complete parse failure; caller falls back to random.
"""

from __future__ import annotations

import json
import logging
import re

from poke_env.battle import AbstractBattle
from poke_env.player.battle_order import BattleOrder
from poke_env.player.player import Player

logger = logging.getLogger(__name__)

# Matches "ACTION: move/switch <slot_or_name>"
# [\s*]* handles markdown variants like "**ACTION:** move X" or "**ACTION: move X**"
_ACTION_RE = re.compile(
    r"ACTION:[\s*]*(move|switch)\s+(\S+)", re.IGNORECASE
)

# Matches "ACTION: <bare_name>" with no move/switch keyword
_BARE_ACTION_RE = re.compile(
    r"ACTION:\s*([A-Za-z][\w]*)", re.IGNORECASE
)

_KEYWORDS = {"move", "switch"}


def _normalize(s: str) -> str:
    """Lowercase, strip non-alphanumeric for fuzzy name comparison."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _resolve_move(
    identifier: str,
    battle: AbstractBattle,
    player: Player,
) -> BattleOrder | None:
    """Resolve a move identifier (slot number or name) to a BattleOrder."""
    moves = battle.available_moves
    if not moves:
        logger.warning("ACTION: move requested but no moves available")
        return None

    # Try numeric slot — extract leading digits to handle trailing markdown (e.g. "2**")
    m = re.match(r"(\d+)", identifier)
    if m:
        slot = int(m.group(1))
        idx = slot - 1
        if 0 <= idx < len(moves):
            return player.create_order(moves[idx])
        logger.warning("ACTION: move slot %d out of range (have %d)", slot, len(moves))
        return None

    # Try move name match (normalized — strips any surrounding punctuation)
    norm = _normalize(identifier)
    for move in moves:
        if _normalize(move.id) == norm:
            return player.create_order(move)

    logger.debug("ACTION: move name %r not found in available moves", identifier)
    return None


def _resolve_switch(
    identifier: str,
    battle: AbstractBattle,
    player: Player,
) -> BattleOrder | None:
    """Resolve a switch identifier (slot number or species name) to a BattleOrder."""
    switches = battle.available_switches
    if not switches:
        logger.warning("ACTION: switch requested but no switches available")
        return None

    # Try numeric slot — extract leading digits to handle trailing markdown (e.g. "2**")
    m = re.match(r"(\d+)", identifier)
    if m:
        slot = int(m.group(1))
        idx = slot - 1
        if 0 <= idx < len(switches):
            return player.create_order(switches[idx])
        logger.warning("ACTION: switch slot %d out of range (have %d)", slot, len(switches))
        return None

    # Try species name match (normalized)
    norm = _normalize(identifier)
    for mon in switches:
        if _normalize(mon.species) == norm:
            return player.create_order(mon)

    logger.debug("ACTION: switch name %r not found in available switches", identifier)
    return None


def _parse_json_action(
    response: str,
    battle: AbstractBattle,
    player: Player,
) -> BattleOrder | None:
    """Try to parse response as a JSON action object (v2 prompt format).

    Expected shape: {"action_type": "move"|"switch", "identifier": "...", "reasoning": "..."}
    The 'reasoning' key is logged for context but not required for parsing.
    """
    text = response.strip()

    # Strip markdown code fences first (e.g. ```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()

    if not text.startswith("{"):
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    action_type = str(data.get("action_type", "")).lower().strip()
    identifier = str(data.get("identifier", "")).strip()

    if not action_type or not identifier:
        logger.debug("JSON action missing action_type or identifier: %s", data)
        return None

    if action_type == "move":
        order = _resolve_move(identifier, battle, player)
        if order is None:
            logger.debug("JSON: move %r not resolved — available: %s",
                         identifier, [m.id for m in battle.available_moves])
        return order
    elif action_type == "switch":
        order = _resolve_switch(identifier, battle, player)
        if order is None:
            logger.debug("JSON: switch %r not resolved — available: %s",
                         identifier, [m.species for m in battle.available_switches])
        return order
    else:
        logger.debug("JSON: unknown action_type %r", action_type)
        return None


def parse_action(
    response: str,
    battle: AbstractBattle,
    player: Player,
) -> BattleOrder | None:
    """Return a BattleOrder from the LLM response, or None on failure.

    Tries JSON parsing first (v2 prompt), then falls back to the legacy
    regex-based text parser (v1 prompt). Using the last valid ACTION line
    so a model that self-corrects mid-response gets the right answer.
    """
    if not response:
        return None

    # Pass 0: JSON structured output (v2 prompt)
    order = _parse_json_action(response, battle, player)
    if order is not None:
        return order

    # Pass 1: ACTION: move/switch <identifier>
    matches = _ACTION_RE.findall(response)
    for action_type, identifier in reversed(matches):
        at = action_type.lower()
        if at == "move":
            order = _resolve_move(identifier, battle, player)
        else:
            order = _resolve_switch(identifier, battle, player)
        if order is not None:
            return order

    # Pass 2: ACTION: <bare_name> (no move/switch keyword) — try as move name
    bare_matches = _BARE_ACTION_RE.findall(response)
    for name in reversed(bare_matches):
        if name.lower() in _KEYWORDS:
            continue
        order = _resolve_move(name, battle, player)
        if order is not None:
            logger.debug("Resolved bare ACTION: %r as move", name)
            return order

    logger.warning("No parseable action found in LLM response")
    return None
