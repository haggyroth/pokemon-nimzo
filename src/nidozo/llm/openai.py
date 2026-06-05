"""OpenAI-compatible backend — covers OpenAI cloud and local LM Studio."""

import openai

from nidozo.llm.backend import Message


class OpenAIBackend:
    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        # base_url=None → OpenAI cloud; set to "http://localhost:1234/v1" for LM Studio
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, messages: list[Message]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.choices[0].message.content or ""
