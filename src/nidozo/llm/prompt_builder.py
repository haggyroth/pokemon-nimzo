"""
PromptBuilder — loads versioned prompt templates and renders turn messages.

Templates live at src/nidozo/llm/prompts/<version>/:
  system.txt        — static system prompt (loaded once)
  turn.txt.jinja    — Jinja2 template rendered each turn with the battle state dict

Changing prompt content = bump the version directory (v1 → v2). The version
string is stored on the builder so it can be persisted with battle records and
correlated with ELO changes.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nidozo.llm.backend import Message

_PROMPTS_ROOT = Path(__file__).parent / "prompts"


class PromptBuilder:
    def __init__(self, version: str = "v1") -> None:
        self.version = version
        self._version_dir = _PROMPTS_ROOT / version

        if not self._version_dir.is_dir():
            raise ValueError(
                f"Prompt version '{version}' not found at {self._version_dir}"
            )

        self._system_text = (self._version_dir / "system.txt").read_text()

        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self._version_dir)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._turn_template = self._jinja_env.get_template("turn.txt.jinja")

    def build_system(self, lessons: list[str] | None = None) -> Message:
        """Return the system message, optionally appending the model's memory."""
        content = self._system_text
        if lessons:
            memory_lines = "\n".join(f"{i}. {lesson}" for i, lesson in enumerate(lessons, 1))
            content = (
                f"{content}\n\n"
                f"## Your Battle Memory\n"
                f"Based on your previous battles, you have learned:\n"
                f"{memory_lines}\n\n"
                f"Apply these lessons as you make decisions this battle."
            )
        return Message(role="system", content=content)

    def build_turn(self, battle_state: dict) -> Message:
        rendered = self._turn_template.render(**battle_state)
        return Message(role="user", content=rendered)

    def build_messages(
        self,
        battle_state: dict,
        lessons: list[str] | None = None,
    ) -> list[Message]:
        """Return [system, turn] ready to pass to a ModelBackend.

        Args:
            battle_state: Serialized battle dict from serialize_battle().
            lessons:      Optional list of prior-battle lesson strings to inject
                          into the system prompt as the model's "memory".
        """
        return [self.build_system(lessons=lessons), self.build_turn(battle_state)]
