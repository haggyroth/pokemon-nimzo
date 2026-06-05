"""Battle bot implementations. RandomBot is the baseline; LLM bots come later."""

from poke_env.player import RandomPlayer


class RandomBot(RandomPlayer):
    """Picks a move uniformly at random from all legal options each turn."""
    pass
