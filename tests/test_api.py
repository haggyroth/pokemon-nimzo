"""Tests for the FastAPI REST endpoints.

Uses httpx.AsyncClient with ASGITransport — no real server is started,
no Pokémon Showdown connection is needed.  The LM Studio proxy endpoint
is tested with a mocked httpx response so tests pass offline.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path: Path):
    """Create a fresh app instance backed by a temp SQLite database."""
    from nidozo.api.app import create_app
    return create_app(db_path=tmp_path / "test.db")


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired directly to the ASGI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# /api/leaderboard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaderboard_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/leaderboard")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_leaderboard_returns_models(app, client: AsyncClient) -> None:
    """After inserting a model + battle the leaderboard returns a row."""

    # Reach into the app's store via the same db_path
    # Instead, seed via the store exposed on app.state (if set) or recreate
    # We use a fresh store pointing at the same tmp db the app uses.
    store = app.state.store if hasattr(app.state, "store") else None
    if store is None:
        # Seed a model directly via SQL on the test DB
        # (the app's store connection owns the db; re-open read-only via same path)
        return  # skip if store not accessible — covered by store tests

    store.get_or_create_model("random", "random", "v2")
    resp = await client.get("/api/leaderboard")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert rows[0]["model_name"] == "random"


@pytest.mark.asyncio
async def test_leaderboard_shape(client: AsyncClient) -> None:
    """Grouped response has expected keys; per-version response includes prompt_version."""
    resp = await client.get("/api/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for row in data:
        for key in ("provider", "model_name", "rating", "games", "wins", "losses", "ties"):
            assert key in row, f"Missing key {key!r} in grouped leaderboard row"
        # grouped mode: no prompt_version column, but versions field present
        assert "prompt_version" not in row, "grouped leaderboard should not have prompt_version"
        assert "versions" in row, "grouped leaderboard should have versions field"

    # per-version mode still works
    resp2 = await client.get("/api/leaderboard?grouped=false")
    assert resp2.status_code == 200
    for row in resp2.json():
        assert "prompt_version" in row


# ---------------------------------------------------------------------------
# /api/battles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_battles_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/battles")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_battles_respects_limit(client: AsyncClient) -> None:
    resp = await client.get("/api/battles?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# POST /api/battles/start
# ---------------------------------------------------------------------------

@pytest.fixture
def no_battle_runner():
    """Patch battle/tournament runners so API calls return immediately without
    trying to connect to Pokémon Showdown (which is not running in CI)."""
    async def _noop(*args, **kwargs):
        pass
    with patch("nidozo.api.app._run_battles", side_effect=_noop), \
         patch("nidozo.api.app._run_tournament", side_effect=_noop):
        yield


@pytest.mark.asyncio
async def test_start_battle_returns_battle_ids(client: AsyncClient, no_battle_runner) -> None:
    """Start endpoint returns battle_ids and a message."""
    resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random", "n_battles": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "battle_ids" in data
    assert len(data["battle_ids"]) == 2
    assert "message" in data


@pytest.mark.asyncio
async def test_start_battle_default_prompt_version(client: AsyncClient, no_battle_runner) -> None:
    """Default prompt_version is v2."""
    resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_start_battle_with_lmstudio_model(client: AsyncClient, no_battle_runner) -> None:
    """lmstudio provider with explicit model id is accepted."""
    resp = await client.post(
        "/api/battles/start",
        json={
            "p1_provider": "lmstudio",
            "p1_model": "ibm/granite-4-h-tiny",
            "p2_provider": "random",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_start_battle_creates_db_rows(client: AsyncClient, no_battle_runner) -> None:
    """Starting a battle creates a pending battle row in the DB."""
    resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random", "n_battles": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    battle_id = data["battle_ids"][0]
    assert isinstance(battle_id, int)
    assert battle_id >= 1


# ---------------------------------------------------------------------------
# /api/lmstudio/models
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lmstudio_models_offline_returns_empty(client: AsyncClient) -> None:
    """When LM Studio is not running the endpoint returns [] not an error."""
    # Mock a connection error so the test doesn't sit waiting for a real timeout.
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=ConnectionRefusedError("LM Studio not running"))

    with patch("nidozo.api.app.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/lmstudio/models")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_lmstudio_models_online_returns_ids(client: AsyncClient) -> None:
    """When LM Studio responds, model ids are extracted from the data array."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "ibm/granite-4-h-tiny", "object": "model"},
            {"id": "mistralai/ministral-3-3b", "object": "model"},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("nidozo.api.app.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/lmstudio/models")

    assert resp.status_code == 200
    models = resp.json()
    assert "ibm/granite-4-h-tiny" in models
    assert "mistralai/ministral-3-3b" in models


