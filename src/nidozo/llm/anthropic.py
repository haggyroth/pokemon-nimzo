"""Anthropic (Claude) backend."""

from typing import Any

import anthropic

from nidozo.llm.backend import Message


class AnthropicBackend:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, messages: list[Message]) -> str:
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        turns = [m for m in messages if m["role"] != "system"]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": turns,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        # Iterate all content blocks and join text parts.  Assuming content[0]
        # crashes on multi-block responses and thinking-model output where the
        # first block is a "thinking" block with no .text attribute.
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
