"""Tests for _spawn_background (issue #135).

Fire-and-forget post-battle tasks must be held by a strong reference until they
finish, or the event loop's weak reference lets the GC drop them mid-flight.
"""

from __future__ import annotations

import asyncio

import pytest

from nidozo.api import orchestration


@pytest.mark.asyncio
async def test_spawn_background_holds_reference_then_discards() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    result: list[str] = []

    async def work() -> None:
        started.set()
        await release.wait()
        result.append("done")

    task = orchestration._spawn_background(work())
    await started.wait()

    # While in flight, the task is held strongly in the module-level set.
    assert task in orchestration._background_tasks

    release.set()
    await task
    await asyncio.sleep(0)  # let the done-callback run

    # Completed task is discarded so the set doesn't grow unbounded.
    assert task not in orchestration._background_tasks
    assert result == ["done"]


@pytest.mark.asyncio
async def test_spawn_background_discards_even_on_exception() -> None:
    async def boom() -> None:
        raise ValueError("kaboom")

    task = orchestration._spawn_background(boom())
    with pytest.raises(ValueError):
        await task
    await asyncio.sleep(0)  # let the done-callback run

    assert task not in orchestration._background_tasks
