"""LLMPlayer — a poke-env Player driven by a ModelBackend each turn."""

from __future__ import annotations

import logging

from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.player.battle_order import BattleOrder

from pokemon_nimzo.battle.action_parser import parse_action
from pokemon_nimzo.battle.serializer import serialize_battle
from pokemon_nimzo.llm.backend import ModelBackend
from pokemon_nimzo.llm.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class LLMPlayer(Player):
    """A Pokémon Showdown player whose moves are chosen by an LLM.

    Args:
        backend: Any object satisfying the ModelBackend protocol.
        prompt_version: Prompt template version to use (default "v1").
        **kwargs: Passed through to poke-env's Player base class
                  (battle_format, server_configuration, etc.).
    """

    def __init__(
        self,
        backend: ModelBackend,
        prompt_version: str = "v1",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._prompt_builder = PromptBuilder(version=prompt_version)

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        state = serialize_battle(battle)
        messages = self._prompt_builder.build_messages(state)

        try:
            response = await self._backend.complete(messages)
        except Exception as exc:
            logger.error("LLM backend error on turn %d: %s", battle.turn, exc)
            return self.choose_random_move(battle)

        order = parse_action(response, battle, self)
        if order is None:
            logger.warning(
                "Action parse failed on turn %d — falling back to random move.\n"
                "Response was:\n%s",
                battle.turn,
                response,
            )
            return self.choose_random_move(battle)

        return order
