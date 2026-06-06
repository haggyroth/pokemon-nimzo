"""Tests for the Lessons / Memory feature.

Covers:
  - BattleStore.create_lesson / get_lessons
  - lesson_generator.generate_lesson
  - PromptBuilder memory injection
  - LLMPlayer lesson threading
  - GET /api/models/{model_id}/lessons endpoint
  - Schema v5 migration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# BattleStore — lesson persistence
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    from nidozo.db.store import BattleStore
    return BattleStore(tmp_path / "test.db")


@pytest.fixture
def battle_with_models(store):
    """Returns (battle_id, p1_model_id, p2_model_id)."""
    p1 = store.get_or_create_model("anthropic", "claude-test", "v2")
    p2 = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("tag-1", "gen3randombattle", p1, p2)
    return bid, p1, p2


def test_create_lesson_returns_id(store, battle_with_models) -> None:
    bid, p1, _ = battle_with_models
    lesson_id = store.create_lesson(p1, bid, "I should switch more aggressively.")
    assert isinstance(lesson_id, int)
    assert lesson_id > 0


def test_get_lessons_returns_stored(store, battle_with_models) -> None:
    bid, p1, _ = battle_with_models
    store.create_lesson(p1, bid, "Lesson one.")
    store.create_lesson(p1, bid, "Lesson two.")
    lessons = store.get_lessons(p1)
    assert len(lessons) == 2
    # Newest first
    assert lessons[0]["content"] == "Lesson two."
    assert lessons[1]["content"] == "Lesson one."


def test_get_lessons_respects_limit(store, battle_with_models) -> None:
    bid, p1, _ = battle_with_models
    for i in range(8):
        store.create_lesson(p1, bid, f"Lesson {i}.")
    assert len(store.get_lessons(p1, limit=5)) == 5


def test_get_lessons_isolated_by_model(store, battle_with_models) -> None:
    bid, p1, p2 = battle_with_models
    store.create_lesson(p1, bid, "P1 lesson.")
    assert store.get_lessons(p2) == []


def test_get_lessons_empty_when_none(store, battle_with_models) -> None:
    _, p1, _ = battle_with_models
    assert store.get_lessons(p1) == []


def test_lesson_row_has_expected_fields(store, battle_with_models) -> None:
    bid, p1, _ = battle_with_models
    store.create_lesson(p1, bid, "Speed matters.")
    row = store.get_lessons(p1)[0]
    assert "content" in row
    assert "battle_id" in row
    assert "created_at" in row
    assert row["battle_id"] == bid


# ---------------------------------------------------------------------------
# lesson_generator.generate_lesson
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_lesson_returns_text() -> None:
    """generate_lesson returns the backend's response string."""
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="  I should use Water-types more.  ")

    result = await generate_lesson(
        backend=backend,
        player_role="p1",
        winner=1,
        total_turns=20,
        opponent_label="random/random",
        turns=[],
    )
    assert result == "I should use Water-types more."
    backend.complete.assert_called_once()


@pytest.mark.asyncio
async def test_generate_lesson_win_label() -> None:
    """System/user messages reflect the correct result label."""
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="Win lesson.")

    await generate_lesson(backend, "p1", winner=1, total_turns=10,
                          opponent_label="random/random", turns=[])
    call_msgs = backend.complete.call_args[0][0]
    user_content = next(m["content"] for m in call_msgs if m["role"] == "user")
    assert "Win" in user_content


@pytest.mark.asyncio
async def test_generate_lesson_loss_label() -> None:
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="Loss lesson.")

    await generate_lesson(backend, "p1", winner=2, total_turns=10,
                          opponent_label="random/random", turns=[])
    call_msgs = backend.complete.call_args[0][0]
    user_content = next(m["content"] for m in call_msgs if m["role"] == "user")
    assert "Loss" in user_content


@pytest.mark.asyncio
async def test_generate_lesson_draw_label() -> None:
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="Draw lesson.")

    await generate_lesson(backend, "p2", winner=None, total_turns=10,
                          opponent_label="random/random", turns=[])
    call_msgs = backend.complete.call_args[0][0]
    user_content = next(m["content"] for m in call_msgs if m["role"] == "user")
    assert "Draw" in user_content


@pytest.mark.asyncio
async def test_generate_lesson_includes_turn_summary() -> None:
    """Turn actions appear in the user message."""
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="ok")
    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "thunderbolt", "parse_success": 1},
        {"turn_number": 2, "player_role": "p2", "action_chosen": "surf", "parse_success": 1},
    ]
    await generate_lesson(backend, "p1", winner=1, total_turns=2,
                          opponent_label="random/random", turns=turns)
    user_content = backend.complete.call_args[0][0][1]["content"]
    assert "thunderbolt" in user_content
    assert "surf" not in user_content  # p2's turns excluded


