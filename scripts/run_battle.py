"""
Run a Gen 3 random-singles battle between two players.

Requires the local Showdown server to be running first:
    ./scripts/start_showdown.sh

Usage:
    # Two random bots (default)
    uv run python scripts/run_battle.py

    # LLM (Anthropic) vs random bot
    uv run python scripts/run_battle.py --p1 anthropic --model claude-sonnet-4-6

    # LLM vs LLM
    uv run python scripts/run_battle.py --p1 anthropic --p2 anthropic

Environment variables:
    ANTHROPIC_API_KEY   — required when --p1 or --p2 is "anthropic"
    OPENAI_API_KEY      — required when --p1 or --p2 is "openai"
    LM_STUDIO_BASE_URL  — base URL for LM Studio (default: http://localhost:1234/v1)
    LM_STUDIO_MODEL     — model name for LM Studio (default: local-model)
"""

import argparse
import asyncio
import logging
import os

from poke_env import LocalhostServerConfiguration
from poke_env.player import Player

from pokemon_nimzo.battle.bots import RandomBot
from pokemon_nimzo.battle.llm_player import LLMPlayer
from pokemon_nimzo.llm import AnthropicBackend, OpenAIBackend

logging.basicConfig(level=logging.WARNING)

_FORMAT = "gen3randombattle"


def _build_player(provider: str, model: str | None, label: str) -> Player:
    cfg = LocalhostServerConfiguration

    if provider == "random":
        return RandomBot(battle_format=_FORMAT, server_configuration=cfg)

    if provider == "anthropic":
        backend = AnthropicBackend(
            model=model or "claude-sonnet-4-6",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        return LLMPlayer(backend=backend, battle_format=_FORMAT, server_configuration=cfg)

    if provider == "openai":
        backend = OpenAIBackend(
            model=model or "gpt-4o",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
        return LLMPlayer(backend=backend, battle_format=_FORMAT, server_configuration=cfg)

    if provider == "lmstudio":
        backend = OpenAIBackend(
            model=model or os.environ.get("LM_STUDIO_MODEL", "local-model"),
            base_url=os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
            api_key="lm-studio",
        )
        return LLMPlayer(backend=backend, battle_format=_FORMAT, server_configuration=cfg)

    raise ValueError(f"Unknown provider '{provider}'. Use: random, anthropic, openai, lmstudio")


async def main(p1_provider: str, p2_provider: str, model: str | None) -> None:
    p1 = _build_player(p1_provider, model, "p1")
    p2 = _build_player(p2_provider, model, "p2")

    print(f"Starting battle: {p1.username} ({p1_provider}) vs {p2.username} ({p2_provider})")

    await p1.battle_against(p2, n_battles=1)

    for player, provider in ((p1, p1_provider), (p2, p2_provider)):
        w, l, t = player.n_won_battles, player.n_lost_battles, player.n_tied_battles
        print(f"  {player.username} [{provider}]: {w}W / {l}L / {t}T")

    if p1.n_finished_battles == 0:
        print("WARNING: no battles finished — is the Showdown server running?")
    else:
        winner = p1 if p1.n_won_battles > 0 else p2
        print(f"\nWinner: {winner.username} [{p1_provider if winner is p1 else p2_provider}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Pokémon battle")
    parser.add_argument("--p1", default="random", help="Player 1 provider (random/anthropic/openai/lmstudio)")
    parser.add_argument("--p2", default="random", help="Player 2 provider (random/anthropic/openai/lmstudio)")
    parser.add_argument("--model", default=None, help="Model name override for LLM players")
    args = parser.parse_args()

    asyncio.run(main(args.p1, args.p2, args.model))
