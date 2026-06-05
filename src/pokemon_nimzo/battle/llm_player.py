"""LLMPlayer — a poke-env Player driven by a ModelBackend each turn."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.player.battle_order import BattleOrder

from pokemon_nimzo.battle.action_parser import parse_action
from pokemon_nimzo.battle.serializer import serialize_battle
from pokemon_nimzo.llm.backend import ModelBackend
from pokemon_nimzo.llm.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from pokemon_nimzo.db.store import BattleStore

logger = logging.getLogger(__name__)


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
        store: Optional["BattleStore"] = None,
        battle_id: Optional[int] = None,
        player_role: str = "p1",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._prompt_builder = PromptBuilder(version=prompt_version)
        self._store = store
        self._battle_id = battle_id
        self._player_role = player_role

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        state = serialize_battle(battle)
        state_json = json.dumps(state)
        messages = self._prompt_builder.build_messages(state)
        response: Optional[str] = None

        try:
            response = await self._backend.complete(messages)
        except Exception as exc:
            logger.error("LLM backend error on turn %d: %s", battle.turn, exc)
            self._log_turn(battle.turn, None, False, None, state_json)
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
        action_chosen: Optional[str],
        parse_success: bool,
        response: Optional[str],
        state_json: Optional[str] = None,
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
