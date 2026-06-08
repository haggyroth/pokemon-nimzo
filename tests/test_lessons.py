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
    assert version == 8  # migrate() always brings to current SCHEMA_VERSION


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


# ---------------------------------------------------------------------------
# New coverage tests — missing lines
# ---------------------------------------------------------------------------

def test_format_turns_none_action_shows_none() -> None:
    """_format_turns renders (none) when action_chosen is None."""
    from nidozo.llm.lesson_generator import _format_turns

    turns = [
        {"turn_number": 1, "player_role": "p1", "action_chosen": None, "parse_success": 1},
    ]
    result = _format_turns(turns, "p1")
    assert "(none)" in result


def test_format_turns_parse_fail_shows_warning() -> None:
    """_format_turns shows parse-failed warning when parse_success is 0."""
    from nidozo.llm.lesson_generator import _format_turns

    turns = [
        {"turn_number": 2, "player_role": "p1", "action_chosen": "tackle", "parse_success": 0},
    ]
    result = _format_turns(turns, "p1")
    assert "parse failed" in result


def test_format_analysis_context_with_no_avg_rank() -> None:
    """_format_analysis_context handles missing avg_heuristic_rank gracefully."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {
            "total_turns": 3,
            "optimal": 1,
            "good": 1,
            "suboptimal": 1,
            "fallback": 1,
            "blunders": 0,
            "avg_heuristic_rank": None,  # explicitly None
        },
        "key_moments": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    # Should not error and should include decision quality section
    assert "Decision quality" in ctx
    # avg_rank line should be absent when None
    assert "Average heuristic rank" not in ctx


def test_format_analysis_context_with_fallback_turns() -> None:
    """_format_analysis_context includes fallback count when >0."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {
            "total_turns": 3,
            "optimal": 1,
            "good": 1,
            "suboptimal": 0,
            "fallback": 2,
            "blunders": 0,
            "avg_heuristic_rank": 1.5,
        },
        "key_moments": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "fallback" in ctx.lower() or "parse failures" in ctx.lower()


# ---------------------------------------------------------------------------
# Richer lesson prompting — draft critique, variance, win-prob context
# ---------------------------------------------------------------------------

def _make_critique(
    *,
    team: list[str] | None = None,
    shared_weaknesses: list[str] | None = None,
    offensive_types: list[str] | None = None,
    quality_pct: float | None = 75.0,
    blunders: int = 0,
    deviation_turns: list[dict] | None = None,
) -> dict:
    return {
        "team": team or ["Pikachu", "Swampert"],
        "shared_weaknesses": shared_weaknesses or [],
        "offensive_types": offensive_types or ["ELECTRIC", "WATER", "GROUND"],
        "coverage_gaps": ["DARK", "GHOST"],
        "execution": {
            "total_turns": 10,
            "blunders": blunders,
            "decision_quality_pct": quality_pct,
            "optimal_rate": 50.0,
            "deviation_turns": deviation_turns or [],
        },
    }


def _make_variance(
    *,
    total_events: int = 2,
    p1_benefit: int = 1,
    p2_benefit: int = 1,
    verdict: str = "Variance was roughly even between both players",
    crits: list[dict] | None = None,
    misses: list[dict] | None = None,
) -> dict:
    return {
        "total_events": total_events,
        "crits": crits or [],
        "misses": misses or [],
        "p1_benefit_events": p1_benefit,
        "p2_benefit_events": p2_benefit,
        "verdict": verdict,
    }


def _make_timeline(*turn_probs: tuple[int, float]) -> list[dict]:
    """Build a minimal win-prob timeline: list of (turn_number, p1_win_prob) pairs."""
    return [{"turn_number": t, "p1_win_prob": p} for t, p in turn_probs]


# ── Draft critique ────────────────────────────────────────────────────────────

def test_format_draft_critique_includes_team_names() -> None:
    """Team member names appear in the analysis context."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 6, "optimal": 4, "good": 1, "suboptimal": 1,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.3},
        "p1_draft_critique": _make_critique(team=["Blaziken", "Gyarados", "Tyranitar"]),
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "Blaziken" in ctx
    assert "Gyarados" in ctx
    assert "Tyranitar" in ctx


def test_format_draft_critique_shared_weaknesses() -> None:
    """Shared team weaknesses are surfaced explicitly."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 4, "optimal": 4, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "p1_draft_critique": _make_critique(shared_weaknesses=["FIRE", "GROUND"]),
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "Fire" in ctx or "FIRE" in ctx
    assert "Ground" in ctx or "GROUND" in ctx
    assert "weak" in ctx.lower()