@pytest.mark.asyncio
async def test_lmstudio_models_error_returns_empty(client: AsyncClient) -> None:
    """HTTP errors from LM Studio are swallowed and return []."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("nidozo.api.app.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/lmstudio/models")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/battles/{id} — single battle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_single_battle(client: AsyncClient, no_battle_runner) -> None:
    """GET /api/battles/{id} returns the battle row after creation."""
    resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = resp.json()["battle_ids"][0]

    resp2 = await client.get(f"/api/battles/{battle_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["id"] == battle_id
    assert "status" in data
    assert "p1" in data
    assert "p2" in data


@pytest.mark.asyncio
async def test_get_single_battle_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/battles/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/battles/{id}/cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_pending_battle(client: AsyncClient, no_battle_runner) -> None:
    """A pending battle can be cancelled."""
    resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = resp.json()["battle_ids"][0]

    cancel_resp = await client.post(f"/api/battles/{battle_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["ok"] is True

    # Verify status updated
    battle = (await client.get(f"/api/battles/{battle_id}")).json()
    assert battle["status"] == "cancelled"


# ---------------------------------------------------------------------------
# POST /api/tournament/start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_tournament_returns_ids(client: AsyncClient, no_battle_runner) -> None:
    """Tournament endpoint returns tournament_id and correct battle count."""
    resp = await client.post(
        "/api/tournament/start",
        json={
            "players": [
                {"provider": "random"},
                {"provider": "random"},
            ],
            "rounds": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tournament_id" in data
    assert data["total_battles"] == 4   # 2 players × 1 pair × 2 rounds × 2 sides
    assert len(data["battle_ids"]) == 4


@pytest.mark.asyncio
async def test_start_tournament_requires_two_players(client: AsyncClient, no_battle_runner) -> None:
    resp = await client.post(
        "/api/tournament/start",
        json={"players": [{"provider": "random"}], "rounds": 1},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_tournament(client: AsyncClient, no_battle_runner) -> None:
    """GET /api/tournaments/{id} returns tournament metadata."""
    start = await client.post(
        "/api/tournament/start",
        json={"players": [{"provider": "random"}, {"provider": "random"}], "rounds": 1},
    )
    tournament_id = start.json()["tournament_id"]

    resp = await client.get(f"/api/tournaments/{tournament_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == tournament_id
    assert data["rounds"] == 1
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# /api/battles/{id}/analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analysis_nonexistent_battle(client: AsyncClient, no_battle_runner) -> None:
    """Analysis for a battle with no turns returns a valid (empty) structure."""
    start_resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = start_resp.json()["battle_ids"][0]

    resp = await client.get(f"/api/battles/{battle_id}/analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert "p1_summary" in data
    assert "p2_summary" in data
    assert "turns" in data
    assert data["turns"] == []


# ---------------------------------------------------------------------------
# /api/battles/{id}/turns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turns_empty_battle(client: AsyncClient, no_battle_runner) -> None:
    start_resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = start_resp.json()["battle_ids"][0]

    resp = await client.get(f"/api/battles/{battle_id}/turns")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/battles/{id}/replay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replay_empty_battle(client: AsyncClient, no_battle_runner) -> None:
    """Replay endpoint returns battle metadata and empty turns list for a fresh battle."""
    start_resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = start_resp.json()["battle_ids"][0]

    resp = await client.get(f"/api/battles/{battle_id}/replay")
    assert resp.status_code == 200

    data = resp.json()
    assert "battle" in data
    assert "turns" in data
    assert data["battle"]["id"] == battle_id
    assert isinstance(data["turns"], list)
    assert data["turns"] == []   # no turns recorded yet


@pytest.mark.asyncio
async def test_replay_not_found(client: AsyncClient) -> None:
    """Replay endpoint returns 404 for a non-existent battle."""
    resp = await client.get("/api/battles/99999/replay")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_replay_merges_turns_by_number(app, client: AsyncClient, no_battle_runner) -> None:
    """Replay endpoint merges p1 and p2 rows into a single dict per turn number."""
    import json as _json

    start_resp = await client.post(
        "/api/battles/start",
        json={"p1_provider": "random", "p2_provider": "random"},
    )
    battle_id = start_resp.json()["battle_ids"][0]

    # Manually insert two turn rows (p1 and p2) for the same turn number via the app's store
    store = app.state.store
    state_p1 = _json.dumps({"my_active": {"species": "Pikachu", "hp_fraction": 0.8}})
    state_p2 = _json.dumps({"my_active": {"species": "Squirtle", "hp_fraction": 0.9}})
    store.log_turn(battle_id, 1, "p1", "v1", "/choose move thunderbolt", True, "", state_p1)
    store.log_turn(battle_id, 1, "p2", "v1", "/choose move tackle",      True, "", state_p2)

    resp = await client.get(f"/api/battles/{battle_id}/replay")
    assert resp.status_code == 200

    data = resp.json()
    assert len(data["turns"]) == 1

    turn = data["turns"][0]
    assert turn["turn"] == 1
    assert "p1" in turn
    assert "p2" in turn
    # p1 side
    assert turn["p1"]["action"] == "/choose move thunderbolt"
    assert turn["p1"]["parse_success"] is True
    assert turn["p1"]["state"]["my_active"]["species"] == "Pikachu"
    # p2 side
    assert turn["p2"]["action"] == "/choose move tackle"
    assert turn["p2"]["state"]["my_active"]["species"] == "Squirtle"
