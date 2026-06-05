"""Tests for ELO calculation — pure math, no I/O."""

import pytest

from pokemon_nimzo.db.elo import expected_score, updated_ratings, DEFAULT_RATING, K_FACTOR


def test_equal_ratings_expect_half() -> None:
    assert expected_score(1000, 1000) == pytest.approx(0.5)


def test_higher_rating_expects_more() -> None:
    e = expected_score(1200, 1000)
    assert e > 0.5


def test_lower_rating_expects_less() -> None:
    e = expected_score(1000, 1200)
    assert e < 0.5


def test_expected_scores_sum_to_one() -> None:
    e_a = expected_score(1100, 950)
    e_b = expected_score(950, 1100)
    assert e_a + e_b == pytest.approx(1.0)


def test_winner_gains_rating() -> None:
    r1, r2 = updated_ratings(1000, 1000, winner=1)
    assert r1 > 1000
    assert r2 < 1000


def test_loser_loses_rating() -> None:
    r1, r2 = updated_ratings(1000, 1000, winner=2)
    assert r1 < 1000
    assert r2 > 1000


def test_tie_equal_ratings_unchanged() -> None:
    r1, r2 = updated_ratings(1000, 1000, winner=None)
    assert r1 == pytest.approx(1000.0)
    assert r2 == pytest.approx(1000.0)


def test_zero_sum_ratings() -> None:
    """Total ELO is conserved across a game."""
    for winner in (1, 2, None):
        r1, r2 = updated_ratings(1000, 1200, winner=winner)
        assert r1 + r2 == pytest.approx(2200.0)


def test_upset_win_gains_more() -> None:
    """Lower-rated player winning an upset should gain more ELO than a favourite winning."""
    low_wins_r, _ = updated_ratings(800, 1200, winner=1)
    high_wins_r, _ = updated_ratings(1200, 800, winner=1)
    assert (low_wins_r - 800) > (high_wins_r - 1200)


def test_k_factor_bounds_delta() -> None:
    """Delta is always strictly less than K (never earn or lose a full K in one game)."""
    for winner in (1, 2, None):
        r1, r2 = updated_ratings(1000, 1000, winner=winner)
        assert abs(r1 - 1000) < K_FACTOR
        assert abs(r2 - 1000) < K_FACTOR
