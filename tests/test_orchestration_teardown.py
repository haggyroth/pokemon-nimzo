"""Tests for player teardown on battle end / cancel (issue #155).

poke-env runs each player's websocket listen loop as an independent task, so a
cancelled battle keeps playing on the Showdown server unless the players are
explicitly torn down. `_battle_and_teardown` must close both players in a
`finally` — on success, error, AND cancellation — and `_StreamingMixin.terminate`
must close the PS websocket.

Pure async unit tests; no Showdown server needed.
"""

from __future__ import annotations

import asyncio

import pytest

from nidozo.api.orchestration import _battle_and_teardown, _terminate_players
from nidozo.battle.streaming_player import _StreamingMixin


class _FakePlayer:
    """Stand-in for a streaming player with just the bits the helper touches."""

    def __init__(self, *, fail: BaseException | None = None, terminate_fail: bool = False) -> None:
        self.terminated = False
        self._fail = fail
        self._terminate_fail = terminate_fail

    async def battle_against(self, opponent: object, n_battles: int = 1) -> None:
        if self._fail is not None:
            raise self._fail

    async def terminate(self) -> None:
        if self._terminate_fail:
            raise RuntimeError("boom")
        self.terminated = True


# ---------------------------------------------------------------------------
# _battle_and_teardown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_teardown_on_normal_completion() -> None:
    p1, p2 = _FakePlayer(), _FakePlayer()
    await _battle_and_teardown(p1, p2)
    assert p1.terminated and p2.terminated


@pytest.mark.asyncio
async def test_teardown_on_cancellation() -> None:
    """A cancelled battle must still tear both players down (the #155 fix)."""
    p1 = _FakePlayer(fail=asyncio.CancelledError())
    p2 = _FakePlayer()
    with pytest.raises(asyncio.CancelledError):
        await _battle_and_teardown(p1, p2)
    assert p1.terminated and p2.terminated


@pytest.mark.asyncio
async def test_teardown_on_error() -> None:
    """A battle that errors out still tears down, and re-raises the error."""
    p1 = _FakePlayer(fail=ValueError("nope"))
    p2 = _FakePlayer()
    with pytest.raises(ValueError):
        await _battle_and_teardown(p1, p2)
    assert p1.terminated and p2.terminated


# ---------------------------------------------------------------------------
# _terminate_players
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminate_players_swallows_errors() -> None:
    """One player's teardown failure must not block the other's."""
    bad = _FakePlayer(terminate_fail=True)
    good = _FakePlayer()
    await _terminate_players(bad, good)  # must not raise
    assert good.terminated


@pytest.mark.asyncio
async def test_terminate_players_skips_none() -> None:
    """Players that were never constructed (None) are skipped, not crashed on."""
    good = _FakePlayer()
    await _terminate_players(None, good)
    assert good.terminated


# ---------------------------------------------------------------------------
# _StreamingMixin.terminate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixin_terminate_closes_websocket() -> None:
    """terminate() must close the PS websocket via stop_listening."""

    class _FakeClient:
        def __init__(self) -> None:
            self.stopped = False

        async def stop_listening(self) -> None:
            self.stopped = True

    class _Host(_StreamingMixin):
        pass

    host = _Host()
    host.ps_client = _FakeClient()  # type: ignore[assignment]
    await host.terminate()
    assert host.ps_client.stopped
