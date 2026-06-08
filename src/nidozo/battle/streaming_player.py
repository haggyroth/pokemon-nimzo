"""StreamingPlayer — wraps any Player subclass and pushes turn events to the EventBus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from poke_env.battle import AbstractBattle
from poke_env.player.battle_order import BattleOrder

from nidozo.battle.bots import RandomBot
from nidozo.battle.llm_player import LLMPlayer
from nidozo.battle.serializer import serialize_battle

if TYPE_CHECKING:
    from nidozo.api.events import EventBus


def _state_event(
    battle: AbstractBattle, player_role: str, state: dict[str, Any]
) -> dict[str, Any]:
    """Lightweight state snapshot emitted at the START of choose_move.

    Fires before the LLM is consulted so the frontend can refresh HP bars
    and active Pokémon immediately when Showdown resolves a turn, rather
    than waiting for the full LLM round-trip.
    """
    return {
        "type": "state_update",
        "battle_tag": battle.battle_tag,
        "turn": battle.turn,
        "player_role": player_role,
        "state": state,
    }


def _turn_event(
    battle: AbstractBattle, action: str, player_role: str, state: dict[str, Any]
) -> dict[str, Any]:
    """Full turn record emitted at the END of choose_move, after action is decided."""
    return {
        "type": "turn",
        "battle_tag": battle.battle_tag,
        "turn": battle.turn,
        "player_role": player_role,
        "action": action,
        "state": state,
    }


class StreamingLLMPlayer(LLMPlayer):
    """LLMPlayer that additionally pushes turn/thinking events to the EventBus."""

    def __init__(
        self,
        event_bus: EventBus,
        player_role: str = "p1",
        lessons: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        # coach is forwarded to LLMPlayer via **kwargs
        super().__init__(
            player_role=player_role,
            on_thinking=self._emit_thinking,
            lessons=lessons,
            **kwargs,
        )
        self._bus: EventBus = event_bus
        self._player_role = player_role

    async def _emit_thinking(self, event: dict[str, Any]) -> None:
        await self._bus.publish(event)

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        # Serialize once; reuse for both the early state_update and the final turn event.
        # The battle object is not mutated during choose_move (Showdown sends no new
        # messages while we're deliberating), so both events share the same snapshot.
        state = serialize_battle(battle)

        # Emit immediately so the UI refreshes HP bars / active Pokémon right when
        # Showdown resolves the previous turn, rather than after LLM think-time.
        await self._bus.publish(_state_event(battle, self._player_role, state))

        order = await super().choose_move(battle)
        action_label = getattr(order, "message", str(order))
        await self._bus.publish(_turn_event(battle, action_label, self._player_role, state))
        return order


class StreamingRandomBot(RandomBot):
    """RandomBot that pushes a turn event to the EventBus after each move."""

    def __init__(self, event_bus: EventBus, player_role: str = "p1", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bus: EventBus = event_bus
        self._player_role = player_role

    async def choose_move(self, battle: AbstractBattle) -> BattleOrder:  # type: ignore[override]
        state = serialize_battle(battle)
        await self._bus.publish(_state_event(battle, self._player_role, state))
        order = self.choose_random_move(battle)
        action_label = getattr(order, "message", str(order))
        await self._bus.publish(_turn_event(battle, action_label, self._player_role, state))
        return order
