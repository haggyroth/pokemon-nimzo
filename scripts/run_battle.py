"""
Run a single Gen 3 random-singles battle between two RandomBots.

Requires the local Showdown server to be running first:
    cd showdown && node pokemon-showdown start --no-security

Usage:
    uv run python scripts/run_battle.py
"""

import asyncio

from poke_env import LocalhostServerConfiguration
from poke_env.player import cross_evaluate

from pokemon_nimzo.battle.bots import RandomBot


async def main() -> None:
    bot1 = RandomBot(
        battle_format="gen3randombattle",
        server_configuration=LocalhostServerConfiguration,
        log_level=25,
    )
    bot2 = RandomBot(
        battle_format="gen3randombattle",
        server_configuration=LocalhostServerConfiguration,
        log_level=25,
    )

    await cross_evaluate([bot1, bot2], n_challenges=1)

    for player in (bot1, bot2):
        w = player.n_won_battles
        l = player.n_lost_battles
        t = player.n_tied_battles
        print(f"{player.username}: {w}W / {l}L / {t}T")


if __name__ == "__main__":
    asyncio.run(main())