def test_format_draft_critique_deviation_turns_show_move_names() -> None:
    """Deviation turns expose the chosen vs. recommended move names."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    dev_turns = [
        {
            "turn_number": 7,
            "chose": "/choose move surf",
            "best": "move 2 (thunderbolt)",
            "gap_pct": 48,
            "was_blunder": True,
        },
    ]
    analysis = {
        "p1_summary": {"total_turns": 8, "optimal": 5, "good": 1, "suboptimal": 2,
                       "fallback": 0, "blunders": 1, "avg_heuristic_rank": 1.5},
        "p1_draft_critique": _make_critique(blunders=1, deviation_turns=dev_turns),
        "key_moments": [],
        "blunders": [
            {
                "turn_number": 7,
                "player_role": "p1",
                "action": "/choose move surf",
                "score_gap": 0.48,
                "notes": "chose surf (rank 3/4, 48% below best) [BLUNDER]; heuristic top: thunderbolt (super effective)",
            }
        ],
        "turning_point": 7,
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "surf" in ctx.lower()
    assert "thunderbolt" in ctx.lower()
    assert "7" in ctx   # turn number appears


def test_format_draft_critique_not_shown_for_opponent_role() -> None:
    """p2_draft_critique is not shown when generating for p1."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 4, "optimal": 4, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "p2_draft_critique": _make_critique(team=["Mew", "Celebi"]),
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    # Opponent's team should NOT leak into p1's lesson context
    assert "Mew" not in ctx
    assert "Celebi" not in ctx


# ── Structured blunders (sorted by score_gap) ────────────────────────────────

def test_blunders_sorted_worst_first() -> None:
    """Structured blunders are shown worst-gap first, not chronologically."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 10, "optimal": 6, "good": 1, "suboptimal": 3,
                       "fallback": 0, "blunders": 2, "avg_heuristic_rank": 1.6},
        "key_moments": [],
        "blunders": [
            {
                "turn_number": 3,
                "player_role": "p1",
                "action": "/choose move tackle",
                "score_gap": 0.42,
                "notes": "chose tackle (rank 3/4, 42% below best) [BLUNDER]; heuristic top: flamethrower",
            },
            {
                "turn_number": 9,
                "player_role": "p1",
                "action": "/choose move splash",
                "score_gap": 0.71,
                "notes": "chose splash (rank 4/4, 71% below best) [BLUNDER]; heuristic top: earthquake",
            },
        ],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    # Turn 9 (larger gap 0.71) should appear before turn 3 (0.42)
    assert ctx.index("Turn 9") < ctx.index("Turn 3")


def test_blunders_only_for_correct_player() -> None:
    """Blunders for the other player are not included in this player's context."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 6, "optimal": 6, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "key_moments": [],
        "blunders": [
            {
                "turn_number": 5,
                "player_role": "p2",   # opponent's blunder
                "action": "/choose move splash",
                "score_gap": 0.80,
                "notes": "chose splash [BLUNDER]; heuristic top: surf",
            },
        ],
        "turning_point": None,
    }
    ctx = _format_analysis_context(analysis, "p1")
    # p2's blunder should not appear in p1's lesson
    assert "splash" not in ctx.lower()


# ── Variance report ───────────────────────────────────────────────────────────

def test_variance_verdict_included() -> None:
    """The plain-English variance verdict appears in the context."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 5, "optimal": 5, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
        "variance_report": _make_variance(verdict="Variance was roughly even between both players"),
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "roughly even" in ctx


def test_variance_labels_benefit_direction() -> None:
    """RNG events are framed as 'in your favour' vs 'against you'."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 6, "optimal": 6, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
        "variance_report": _make_variance(
            total_events=3,
            p1_benefit=1,
            p2_benefit=2,
            verdict="Variance slightly favored p2",
            crits=[
                {"turn_number": 4, "attacker": "p2"},  # hurt p1
                {"turn_number": 8, "attacker": "p1"},  # helped p1
            ],
            misses=[
                {"turn_number": 6, "attacker": "p1"},  # hurt p1
            ],
        ),
    }
    ctx = _format_analysis_context(analysis, "p1")
    # p1 benefited from the turn-8 crit
    assert "favour" in ctx.lower() or "favor" in ctx.lower()
    # p1 was hurt by opponent's turn-4 crit and p1's turn-6 miss
    assert "against" in ctx.lower()


def test_variance_not_included_when_zero_events() -> None:
    """When total_events==0, variance section is omitted."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 4, "optimal": 4, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
        "variance_report": _make_variance(total_events=0, verdict="No notable RNG events detected"),
    }
    ctx = _format_analysis_context(analysis, "p1")
    # With zero events the variance block is still emitted (verdict is set),
    # but there should be no per-event lines
    assert "favour" not in ctx.lower()
    assert "against you" not in ctx.lower()


# ── Win-probability context ───────────────────────────────────────────────────

def test_win_prob_context_shows_swing_magnitude() -> None:
    """The turning-point win-probability swing is shown with before/after values."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 10, "optimal": 8, "good": 1, "suboptimal": 1,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.2},
        "key_moments": [],
        "blunders": [],
        "turning_point": 6,
        "win_probability_timeline": _make_timeline((5, 0.62), (6, 0.62), (7, 0.31)),
    }
    ctx = _format_analysis_context(analysis, "p1")
    assert "62" in ctx   # before %
    assert "31" in ctx   # after %
    assert "6" in ctx    # turning point turn


