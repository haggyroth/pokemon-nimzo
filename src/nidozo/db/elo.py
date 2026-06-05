"""ELO rating calculation — pure functions, no I/O."""

K_FACTOR = 32
DEFAULT_RATING = 1000.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability that player A wins against player B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def updated_ratings(
    rating_a: float,
    rating_b: float,
    winner: int | None,  # 1=A wins, 2=B wins, None=tie
    k: float = K_FACTOR,
) -> tuple[float, float]:
    """Return (new_rating_a, new_rating_b) after one game."""
    e_a = expected_score(rating_a, rating_b)
    e_b = 1.0 - e_a

    if winner == 1:
        s_a, s_b = 1.0, 0.0
    elif winner == 2:
        s_a, s_b = 0.0, 1.0
    else:
        s_a, s_b = 0.5, 0.5

    new_a = rating_a + k * (s_a - e_a)
    new_b = rating_b + k * (s_b - e_b)
    return new_a, new_b
