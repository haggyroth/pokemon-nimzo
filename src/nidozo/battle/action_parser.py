"""
ActionParser — extracts a BattleOrder from an LLM response.

Expected format at end of response:
    ACTION: move <1-based slot>
    ACTION: switch <1-based slot>

If parsing fails for any reason (bad format, out-of-range slot, no legal
moves matching the slot), returns None. The caller is responsible for
falling back to a safe default (typically a random legal move).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from poke_env.battle import AbstractBattle
from poke_env.player.battle_order import BattleOrder
from poke_env.player.player import Player

logger = logging.getLogger(__name__)

# Matches the last occurrence of ACTION: move N or ACTION: switch N
_ACTION_RE = re.compile(
    r"ACTION:\s*(move|switch)\s+(\d+)", re.IGNORECASE
)


def parse_action(
    response: str,
    battle: AbstractBattle,
    player: Player,
) -> Optional[BattleOrder]:
    """Return a BattleOrder from the LLM response, or None on failure."""
    matches = _ACTION_RE.findall(response)
    if not matches:
        logger.warning("No ACTION line found in LLM response")
        return None

    # Take the last match in case the model repeated itself mid-reasoning
    action_type, slot_str = matches[-1]
    slot = int(slot_str)

    if action_type.lower() == "move":
        moves = battle.available_moves
        if not moves:
            logger.warning("ACTION: move requested but no moves available")
            return None
        idx = slot - 1
        if idx < 0 or idx >= len(moves):
            logger.warning(
                "ACTION: move slot %d out of range (have %d moves)", slot, len(moves)
            )
            return None
        return player.create_order(moves[idx])

    if action_type.lower() == "switch":
        switches = battle.available_switches
        if not switches:
            logger.warning("ACTION: switch requested but no switches available")
            return None
        idx = slot - 1
        if idx < 0 or idx >= len(switches):
            logger.warning(
                "ACTION: switch slot %d out of range (have %d switches)",
                slot,
                len(switches),
            )
            return None
        return player.create_order(switches[idx])

    return None
