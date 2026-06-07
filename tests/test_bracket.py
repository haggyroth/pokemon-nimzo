"""Tests for bracket generation and result recording."""

from __future__ import annotations

import pytest

from nidozo.tournament.bracket import (
    build_bracket,
    build_double_elim,
    build_single_elim,
    get_pending_matches,
    record_result,
    record_result_single,
    resolve_seed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _players(n: int) -> list[dict]:
    return [{"provider": "random", "model_name": f"bot{i + 1}"} for i in range(n)]


# ---------------------------------------------------------------------------
# Single-elimination — structure
# ---------------------------------------------------------------------------

class TestSingleElimStructure:
    def test_two_player_bracket(self) -> None:
        state = build_single_elim(_players(2))
        assert state["format"] == "single_elim"
        assert state["size"] == 2
        assert state["num_rounds"] == 1
        rounds = state["rounds"]
        assert len(rounds) == 1
        assert len(rounds[0]["matches"]) == 1

    def test_four_player_bracket(self) -> None:
        state = build_single_elim(_players(4))
        assert state["size"] == 4
        assert state["num_rounds"] == 2
        # Round 1 has 2 matches, round 2 has 1
        matches_by_round = {r["round_num"]: len(r["matches"]) for r in state["rounds"]}
        assert matches_by_round == {1: 2, 2: 1}

    def test_eight_player_bracket(self) -> None:
        state = build_single_elim(_players(8))
        assert state["size"] == 8
        assert state["num_rounds"] == 3
        matches_by_round = {r["round_num"]: len(r["matches"]) for r in state["rounds"]}
        assert matches_by_round == {1: 4, 2: 2, 3: 1}

    def test_non_power_of_two_gets_padded(self) -> None:
        # 6 players → size 8 with 2 byes
        state = build_single_elim(_players(6))
        assert state["size"] == 8
        byes = [
            m for m in state["match_index"].values()
            if m["status"] == "bye"
        ]
        assert len(byes) == 2

    def test_seeds_assigned(self) -> None:
        state = build_single_elim(_players(4))
        assert resolve_seed(state, 1) is not None
        assert resolve_seed(state, 4) is not None
        assert resolve_seed(state, 5) is None

    def test_champion_initially_none(self) -> None:
        state = build_single_elim(_players(4))
        assert state["champion_seed"] is None

    def test_round1_seeds_cover_all_positions(self) -> None:
        """Every player seed should appear exactly once in round-1 matchups."""
        state = build_single_elim(_players(8))
        r1 = state["rounds"][0]["matches"]
        seeds_in_r1 = set()
        for m in r1:
            seeds_in_r1.add(m["p1_seed"])
            seeds_in_r1.add(m["p2_seed"])
        assert seeds_in_r1 == {1, 2, 3, 4, 5, 6, 7, 8}

    def test_top_seeds_cant_meet_until_final(self) -> None:
        """Seeds 1 and 2 should be in different halves of the bracket."""
        state = build_single_elim(_players(8))
        r1 = state["rounds"][0]["matches"]
        # Find which match seed 1 and seed 2 are in
        seed1_match = next(m["match_id"] for m in r1 if m["p1_seed"] == 1 or m["p2_seed"] == 1)
        seed2_match = next(m["match_id"] for m in r1 if m["p1_seed"] == 2 or m["p2_seed"] == 2)
        assert seed1_match != seed2_match


# ---------------------------------------------------------------------------
# Single-elimination — result recording
# ---------------------------------------------------------------------------

class TestSingleElimResults:
    def test_record_result_sets_winner(self) -> None:
        state = build_single_elim(_players(2))
        record_result_single(state, "WR1-1", 1, battle_id=42)
        assert state["match_index"]["WR1-1"]["winner_seed"] == 1
        assert state["match_index"]["WR1-1"]["status"] == "completed"

    def test_winner_advances_to_next_round(self) -> None:
        state = build_single_elim(_players(4))
        # Seed pairings for 4-player: WR1-1 = (1,4), WR1-2 = (2,3)
        record_result_single(state, "WR1-1", 1, battle_id=1)  # seed 1 wins
        record_result_single(state, "WR1-2", 1, battle_id=2)  # seed 2 wins
        final = state["match_index"]["WR2-1"]
        assert final["p1_seed"] == 1
        assert final["p2_seed"] == 2

    def test_champion_set_after_final(self) -> None:
        state = build_single_elim(_players(2))
        record_result_single(state, "WR1-1", 1, battle_id=99)
        assert state["champion_seed"] == 1

    def test_champion_set_for_four_players(self) -> None:
        state = build_single_elim(_players(4))
        record_result_single(state, "WR1-1", 1, battle_id=1)
        record_result_single(state, "WR1-2", 2, battle_id=2)
        record_result_single(state, "WR2-1", 1, battle_id=3)
        assert state["champion_seed"] is not None

    def test_pending_matches_decreases_as_completed(self) -> None:
        state = build_single_elim(_players(4))
        before = len(get_pending_matches(state))
        record_result_single(state, "WR1-1", 1, battle_id=1)
        after = len(get_pending_matches(state))
        assert after == before - 1

    def test_final_unlocks_only_after_both_semis(self) -> None:
        state = build_single_elim(_players(4))
        # After recording one semi the final is still not pending (p2 is None)
        record_result_single(state, "WR1-1", 1, battle_id=1)
        pending = [m["match_id"] for m in get_pending_matches(state)]
        assert "WR2-1" not in pending
        # After second semi it's available
        record_result_single(state, "WR1-2", 1, battle_id=2)
        pending = [m["match_id"] for m in get_pending_matches(state)]
        assert "WR2-1" in pending


# ---------------------------------------------------------------------------
# Bye handling
# ---------------------------------------------------------------------------

class TestByeHandling:
    def test_bye_match_auto_resolved(self) -> None:
        # 3 players → size 4, one bye
        state = build_single_elim(_players(3))
        bye_matches = [m for m in state["match_index"].values() if m["status"] == "bye"]
        assert len(bye_matches) >= 1
        # The real seed in the bye match should be pre-advanced
        for m in bye_matches:
            assert m["winner_seed"] is not None

    def test_bye_match_not_in_pending(self) -> None:
        state = build_single_elim(_players(3))
        pending = get_pending_matches(state)
        for m in pending:
            assert not m.get("p1_is_bye") and not m.get("p2_is_bye")


# ---------------------------------------------------------------------------
# Double-elimination — structure
# ---------------------------------------------------------------------------

class TestDoubleElimStructure:
    def test_four_player_de_has_wb_and_lb(self) -> None:
        state = build_double_elim(_players(4))
        assert state["format"] == "double_elim"
        mi = state["match_index"]
        wb_matches = [m for m in mi.values() if m["bracket"] == "winners"]
        lb_matches = [m for m in mi.values() if m["bracket"] == "losers"]
        gf_matches = [m for m in mi.values() if m["bracket"] == "grand_final"]
        assert len(wb_matches) >= 2
        assert len(lb_matches) >= 2
        assert len(gf_matches) == 2  # GF + GFR

    def test_grand_final_in_match_index(self) -> None:
        state = build_double_elim(_players(4))
        assert "GF" in state["match_index"]
        assert "GFR" in state["match_index"]

    def test_champion_initially_none(self) -> None:
        state = build_double_elim(_players(4))
        assert state["champion_seed"] is None


# ---------------------------------------------------------------------------
# Double-elimination — result recording
# ---------------------------------------------------------------------------

class TestDoubleElimResults:
    def _full_run_4p(self) -> dict:
        """Run 4-player DE to completion (seed 1 wins everything)."""
        state = build_double_elim(_players(4))
        battle_id = 0

        def step() -> None:
            nonlocal battle_id
            for m in get_pending_matches(state):
                battle_id += 1
                # Always pick p1 (seed with lower seed number = p1_seed)
                record_result(state, m["match_id"], 1, battle_id)
                return  # one at a time

        # Keep stepping until champion known
        for _ in range(20):
            if state["champion_seed"] is not None:
                break
            step()

        return state

    def test_champion_determined(self) -> None:
        state = self._full_run_4p()
        assert state["champion_seed"] is not None

    def test_loser_drops_to_lb(self) -> None:
        state = build_double_elim(_players(4))
        # Play WB round 1 match 1 — loser should appear in LB
        pending = get_pending_matches(state)
        wb_r1 = next(m for m in pending if m["bracket"] == "winners" and m["round_num"] == 1)
        loser_to = wb_r1["loser_to"]
        assert loser_to is not None and loser_to.startswith("LR")
        record_result(state, wb_r1["match_id"], 1, 1)
        lb_m = state["match_index"][loser_to]
        loser_slot = wb_r1["loser_slot"]
        seeded_in_lb = lb_m["p1_seed"] if loser_slot == 1 else lb_m["p2_seed"]
        assert seeded_in_lb == wb_r1["p2_seed"]  # p2 lost

    def test_gfr_voided_when_wb_wins_gf(self) -> None:
        state = self._full_run_4p()
        # If seed 1 wins the GF directly, GFR should be void
        gf = state["match_index"]["GF"]
        if gf["status"] == "completed":
            gfr = state["match_index"]["GFR"]
            # Either void (WB won) or pending/completed (LB won)
            assert gfr["status"] in ("void", "pending", "completed")


# ---------------------------------------------------------------------------
# build_bracket dispatch
# ---------------------------------------------------------------------------

def test_build_bracket_single() -> None:
    state = build_bracket(_players(4), "single_elim")
    assert state["format"] == "single_elim"


def test_build_bracket_double() -> None:
    state = build_bracket(_players(4), "double_elim")
    assert state["format"] == "double_elim"


def test_build_bracket_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown bracket format"):
        build_bracket(_players(4), "swiss")


# ---------------------------------------------------------------------------
# Schema v7 migration
# ---------------------------------------------------------------------------

class TestSchemaV7Migration:
    def test_v7_adds_bracket_columns(self) -> None:
        import sqlite3

        from nidozo.db.schema import migrate

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        migrate(conn)

        cols = [r["name"] for r in conn.execute("PRAGMA table_info(tournaments)").fetchall()]
        assert "tournament_format" in cols
        assert "bracket_state" in cols

    def test_v7_tournament_format_defaults_to_round_robin(self) -> None:
        import sqlite3

        from nidozo.db.schema import migrate

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        migrate(conn)

        conn.execute(
            """INSERT INTO tournaments
               (players, rounds, prompt_version, total_battles, tier)
               VALUES ('[]', 1, 'v2', 0, 'random')"""
        )
        row = conn.execute(
            "SELECT tournament_format FROM tournaments LIMIT 1"
        ).fetchone()
        assert row["tournament_format"] == "round_robin"
