"""Tests for the ModelBackend protocol and concrete backends."""

import pytest

from pokemon_nimzo.llm.backend import Message, ModelBackend


class _EchoBackend:
    """Trivial backend that echoes the last user message — satisfies the protocol."""

    async def complete(self, messages: list[Message]) -> str:
        user_msgs = [m for m in messages if m["role"] == "user"]
        return user_msgs[-1]["content"] if user_msgs else ""


def test_echo_backend_satisfies_protocol() -> None:
    backend: ModelBackend = _EchoBackend()
    assert backend is not None


@pytest.mark.asyncio
async def test_echo_backend_returns_last_user_message() -> None:
    backend = _EchoBackend()
    msgs: list[Message] = [
        {"role": "system", "content": "You are a Pokémon trainer."},
        {"role": "user", "content": "Which move should I use?"},
    ]
    result = await backend.complete(msgs)
    assert result == "Which move should I use?"


@pytest.mark.asyncio
async def test_echo_backend_empty_messages() -> None:
    backend = _EchoBackend()
    result = await backend.complete([])
    assert result == ""
