"""ModelBackend protocol — the single interface all LLM providers must satisfy."""

from typing import Protocol, TypedDict


class Message(TypedDict):
    role: str   # "system" | "user" | "assistant"
    content: str


class ModelBackend(Protocol):
    """Complete a conversation and return the assistant's reply as a plain string."""

    async def complete(self, messages: list[Message]) -> str:
        ...
