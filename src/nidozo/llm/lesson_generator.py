"""Post-battle lesson generator.

After a battle finishes, each LLM player is asked to reflect on what happened
and produce a 2-3 sentence lesson.  The lesson is stored in the DB and injected
into future prompts so the model can adapt its strategy across battles.

The lesson call uses plain-text output (not JSON).  Callers must supply a
backend that is NOT in json_mode so that grammar sampling does not force
JSON-shaped output.
"""

from __future__ import annotations

import logging
from typing import Any

from nidozo.llm.backend import Message, ModelBackend

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a competitive Pokémon trainer reviewing your most recent battle. "
    "Your goal is to extract a concise, actionable lesson that will improve your "
    "future play. Be honest about mistakes."
)

_MAX_TURNS_SHOWN = 20  # cap turn list to keep the prompt short


def _result_label(winner: int | None, player_role: str) -> str:
    if winner is None:
        return "Draw"
    role_num = 1 if player_role == "p1" else 2
    return "Win" if winner == role_num else "Loss"


def _format_turns(turns: list[dict[str, Any]], player_role: str) -> str:
    """Format a player's turns into a compact bullet list."""
    my_turns = [t for t in turns if t.get("player_role") == player_role]
    # Most recent turns are most informative; show up to _MAX_TURNS_SHOWN
    my_turns = my_turns[-_MAX_TURNS_SHOWN:]
    if not my_turns:
        return "  (no turns recorded)"
    lines = []
    for t in my_turns:
        action = t.get("action_chosen") or "(none)"
        ok = t.get("parse_success", 1)
        flag = "" if ok else " ⚠ parse failed → random"
        lines.append(f"  Turn {t['turn_number']}: {action}{flag}")
    return "\n".join(lines)


async def generate_lesson(
    backend: ModelBackend,
    player_role: str,
    winner: int | None,
    total_turns: int,
    opponent_label: str,
    turns: list[dict[str, Any]],
) -> str:
    """Ask the LLM to reflect on the battle and return a 2-3 sentence lesson.

    Args:
        backend:        A ModelBackend instance with json_mode=False.
        player_role:    "p1" or "p2".
        winner:         1, 2, or None (tie).
        total_turns:    Total turns played.
        opponent_label: Human-readable opponent identifier (e.g. "random/random").
        turns:          Full turn log from BattleStore.get_turns_basic().

    Returns:
        A plain-text lesson string, or "" if the backend fails.
    """
    result = _result_label(winner, player_role)
    turn_summary = _format_turns(turns, player_role)

    user_content = (
        f"You just played a Gen 3 random battle.\n"
        f"Result: {result} in {total_turns} turns against {opponent_label}.\n\n"
        f"Your decisions this battle:\n{turn_summary}\n\n"
        f"Write 2-3 sentences about the single most important lesson from this battle. "
        f"Focus on type matchups, speed, switching, HP management, or a strategic mistake. "
        f"Write in first person. Plain text only — no JSON, no bullet points, no headers."
    )

    messages: list[Message] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        lesson = await backend.complete(messages)
        lesson = lesson.strip()
        if not lesson:
            logger.warning("Lesson generator returned empty string for %s", player_role)
        return lesson
    except Exception as exc:
        logger.error("Lesson generation failed for %s: %s", player_role, exc)
        return ""