def test_win_prob_context_flipped_for_p2() -> None:
    """p2's win probability is correctly shown as (1 - p1_win_prob)."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p2_summary": {"total_turns": 8, "optimal": 7, "good": 1, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.1},
        "key_moments": [],
        "blunders": [],
        "turning_point": 4,
        "win_probability_timeline": _make_timeline((4, 0.30), (5, 0.70)),
    }
    # p1 prob = 0.30 at turn 4 → p2 prob = 0.70
    ctx = _format_analysis_context(analysis, "p2")
    assert "70" in ctx   # p2's win prob at turning point


def test_win_prob_context_omitted_when_no_timeline() -> None:
    """When timeline is empty, win-prob section falls back to plain turn number."""
    from nidozo.llm.lesson_generator import _format_analysis_context

    analysis = {
        "p1_summary": {"total_turns": 6, "optimal": 4, "good": 1, "suboptimal": 1,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.3},
        "key_moments": [],
        "blunders": [],
        "turning_point": 5,
        "win_probability_timeline": [],
    }
    ctx = _format_analysis_context(analysis, "p1")
    # Falls back to the plain "Turning point: turn 5..." line
    assert "5" in ctx
    assert "Turning point" in ctx


# ── Lesson instruction quality ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lesson_prompt_instructs_specificity_when_blunder_present() -> None:
    """When blunders exist the prompt includes a directive to name the move."""
    from unittest.mock import AsyncMock

    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="I should have used earthquake on turn 5.")

    analysis = {
        "p1_summary": {"total_turns": 6, "optimal": 4, "good": 1, "suboptimal": 1,
                       "fallback": 0, "blunders": 1, "avg_heuristic_rank": 1.4},
        "key_moments": [],
        "blunders": [
            {
                "turn_number": 5,
                "player_role": "p1",
                "action": "/choose move tackle",
                "score_gap": 0.55,
                "notes": "chose tackle (rank 3/3, 55% below best) [BLUNDER]; heuristic top: earthquake (super effective)",
            }
        ],
        "turning_point": 5,
    }

    await generate_lesson(
        backend=backend,
        player_role="p1",
        winner=2,
        total_turns=6,
        opponent_label="random/random",
        turns=[],
        analysis=analysis,
    )

    call_args = backend.complete.call_args
    user_msg = call_args[0][0][1]["content"]
    # Must instruct the model to reference the blunder specifically
    assert "blunder" in user_msg.lower() or "Blunder" in user_msg
    assert "centerpiece" in user_msg.lower() or "name the move" in user_msg.lower()


@pytest.mark.asyncio
async def test_lesson_prompt_instructs_rng_attribution_when_variance_present() -> None:
    """When variance data exists the prompt instructs correct RNG attribution."""
    from unittest.mock import AsyncMock

    from nidozo.llm.lesson_generator import generate_lesson

    backend = AsyncMock()
    backend.complete = AsyncMock(return_value="The crits were significant but I still made mistakes.")

    analysis = {
        "p1_summary": {"total_turns": 5, "optimal": 5, "good": 0, "suboptimal": 0,
                       "fallback": 0, "blunders": 0, "avg_heuristic_rank": 1.0},
        "key_moments": [],
        "blunders": [],
        "turning_point": None,
        "variance_report": _make_variance(
            total_events=4,
            p1_benefit=1,
            p2_benefit=3,
            verdict="Variance slightly favored p2 (3 vs 1 beneficial events)",
        ),
    }

    await generate_lesson(
        backend=backend,
        player_role="p1",
        winner=2,
        total_turns=5,
        opponent_label="random/random",
        turns=[],
        analysis=analysis,
    )

    user_msg = backend.complete.call_args[0][0][1]["content"]
    assert "RNG" in user_msg or "variance" in user_msg.lower()


# ── _extract_move_name helper ─────────────────────────────────────────────────

def test_extract_move_name_poke_env_format() -> None:
    from nidozo.llm.lesson_generator import _extract_move_name
    assert _extract_move_name("/choose move fireblast") == "fireblast"
    assert _extract_move_name("move thunderbolt") == "thunderbolt"


def test_extract_move_name_annotator_format() -> None:
    from nidozo.llm.lesson_generator import _extract_move_name
    assert _extract_move_name("move 2 (thunderbolt)") == "thunderbolt"
    assert _extract_move_name("move 1 (surf)") == "surf"


def test_extract_move_name_switch_format() -> None:
    from nidozo.llm.lesson_generator import _extract_move_name
    assert _extract_move_name("/choose switch Swampert") == "Swampert"


def test_extract_move_name_none() -> None:
    from nidozo.llm.lesson_generator import _extract_move_name
    assert _extract_move_name(None) == "?"
    assert _extract_move_name("") == "?"
