"""StreamingPlayer — wraps any Player subclass and pushes turn events to the EventBus."""

from __future__ import annotations

from typing import Any, Optional

from poke_env.battle import AbstractBattle
from poke_env.player.battle_order import BattleOrder

from nidozo.battle.bots import RandomBot
from nidozo.battle.llm_player import LLMPlayer
from nidozo.battle.serializer import serialize_battle
from nidozo.llm.backend import ModelBackend


def _battle_event(battle: AbstractBattle, action: str, player_role: str) -> dict[str, Any]:
    state = serialize_battle(battle)
    return {
        "type": "turn",
        "battle_tag": battle.battle_tag,
        "turn": battle.turn,
        "player_role": player_role,
        "action": action,
        "state": state,
    }


class StreamingLLMPlayer(LLMPlayer):
    """LLMPlayer that additionally pushes a turn event to the EventBus after each move."""

    def __init__(self, event_bus, player_role: str = "p1", **kwargs) -> None:
        super().__init__(player_role=player_role, **kwargs)
        self._bus = event_bus
        self._player_role = player_role

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        order = await super().choose_move(battle)
        action_label = getattr(order, "message", str(order))
        await self._bus.publish(
            _battle_event(battle, action_label, self._player_role)
        )
        return order


class StreamingRandomBot(RandomBot):
    """RandomBot that pushes a turn event to the EventBus after each move."""

    def __init__(self, event_bus, player_role: str = "p1", **kwargs) -> None:
        super().__init__(**kwargs)
        self._bus = event_bus
        self._player_role = player_role

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        order = self.choose_random_move(battle)
        action_label = getattr(order, "message", str(order))
        await self._bus.publish(
            _battle_event(battle, action_label, self._player_role)
        )
        return order
