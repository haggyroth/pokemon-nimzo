"""Anthropic (Claude) backend."""

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

        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": turns,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text