@pytest.mark.asyncio
async def test_generate_lesson_backend_error_returns_empty() -> None:
    """If the backend raises, generate_lesson returns '' without re-raising."""
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(side_effect=RuntimeError("API down"))

    result = await generate_lesson(backend, "p1", winner=1, total_turns=5,
                                   opponent_label="opp", turns=[])
    assert result == ""


@pytest.mark.asyncio
async def test_generate_lesson_empty_response_returns_empty() -> None:
    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="   ")

    result = await generate_lesson(backend, "p2", winner=None, total_turns=5,
                                   opponent_label="opp", turns=[])
    assert result == ""


# ---------------------------------------------------------------------------
# PromptBuilder — lesson injection
# ---------------------------------------------------------------------------

def test_prompt_builder_no_lessons_unchanged() -> None:
    """build_system without lessons returns the unmodified system text."""
    from nidozo.llm.prompt_builder import PromptBuilder

    pb = PromptBuilder(version="v2")
    msg = pb.build_system(lessons=None)
    assert "Battle Memory" not in msg["content"]


def test_prompt_builder_lessons_injected() -> None:
    """build_system with lessons appends the memory section to the system prompt."""
    from nidozo.llm.prompt_builder import PromptBuilder

    pb = PromptBuilder(version="v2")
    lessons = ["Use Water-types against Fire.", "Switch early when outmatched."]
    msg = pb.build_system(lessons=lessons)

    assert "Battle Memory" in msg["content"]
    assert "Use Water-types against Fire." in msg["content"]
    assert "Switch early when outmatched." in msg["content"]


def test_prompt_builder_empty_lessons_list_no_injection() -> None:
    """An empty list is treated the same as None — no memory section added."""
    from nidozo.llm.prompt_builder import PromptBuilder

    pb = PromptBuilder(version="v2")
    msg = pb.build_system(lessons=[])
    assert "Battle Memory" not in msg["content"]


def test_prompt_builder_lessons_numbered() -> None:
    """Lessons are numbered 1, 2, 3... in the memory section."""
    from nidozo.llm.prompt_builder import PromptBuilder

    pb = PromptBuilder(version="v2")
    msg = pb.build_system(lessons=["Alpha.", "Beta.", "Gamma."])

    assert "1. Alpha." in msg["content"]
    assert "2. Beta." in msg["content"]
    assert "3. Gamma." in msg["content"]


# ---------------------------------------------------------------------------
# LLMPlayer — lessons passed to build_messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_player_passes_lessons_to_prompt_builder() -> None:
    """LLMPlayer calls build_messages with the lessons list it was given."""
    backend = AsyncMock()
    backend.complete = AsyncMock(
        return_value='{"action_type":"move","identifier":"thunderbolt","reasoning":"ok"}'
    )

    with patch("poke_env.player.Player.__init__", return_value=None):
        from nidozo.battle.llm_player import LLMPlayer
        player = LLMPlayer(backend=backend, lessons=["Always check speed tiers."])

    player.choose_random_move = MagicMock()
    player.create_order = MagicMock()

    build_spy = MagicMock(return_value=[{"role": "user", "content": "go"}])
    player._prompt_builder.build_messages = build_spy

    battle = MagicMock()
    battle.turn = 1
    battle.available_moves = [MagicMock(id="thunderbolt"), MagicMock(id="surf")]
    battle.available_switches = []

    fake_order = MagicMock()
    fake_order.message = "/choose move thunderbolt"

    with patch("nidozo.battle.llm_player.serialize_battle", return_value={}), \
         patch("nidozo.battle.llm_player.parse_action", return_value=fake_order):
        await player.choose_move(battle)

    build_spy.assert_called_once()
    _, kwargs = build_spy.call_args
    assert kwargs.get("lessons") == ["Always check speed tiers."]


# ---------------------------------------------------------------------------
# GET /api/models/{model_id}/lessons
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    from nidozo.api.app import create_app
    return create_app(db_path=tmp_path / "test.db")


@pytest.fixture
def api_client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_get_lessons_endpoint_empty(api_client, app) -> None:
    """Returns empty list for model with no lessons."""
    store = app.state.store
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")

    resp = await api_client.get(f"/api/models/{mid}/lessons")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_lessons_endpoint_returns_lessons(api_client, app) -> None:
    """Returns lessons for a model that has them."""
    store = app.state.store
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    p2 = store.get_or_create_model("random", "random", "v2")
    bid = store.create_battle("tag-x", "gen3randombattle", mid, p2)
    store.create_lesson(mid, bid, "Fire beats Grass.")

    resp = await api_client.get(f"/api/models/{mid}/lessons")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Fire beats Grass."


