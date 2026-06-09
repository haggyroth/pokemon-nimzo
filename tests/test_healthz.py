"""Tests for GET /healthz — liveness/readiness probe."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(tmp_path):
    from nidozo.api.app import create_app
    return create_app(db_path=tmp_path / "test.db")


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Healthy — both DB and Showdown reachable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthz_ok_when_all_up(client) -> None:
    """Returns 200 with status=ok when DB is fine and Showdown is reachable."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)

    with patch("nidozo.api.routes.socket.create_connection", return_value=mock_sock):
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["showdown"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# Degraded — Showdown unreachable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthz_degraded_when_showdown_down(client) -> None:
    """Returns 503 with status=degraded when Showdown is not running."""
    with patch(
        "nidozo.api.routes.socket.create_connection",
        side_effect=OSError("Connection refused"),
    ):
        resp = await client.get("/healthz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "ok"          # DB is still fine
    assert body["showdown"] == "unreachable"


# ---------------------------------------------------------------------------
# Degraded — DB unreachable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthz_degraded_when_db_down(client, app) -> None:
    """Returns 503 with status=degraded when the DB connection fails."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)

    # Mark the store as closed so every thread sees the failure.
    # With thread-local connections, closing _conn on the test thread only
    # affects that thread; setting _closed=True gates all threads uniformly.
    app.state.store._closed = True

    with patch("nidozo.api.routes.socket.create_connection", return_value=mock_sock):
        resp = await client.get("/healthz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "unreachable"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthz_version_field_present(client) -> None:
    """Response always includes a version string."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)

    with patch("nidozo.api.routes.socket.create_connection", return_value=mock_sock):
        resp = await client.get("/healthz")

    from nidozo import __version__
    assert resp.json()["version"] == __version__


# ---------------------------------------------------------------------------
# configure_logging — smoke tests
# ---------------------------------------------------------------------------

def test_configure_logging_runs_without_error() -> None:
    """configure_logging() completes without raising."""

    # Reset the _CONFIGURED guard so we can call it in tests
    import nidozo.api.logging_config as lc
    from nidozo.api.logging_config import configure_logging
    lc._CONFIGURED = False
    configure_logging(level="WARNING")
    lc._CONFIGURED = False  # reset again so other tests aren't affected


def test_json_formatter_produces_valid_json() -> None:
    """_JsonFormatter emits a parseable JSON string with expected keys."""
    import json
    import logging

    from nidozo.api.logging_config import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "ts" in parsed


def test_json_formatter_includes_exc_info() -> None:
    """Exception info is serialised into the 'exc' field."""
    import json
    import logging

    from nidozo.api.logging_config import _JsonFormatter

    formatter = _JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="error occurred",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert "exc" in parsed
    assert "ValueError" in parsed["exc"]
    assert "boom" in parsed["exc"]


def test_json_formatter_includes_stack_info() -> None:
    """Stack info is serialised into the 'stack' field when present."""
    import json
    import logging

    from nidozo.api.logging_config import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="with stack",
        args=(),
        exc_info=None,
    )
    record.stack_info = "Stack trace here"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "stack" in parsed
    assert "Stack trace here" in parsed["stack"]


def test_configure_logging_second_call_is_noop() -> None:
    """configure_logging() is idempotent — second call does nothing."""
    import nidozo.api.logging_config as lc

    # Reset state so we can test the first-call path
    original = lc._CONFIGURED
    lc._CONFIGURED = False
    try:
        from nidozo.api.logging_config import configure_logging
        configure_logging(level="DEBUG")
        assert lc._CONFIGURED is True
        # Second call should be a no-op (no error)
        configure_logging(level="DEBUG")
        assert lc._CONFIGURED is True
    finally:
        lc._CONFIGURED = original
