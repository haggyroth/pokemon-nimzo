"""Tests for LLMPlayer.choose_move — the core decision loop.

All tests run without a live Showdown server:
  - poke_env.player.Player.__init__ is patched to skip network setup
  - AbstractBattle is replaced with a lightweight MagicMock
  - serialize_battle and parse_action are patched at import sites
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nidozo.battle.llm_player import LLMPlayer

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_battle():
    """Minimal battle mock for choose_move tests."""
    battle = MagicMock()
    battle.turn = 3
    battle.battle_tag = "gen3randombattle-test"
    battle.format = "gen3randombattle"
    battle.weather = {}
    battle.fields = []
    battle.side_conditions = {}
    battle.opponent_side_conditions = {}
    battle.active_pokemon = None
    battle.opponent_active_pokemon = None
    battle.team = {}
    battle.opponent_team = {}
    battle.force_switch = False
    # Two regular moves by default
    m1, m2 = MagicMock(), MagicMock()
    m1.id, m2.id = "thunderbolt", "surf"
    battle.available_moves = [m1, m2]
    battle.available_switches = []
    return battle


@pytest.fixture
def fake_order():
    order = MagicMock()
    order.message = "/choose move thunderbolt"
    return order


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.complete = AsyncMock(
        return_value='{"reasoning":"test","action_type":"move","identifier":"thunderbolt"}'
    )
    return backend


def _make_player(backend, **kwargs) -> LLMPlayer:
    """Instantiate LLMPlayer without connecting to Showdown."""
    with patch("poke_env.player.Player.__init__", return_value=None):
        player = LLMPlayer(backend=backend, **kwargs)
    player.choose_random_move = MagicMock()
    player.create_order = MagicMock()
    # Short-circuit the prompt builder so tests don't need real templates
    player._prompt_builder.build_messages = MagicMock(
        return_value=[{"role": "user", "content": "Choose your move."}]
    )
    return player


# ---------------------------------------------------------------------------
# choose_move — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_returns_parsed_order(mock_backend, mock_battle, fake_order) -> None:
    """Successful backend response → parse_action result is returned."""
    player = _make_player(mock_backend)

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        result = await player.choose_move(mock_battle)

    assert result is fake_order
    mock_backend.complete.assert_called_once()
    player.choose_random_move.assert_not_called()


@pytest.mark.asyncio
async def test_choose_move_logs_success_to_store(mock_backend, mock_battle, fake_order, tmp_path) -> None:
    """Successful turn is written to BattleStore with parse_success=True."""
    from nidozo.db.store import BattleStore

    store = BattleStore(tmp_path / "test.db")
    m_id = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("test", "gen3randombattle", m_id, m_id)

    player = _make_player(mock_backend, store=store, battle_id=bid, player_role="p1")

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        await player.choose_move(mock_battle)

    turns = store.get_turns_with_state(bid)
    assert len(turns) == 1
    assert turns[0]["player_role"] == "p1"
    assert turns[0]["parse_success"] == 1
    assert turns[0]["action_chosen"] == fake_order.message


# ---------------------------------------------------------------------------
# choose_move — recharge short-circuit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_recharge_skips_llm(mock_backend, mock_battle) -> None:
    """Single recharge move → LLM is never called; create_order is used directly."""
    recharge = MagicMock()
    recharge.id = "recharge"
    mock_battle.available_moves = [recharge]

    player = _make_player(mock_backend)
    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}):
        await player.choose_move(mock_battle)

    mock_backend.complete.assert_not_called()
    player.create_order.assert_called_once_with(recharge)


# ---------------------------------------------------------------------------
# choose_move — empty response / retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_retries_on_empty_response(mock_backend, mock_battle, fake_order) -> None:
    """First attempt returns '' → one retry → succeeds."""
    mock_backend.complete = AsyncMock(side_effect=[
        "",
        '{"action_type":"move","identifier":"surf","reasoning":"ok"}',
    ])

    player = _make_player(mock_backend)

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        result = await player.choose_move(mock_battle)

    assert result is fake_order
    assert mock_backend.complete.call_count == 2


@pytest.mark.asyncio
async def test_choose_move_empty_both_attempts_falls_back(mock_backend, mock_battle) -> None:
    """Both attempts return '' → choose_random_move, logged with parse_success=False."""
    mock_backend.complete = AsyncMock(return_value="")
    random_order = MagicMock()

    player = _make_player(mock_backend)
    player.choose_random_move.return_value = random_order

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}):
        result = await player.choose_move(mock_battle)

    assert result is random_order
    assert mock_backend.complete.call_count == 2
    player.choose_random_move.assert_called_once_with(mock_battle)


# ---------------------------------------------------------------------------
# choose_move — backend exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_backend_error_first_then_succeeds(mock_battle, fake_order) -> None:
    """Backend raises on attempt 1; succeeds on attempt 2."""
    backend = AsyncMock()
    backend.complete = AsyncMock(side_effect=[
        RuntimeError("timeout"),
        '{"action_type":"move","identifier":"thunderbolt","reasoning":"ok"}',
    ])

    player = _make_player(backend)

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        result = await player.choose_move(mock_battle)

    assert result is fake_order
    assert backend.complete.call_count == 2


@pytest.mark.asyncio
async def test_choose_move_backend_error_both_attempts_falls_back(mock_battle) -> None:
    """Backend raises both times → choose_random_move."""
    backend = AsyncMock()
    backend.complete = AsyncMock(side_effect=RuntimeError("down"))
    random_order = MagicMock()

    player = _make_player(backend)
    player.choose_random_move.return_value = random_order

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}):
        result = await player.choose_move(mock_battle)

    assert result is random_order
    player.choose_random_move.assert_called_once_with(mock_battle)


# ---------------------------------------------------------------------------
# choose_move — parse failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_parse_failure_falls_back(mock_backend, mock_battle) -> None:
    """parse_action returns None → choose_random_move."""
    random_order = MagicMock()

    player = _make_player(mock_backend)
    player.choose_random_move.return_value = random_order

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=None):
        result = await player.choose_move(mock_battle)

    assert result is random_order
    player.choose_random_move.assert_called_once_with(mock_battle)


@pytest.mark.asyncio
async def test_choose_move_parse_failure_logged(mock_backend, mock_battle, tmp_path) -> None:
    """Parse failure is written to the store with parse_success=False."""
    from nidozo.db.store import BattleStore

    store = BattleStore(tmp_path / "test.db")
    m_id = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("test", "gen3randombattle", m_id, m_id)

    player = _make_player(mock_backend, store=store, battle_id=bid, player_role="p2")
    player.choose_random_move.return_value = MagicMock()

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=None):
        await player.choose_move(mock_battle)

    turns = store.get_turns_with_state(bid)
    assert len(turns) == 1
    assert turns[0]["parse_success"] == 0


# ---------------------------------------------------------------------------
# choose_move — on_thinking callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choose_move_thinking_callback_fired(mock_backend, mock_battle, fake_order) -> None:
    """on_thinking callback is awaited with the correct event dict each turn."""
    thinking_cb = AsyncMock()

    player = _make_player(mock_backend, on_thinking=thinking_cb, player_role="p2")

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        await player.choose_move(mock_battle)

    thinking_cb.assert_called_once()
    event = thinking_cb.call_args[0][0]
    assert event["type"] == "thinking"
    assert event["player_role"] == "p2"
    assert event["turn"] == mock_battle.turn


@pytest.mark.asyncio
async def test_choose_move_thinking_callback_exception_is_swallowed(mock_backend, mock_battle, fake_order) -> None:
    """A crashing on_thinking callback does not abort the turn."""
    bad_cb = AsyncMock(side_effect=RuntimeError("boom"))

    player = _make_player(mock_backend, on_thinking=bad_cb)

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        result = await player.choose_move(mock_battle)

    # Despite the callback raising, we still got a valid order
    assert result is fake_order


# ---------------------------------------------------------------------------
# _log_turn — no-op without store
# ---------------------------------------------------------------------------

def test_log_turn_no_op_without_store(mock_backend) -> None:
    """_log_turn is silent when no store is configured."""
    player = _make_player(mock_backend)
    # Should not raise even without a store
    player._log_turn(1, "/choose move thunderbolt", True, "response", "{}")


# ---------------------------------------------------------------------------
# StreamingLLMPlayer — publishes turn event to the EventBus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_streaming_llm_player_publishes_turn_event(mock_battle, fake_order) -> None:
    """StreamingLLMPlayer.choose_move publishes a 'turn' event via the bus."""
    from nidozo.api.events import EventBus
    from nidozo.battle.streaming_player import StreamingLLMPlayer

    bus = EventBus()
    queue = bus.subscribe()
    backend = AsyncMock()
    backend.complete = AsyncMock(
        return_value='{"action_type":"move","identifier":"thunderbolt","reasoning":"ok"}'
    )

    with patch("poke_env.player.Player.__init__", return_value=None):
        player = StreamingLLMPlayer(event_bus=bus, player_role="p1", backend=backend)

    player.choose_random_move = MagicMock()
    player.create_order = MagicMock()
    player._prompt_builder.build_messages = MagicMock(
        return_value=[{"role": "user", "content": "Choose."}]
    )

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.serializer.serialize_battle", return_value={}), \
         patch("nidozo.battle.streaming_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        result = await player.choose_move(mock_battle)

    assert result is fake_order
    # Drain and collect events (thinking + turn)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    turn_events = [e for e in events if e["type"] == "turn"]
    assert len(turn_events) == 1
    assert turn_events[0]["player_role"] == "p1"
    assert turn_events[0]["turn"] == mock_battle.turn
    assert turn_events[0]["action"] == fake_order.message


@pytest.mark.asyncio
async def test_streaming_llm_player_thinking_event_before_turn_event(mock_battle, fake_order) -> None:
    """StreamingLLMPlayer emits 'thinking' event before 'turn' event."""
    from nidozo.api.events import EventBus
    from nidozo.battle.streaming_player import StreamingLLMPlayer

    bus = EventBus()
    queue = bus.subscribe()
    backend = AsyncMock()
    backend.complete = AsyncMock(
        return_value='{"action_type":"move","identifier":"thunderbolt","reasoning":"ok"}'
    )

    with patch("poke_env.player.Player.__init__", return_value=None):
        player = StreamingLLMPlayer(event_bus=bus, player_role="p2", backend=backend)

    player.choose_random_move = MagicMock()
    player.create_order = MagicMock()
    player._prompt_builder.build_messages = MagicMock(
        return_value=[{"role": "user", "content": "Choose."}]
    )

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.streaming_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        await player.choose_move(mock_battle)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "turn" in types
    assert types.index("thinking") < types.index("turn")


# ---------------------------------------------------------------------------
# StreamingRandomBot — publishes turn event from a random bot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_streaming_random_bot_publishes_turn_event(mock_battle) -> None:
    """StreamingRandomBot.choose_move calls choose_random_move and publishes a turn."""
    from nidozo.api.events import EventBus
    from nidozo.battle.streaming_player import StreamingRandomBot

    bus = EventBus()
    queue = bus.subscribe()

    with patch("poke_env.player.Player.__init__", return_value=None):
        bot = StreamingRandomBot(event_bus=bus, player_role="p2")

    random_order = MagicMock()
    random_order.message = "/choose move surf"
    bot.choose_random_move = MagicMock(return_value=random_order)

    with patch("nidozo.battle.streaming_player.serialize_battle", return_value={}):
        result = await bot.choose_move(mock_battle)

    assert result is random_order
    bot.choose_random_move.assert_called_once_with(mock_battle)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert len(events) == 1
    assert events[0]["type"] == "turn"
    assert events[0]["player_role"] == "p2"
    assert events[0]["action"] == "/choose move surf"


# ---------------------------------------------------------------------------
# RandomBot — structural sanity check (no network needed)
# ---------------------------------------------------------------------------

def test_random_bot_is_subclass_of_random_player() -> None:
    """RandomBot is a RandomPlayer subclass — no logic to test, just the inheritance."""
    from poke_env.player import RandomPlayer

    from nidozo.battle.bots import RandomBot

    assert issubclass(RandomBot, RandomPlayer)