@pytest.mark.asyncio
async def test_get_lessons_endpoint_respects_limit(api_client, app) -> None:
    """?limit= parameter is forwarded to the store."""
    store = app.state.store
    mid = store.get_or_create_model("anthropic", "claude-test", "v2")
    p2 = store.get_or_create_model("random", "random", "v2")
    for i in range(7):
        bid = store.create_battle(f"tag-{i}", "gen3randombattle", mid, p2)
        store.create_lesson(mid, bid, f"Lesson {i}.")

    resp = await api_client.get(f"/api/models/{mid}/lessons?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# Schema v5 migration
# ---------------------------------------------------------------------------

def test_schema_v5_fresh_install_has_lessons_table() -> None:
    """Fresh install creates the lessons table."""
    import sqlite3

    from nidozo.db.schema import migrate

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "lessons" in tables


def test_schema_v5_migration_from_v4() -> None:
    """Upgrading a v4 DB creates the lessons table and index."""
    import sqlite3

    from nidozo.db.schema import migrate

    # Build a minimal v4 DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate(conn)  # fresh v5 install

    # Downgrade to v4 to simulate an existing DB
    conn.execute("UPDATE schema_version SET version=4")
    conn.execute("DROP TABLE IF EXISTS lessons")
    conn.execute("DROP INDEX IF EXISTS idx_lessons_model")
    conn.commit()

    migrate(conn)

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}

    assert "lessons" in tables
    assert "idx_lessons_model" in indexes
    version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    assert version == 6  # migrate() always brings to current SCHEMA_VERSION


# ---------------------------------------------------------------------------
# generate_lesson — analysis enrichment  (feat/richer-analysis)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_lesson_with_analysis_includes_context() -> None:
    """generate_lesson embeds analysis context when analysis dict is provided."""
    from unittest.mock import AsyncMock

    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="I learned to avoid splash vs immune types.")

    analysis = {
        "p1_summary": {
            "total_turns": 4,
            "optimal": 2,
            "good": 1,
            "suboptimal": 1,
            "fallback": 0,
            "switch": 0,
            "no_data": 0,
            "blunders": 1,
            "avg_heuristic_rank": 1.75,
        },
        "p2_summary": {"total_turns": 0},
        "key_moments": [
            {
                "turn_number": 3,
                "player_role": "p1",
                "type": "blunder",
                "description": "chose splash (rank 4/4, 62% below best); heuristic top: thunderbolt",
            },
        ],
        "turning_point": 3,
    }

    turns: list[dict] = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": "/choose move thunderbolt", "parse_success": 1},
        {"turn_number": 2, "player_role": "p1", "action_chosen": "/choose move thunderbolt", "parse_success": 1},
        {"turn_number": 3, "player_role": "p1", "action_chosen": "/choose move splash",      "parse_success": 1},
        {"turn_number": 4, "player_role": "p1", "action_chosen": "/choose move tackle",       "parse_success": 1},
    ]

    lesson = await generate_lesson(
        backend=backend,
        player_role="p1",
        winner=1,
        total_turns=4,
        opponent_label="random/random",
        turns=turns,
        analysis=analysis,
    )

    assert lesson == "I learned to avoid splash vs immune types."

    # The prompt passed to backend.complete should contain analysis context
    call_args = backend.complete.call_args
    prompt_messages = call_args[0][0]
    user_msg = next(m["content"] for m in prompt_messages if m["role"] == "user")
    assert "Post-battle analysis" in user_msg
    assert "blunder" in user_msg.lower() or "Blunder" in user_msg
    assert "Turn 3" in user_msg
    assert "splash" in user_msg.lower()


@pytest.mark.asyncio
async def test_generate_lesson_without_analysis_unchanged() -> None:
    """generate_lesson works as before when analysis=None."""
    from unittest.mock import AsyncMock

    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="Keep attacking.")

    lesson = await generate_lesson(
        backend=backend,
        player_role="p2",
        winner=2,
        total_turns=5,
        opponent_label="lmstudio/llama",
        turns=[
            {"turn_number": 1, "player_role": "p2", "action_chosen": "/choose move tackle", "parse_success": 1},
        ],
        analysis=None,
    )

    assert lesson == "Keep attacking."
    call_args = backend.complete.call_args
    prompt_messages = call_args[0][0]
    user_msg = next(m["content"] for m in prompt_messages if m["role"] == "user")
    assert "Post-battle analysis" not in user_msg


def test_format_analysis_context_empty_summary() -> None:
    """_format_analysis_context returns '' for a zero-turn summary."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 0},
        "key_moments": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert ctx == ""


def test_format_analysis_context_includes_rng() -> None:
    """RNG events are included in the analysis context."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {
            "total_turns": 2,
            "optimal": 2,
            "good": 0,
            "suboptimal": 0,
            "fallback": 0,
            "switch": 0,
            "no_data": 0,
            "blunders": 0,
            "avg_heuristic_rank": 1.0,
        },
        "key_moments": [
            {
                "turn_number": 5,
                "player_role": "p1",
                "type": "rng",
                "description": "Possible Crit — may have shifted battle outcome",
            }
        ],
        "turning_point": 5,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "RNG" in ctx
    assert "Turn 5" in ctx
    assert "Crit" in ctx
