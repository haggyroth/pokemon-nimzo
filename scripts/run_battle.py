"""
Run a single Gen 3 random-singles battle between two RandomBots.

Requires the local Showdown server to be running first:
    ./scripts/start_showdown.sh

Usage:
    uv run python scripts/run_battle.py
"""

import asyncio
import logging

from poke_env import LocalhostServerConfiguration
from poke_env.player import cross_evaluate

from pokemon_nimzo.battle.bots import RandomBot

logging.basicConfig(level=logging.WARNING)


async def main() -> None:
    bot1 = RandomBot(
        battle_format="gen3randombattle",
        server_configuration=LocalhostServerConfiguration,
    )
    bot2 = RandomBot(
        battle_format="gen3randombattle",
        server_configuration=LocalhostServerConfiguration,
    )

    print(f"Starting battle: {bot1.username} vs {bot2.username}")

    # battle_against directly — avoids the reset_battles() call inside cross_evaluate
    await bot1.battle_against(bot2, n_battles=1)

    for bot in (bot1, bot2):
        w = bot.n_won_battles
        l = bot.n_lost_battles
        t = bot.n_tied_battles
        total = bot.n_finished_battles
        print(f"  {bot.username}: {w}W / {l}L / {t}T  (finished: {total})")

    if bot1.n_finished_battles == 0:
        print("WARNING: no battles finished — check that Showdown is running")
    else:
        winner = bot1.username if bot1.n_won_battles > 0 else bot2.username
        print(f"\nWinner: {winner}")


if __name__ == "__main__":
    asyncio.run(main())
