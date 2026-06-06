"""LLMPlayer — a poke-env Player driven by a ModelBackend each turn."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.player.battle_order import BattleOrder

from nidozo.battle.action_parser import parse_action
from nidozo.battle.serializer import serialize_battle
from nidozo.llm.backend import ModelBackend
from nidozo.llm.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from nidozo.db.store import BattleStore

logger = logging.getLogger(__name__)

# Callback type: async fn(event_dict) — injected by StreamingLLMPlayer
ThinkingCallback = Callable[[dict[str, Any]], Coroutine] | None


class LLMPlayer(Player):
    """A Pokémon Showdown player whose moves are chosen by an LLM.

    Args:
        backend: Any object satisfying the ModelBackend protocol.
        prompt_version: Prompt template version to use (default "v1").
        store: Optional BattleStore for turn logging.
        battle_id: DB battle id — required when store is provided.
        player_role: "p1" or "p2" — required when store is provided.
        **kwargs: Passed through to poke-env's Player base class.
    """

    def __init__(
        self,
        backend: ModelBackend,
        prompt_version: str = "v1",
        store: BattleStore | None = None,
        battle_id: int | None = None,
        player_role: str = "p1",
        on_thinking: ThinkingCallback = None,
        lessons: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._prompt_builder = PromptBuilder(version=prompt_version)
        self._store = store
        self._battle_id = battle_id
        self._player_role = player_role
        self._on_thinking = on_thinking
        self._lessons = lessons or []

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        # Recharge turn (e.g. after Hyper Beam): only one forced pseudo-move, skip LLM
        moves = battle.available_moves
        if len(moves) == 1 and moves[0].id == "recharge":
            return self.create_order(moves[0])

        state = serialize_battle(battle)
        state_json = json.dumps(state)
        messages = self._prompt_builder.build_messages(
            state, lessons=self._lessons or None
        )
        response: str | None = None

        # Notify listeners that the model is thinking (for UI spinner)
        if self._on_thinking is not None:
            try:
                await self._on_thinking({
                    "type": "thinking",
                    "player_role": self._player_role,
                    "turn": battle.turn,
                })
            except Exception:
                pass

        # Call LLM with one retry on empty response
        for attempt in range(2):
            try:
                response = await self._backend.complete(messages)
            except Exception as exc:
                logger.error("LLM backend error on turn %d (attempt %d): %s", battle.turn, attempt + 1, exc)
                if attempt == 1:
                    self._log_turn(battle.turn, None, False, None, state_json)
                    return self.choose_random_move(battle)
                continue

            if response:
                break

            if attempt == 0:
                logger.warning(
                    "Empty response from LLM on turn %d — retrying once.", battle.turn
                )

        if not response:
            logger.warning(
                "LLM returned empty response on turn %d after retry — falling back to random.",
                battle.turn,
            )
            self._log_turn(battle.turn, None, False, "", state_json)
            return self.choose_random_move(battle)

        order = parse_action(response, battle, self)
        if order is None:
            logger.warning(
                "Action parse failed on turn %d — falling back to random move.\n"
                "Response was:\n%s",
                battle.turn,
                response,
            )
            self._log_turn(battle.turn, None, False, response, state_json)
            return self.choose_random_move(battle)

        action_label = getattr(order, "message", str(order))
        self._log_turn(battle.turn, action_label, True, response, state_json)
        return order

    def _log_turn(
        self,
        turn_number: int,
        action_chosen: str | None,
        parse_success: bool,
        response: str | None,
        state_json: str | None = None,
    ) -> None:
        if self._store is None or self._battle_id is None:
            return
        try:
            self._store.log_turn(
                battle_id=self._battle_id,
                turn_number=turn_number,
                player_role=self._player_role,
                prompt_version=self._prompt_builder.version,
                action_chosen=action_chosen,
                parse_success=parse_success,
                llm_response=response,
                state_json=state_json,
            )
        except Exception as exc:
            logger.warning("Failed to log turn: %s", exc)
