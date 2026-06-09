"""OpenAI-compatible backend — covers OpenAI cloud and local LM Studio."""

import logging
from typing import Any

import openai

from nidozo.llm.backend import Message

logger = logging.getLogger(__name__)

# JSON Schema for the v2 structured action output.
# LM Studio (and OpenAI) grammar-sample against this to guarantee valid JSON
# that exactly matches our expected shape.
_ACTION_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "battle_action",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "2-4 sentence analysis: type matchups, speed, HP, status.",
                },
                "action_type": {
                    "type": "string",
                    "enum": ["move", "switch"],
                },
                "identifier": {
                    "type": "string",
                    "description": (
                        "Move name, Pokémon species name, or 1-based slot number "
                        "(e.g. 'thunderbolt', 'masquerain', '2')."
                    ),
                },
            },
            "required": ["reasoning", "action_type", "identifier"],
            "additionalProperties": False,
        },
    },
}


class OpenAIBackend:
    """OpenAI-compatible chat backend.

    Args:
        model: Model identifier string.
        max_tokens: Maximum tokens to generate.
        api_key: API key (use any non-empty string for LM Studio, e.g. "lm-studio").
        base_url: Override base URL — set to "http://localhost:1234/v1" for LM Studio.
        json_mode: If True, send response_format to grammar-sample JSON output.
                   Supported by LM Studio ≥0.3.6 and OpenAI.
                   Do NOT use with Anthropic backends.
        use_json_object: When json_mode=True, use the simple {"type":"json_object"}
                         format instead of the full json_schema.  Set this for LM
                         Studio — local models often struggle with strict: true, but
                         reliably honour json_object grammar sampling.  OpenAI cloud
                         benefits from the richer json_schema (type enforcement +
                         additionalProperties: false) so use the full schema there.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 1536,
        api_key: str | None = None,
        base_url: str | None = None,
        json_mode: bool = False,
        use_json_object: bool = False,
    ) -> None:
        # base_url=None → OpenAI cloud; set to "http://localhost:1234/v1" for LM Studio
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._use_json_object = use_json_object

    async def complete(self, messages: list[Message]) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._json_mode:
            if self._use_json_object:
                # Simple JSON grammar sampling — all LM Studio models honour this.
                kwargs["response_format"] = {"type": "json_object"}
            else:
                # Full structured-output schema — enforces exact shape on OpenAI cloud.
                kwargs["response_format"] = _ACTION_JSON_SCHEMA

        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        content = msg.content or ""

        if not content:
            # Qwen 3 (and other thinking models) route all output through
            # reasoning_content, leaving content empty.  When using json_mode
            # the actual JSON lands in reasoning_content — use it as the response.
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                logger.debug(
                    "content empty for %s — using reasoning_content (%d chars)",
                    self._model, len(reasoning),
                )
                content = reasoning

        if not content:
            finish = getattr(response.choices[0], "finish_reason", "unknown")
            logger.warning(
                "Empty response from %s (finish_reason=%s). "
                "Check that the model is loaded and the model ID is correct.",
                self._model,
                finish,
            )

        return content
