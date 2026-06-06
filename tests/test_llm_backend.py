"""Tests for the ModelBackend protocol and concrete backends."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nidozo.llm.backend import Message, ModelBackend


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


# ---------------------------------------------------------------------------
# AnthropicBackend
# ---------------------------------------------------------------------------

def _make_anthropic_backend(model: str = "claude-test"):
    """Create AnthropicBackend with a stubbed client so no real network calls occur."""
    from nidozo.llm.anthropic import AnthropicBackend

    with patch("anthropic.AsyncAnthropic.__init__", return_value=None):
        backend = AnthropicBackend(model=model, api_key="test-key")
    # Replace the real async client with a mock
    backend._client = MagicMock()
    return backend


def _anthropic_response(text: str):
    """Minimal Anthropic-like response object."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


@pytest.mark.asyncio
async def test_anthropic_backend_returns_text() -> None:
    """AnthropicBackend.complete returns the first content block's text."""
    backend = _make_anthropic_backend()
    backend._client.messages.create = AsyncMock(
        return_value=_anthropic_response("Use thunderbolt!")
    )

    msgs: list[Message] = [{"role": "user", "content": "Which move?"}]
    result = await backend.complete(msgs)

    assert result == "Use thunderbolt!"


@pytest.mark.asyncio
async def test_anthropic_backend_extracts_system_message() -> None:
    """System message is passed in the 'system' kwarg, not in the messages list."""
    backend = _make_anthropic_backend()
    backend._client.messages.create = AsyncMock(
        return_value=_anthropic_response("Switch!")
    )

    msgs: list[Message] = [
        {"role": "system", "content": "You are a trainer."},
        {"role": "user", "content": "Which move?"},
    ]
    await backend.complete(msgs)

    call_kwargs = backend._client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are a trainer."
    assert all(m["role"] != "system" for m in call_kwargs["messages"])


@pytest.mark.asyncio
async def test_anthropic_backend_no_system_message() -> None:
    """When there's no system message, 'system' kwarg is omitted entirely."""
    backend = _make_anthropic_backend()
    backend._client.messages.create = AsyncMock(
        return_value=_anthropic_response("ok")
    )

    msgs: list[Message] = [{"role": "user", "content": "Go!"}]
    await backend.complete(msgs)

    call_kwargs = backend._client.messages.create.call_args.kwargs
    assert "system" not in call_kwargs


@pytest.mark.asyncio
async def test_anthropic_backend_passes_model_and_max_tokens() -> None:
    """Model name and max_tokens are forwarded to the client."""
    from nidozo.llm.anthropic import AnthropicBackend

    with patch("anthropic.AsyncAnthropic.__init__", return_value=None):
        backend = AnthropicBackend(model="claude-sonnet-4-6", max_tokens=512, api_key="x")
    backend._client = MagicMock()
    backend._client.messages.create = AsyncMock(
        return_value=_anthropic_response("ok")
    )

    await backend.complete([{"role": "user", "content": "hi"}])

    call_kwargs = backend._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# OpenAIBackend
# ---------------------------------------------------------------------------

def _make_openai_backend(json_mode: bool = False):
    """Create OpenAIBackend with a stubbed client."""
    from nidozo.llm.openai import OpenAIBackend

    with patch("openai.AsyncOpenAI.__init__", return_value=None):
        backend = OpenAIBackend(model="gpt-test", api_key="test-key", json_mode=json_mode)
    backend._client = MagicMock()
    return backend


def _openai_response(content: str, reasoning_content: str | None = None):
    """Minimal OpenAI-like response object."""
    msg = MagicMock()
    msg.content = content
    msg.reasoning_content = reasoning_content
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_openai_backend_returns_content() -> None:
    """OpenAIBackend.complete returns message.content on success."""
    backend = _make_openai_backend()
    backend._client.chat.completions.create = AsyncMock(
        return_value=_openai_response('{"action_type":"move"}')
    )

    msgs: list[Message] = [{"role": "user", "content": "Move?"}]
    result = await backend.complete(msgs)

    assert result == '{"action_type":"move"}'


@pytest.mark.asyncio
async def test_openai_backend_no_response_format_without_json_mode() -> None:
    """response_format is NOT sent when json_mode=False."""
    backend = _make_openai_backend(json_mode=False)
    backend._client.chat.completions.create = AsyncMock(
        return_value=_openai_response("ok")
    )

    await backend.complete([{"role": "user", "content": "hi"}])

    call_kwargs = backend._client.chat.completions.create.call_args.kwargs
    assert "response_format" not in call_kwargs


@pytest.mark.asyncio
async def test_openai_backend_sends_response_format_with_json_mode() -> None:
    """response_format IS sent when json_mode=True."""
    backend = _make_openai_backend(json_mode=True)
    backend._client.chat.completions.create = AsyncMock(
        return_value=_openai_response('{"reasoning":"r","action_type":"move","identifier":"tb"}')
    )

    await backend.complete([{"role": "user", "content": "hi"}])

    call_kwargs = backend._client.chat.completions.create.call_args.kwargs
    assert "response_format" in call_kwargs
    assert call_kwargs["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_openai_backend_falls_back_to_reasoning_content() -> None:
    """When content is empty, reasoning_content is used as the response."""
    backend = _make_openai_backend()
    backend._client.chat.completions.create = AsyncMock(
        return_value=_openai_response("", reasoning_content='{"action_type":"move"}')
    )

    result = await backend.complete([{"role": "user", "content": "hi"}])

    assert result == '{"action_type":"move"}'


@pytest.mark.asyncio
async def test_openai_backend_returns_empty_string_when_no_content() -> None:
    """Both content and reasoning_content empty → return empty string."""
    backend = _make_openai_backend()
    backend._client.chat.completions.create = AsyncMock(
        return_value=_openai_response("", reasoning_content=None)
    )

    result = await backend.complete([{"role": "user", "content": "hi"}])

    assert result == ""
