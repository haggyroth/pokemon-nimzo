"""Tests for tiers.py and team_builder.py."""

from __future__ import annotations

import pytest

from nidozo.battle.team_builder import (
    all_species,
    build_pokemon_block,
    build_team_string,
    get_pool_info,
    load_movesets,
)
from nidozo.battle.tiers import TIER_DISPLAY, TIER_TO_FORMAT, get_pool, is_valid_tier

# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------

class TestGetPool:
    def test_ou_pool_is_nonempty(self) -> None:
        ms = load_movesets()
        pool = get_pool("ou", set(ms.keys()))
        assert len(pool) > 0

    def test_ou_pool_contains_salamence(self) -> None:
        ms = load_movesets()
        pool = get_pool("ou", set(ms.keys()))
        assert "salamence" in pool

    def test_freeforall_returns_all_species(self) -> None:
        ms = load_movesets()
        all_s = set(ms.keys())
        pool = get_pool("freeforall", all_s)
        assert set(pool) == all_s

    def test_uu_excludes_ou_pokemon(self) -> None:
        ms = load_movesets()
        uu_pool = get_pool("uu", set(ms.keys()))
        ou_pool = get_pool("ou", set(ms.keys()))
        assert not (set(uu_pool) & set(ou_pool)), "UU and OU pools should not overlap"

    def test_pool_is_sorted(self) -> None:
        ms = load_movesets()
        pool = get_pool("ou", set(ms.keys()))
        assert pool == sorted(pool)

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            get_pool("superubers", {"salamence"})

    def test_lc_pool_contains_lc_pokemon(self) -> None:
        ms = load_movesets()
        pool = get_pool("lc", set(ms.keys()))
        assert "elekid" in pool

    def test_pool_only_includes_species_in_movesets(self) -> None:
        """Pool never returns a species that lacks a moveset definition."""
        pool = get_pool("ou", {"salamence", "nonexistent_mon"})
        assert "nonexistent_mon" not in pool
        assert "salamence" in pool


class TestIsValidTier:
    def test_known_tiers_are_valid(self) -> None:
        for tier in ("ubers", "ou", "uu", "nu", "lc", "freeforall", "random"):
            assert is_valid_tier(tier), f"Expected {tier!r} to be valid"

    def test_unknown_tier_is_invalid(self) -> None:
        assert not is_valid_tier("bl2")
        assert not is_valid_tier("")
        assert not is_valid_tier("gen3ou")


class TestTierConstants:
    def test_all_tiers_have_display_names(self) -> None:
        for tier in ("ubers", "ou", "uu", "nu", "lc", "freeforall", "random"):
            assert tier in TIER_DISPLAY

    def test_all_tiers_have_format_mapping(self) -> None:
        for tier in ("ubers", "ou", "uu", "nu", "lc", "freeforall"):
            assert tier in TIER_TO_FORMAT
            fmt = TIER_TO_FORMAT[tier]
            assert fmt.startswith("gen3"), f"Expected gen3 format for {tier!r}, got {fmt!r}"


# ---------------------------------------------------------------------------
# team_builder helpers
# ---------------------------------------------------------------------------

class TestLoadMovesets:
    def test_returns_dict(self) -> None:
        ms = load_movesets()
        assert isinstance(ms, dict)
        assert len(ms) > 50

    def test_no_comment_key(self) -> None:
        ms = load_movesets()
        assert "__comment" not in ms

    def test_each_entry_has_required_fields(self) -> None:
        ms = load_movesets()
        required = {"species", "item", "ability", "nature", "moves"}
        for sid, entry in ms.items():
            missing = required - entry.keys()
            assert not missing, f"{sid!r} missing fields: {missing}"

    def test_each_entry_has_four_moves(self) -> None:
        ms = load_movesets()
        for sid, entry in ms.items():
            assert len(entry["moves"]) == 4, f"{sid!r} has {len(entry['moves'])} moves"

    def test_ev_totals_do_not_exceed_510(self) -> None:
        ms = load_movesets()
        for sid, entry in ms.items():
            total = sum(entry.get("evs", {}).values())
            assert total <= 510, f"{sid!r} EV total {total} exceeds 510"

    def test_caching_returns_same_object(self) -> None:
        ms1 = load_movesets()
        ms2 = load_movesets()
        assert ms1 is ms2


class TestAllSpecies:
    def test_returns_set_of_strings(self) -> None:
        s = all_species()
        assert isinstance(s, set)
        assert all(isinstance(x, str) for x in s)

    def test_contains_expected_pokemon(self) -> None:
        s = all_species()
        for mon in ("salamence", "tyranitar", "gengar", "blissey"):
            assert mon in s


class TestBuildPokemonBlock:
    def test_basic_block_structure(self) -> None:
        ms = load_movesets()
        block = build_pokemon_block("salamence", ms["salamence"])
        assert "Salamence @ Choice Band" in block
        assert "Ability: Intimidate" in block
        assert "Adamant Nature" in block
        assert "- Dragon Claw" in block

    def test_ev_line_format(self) -> None:
        ms = load_movesets()
        block = build_pokemon_block("salamence", ms["salamence"])
        assert "EVs:" in block

    def test_level_100_not_shown(self) -> None:
        """Level 100 is default and should NOT appear in the block."""
        ms = load_movesets()
        block = build_pokemon_block("salamence", ms["salamence"])
        assert "Level: 100" not in block

    def test_lc_level_5_is_shown(self) -> None:
        ms = load_movesets()
        block = build_pokemon_block("elekid", ms["elekid"])
        assert "Level: 5" in block

    def test_four_moves_rendered(self) -> None:
        ms = load_movesets()
        for sid in ("tyranitar", "gengar", "blissey"):
            block = build_pokemon_block(sid, ms[sid])
            move_lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
            assert len(move_lines) == 4, f"{sid!r} block has {len(move_lines)} move lines"


class TestBuildTeamString:
    def test_six_pokemon_produces_five_separators(self) -> None:
        team = ["salamence", "tyranitar", "gengar", "swampert", "skarmory", "blissey"]
        result = build_team_string(team)
        # Pokémon blocks are separated by double newlines
        assert result.count("\n\n") == 5

    def test_unknown_species_raises(self) -> None:
        with pytest.raises(KeyError, match="nonexistent_mon"):
            build_team_string(["nonexistent_mon"])

    def test_team_string_contains_all_species(self) -> None:
        team = ["salamence", "blissey", "skarmory"]
        result = build_team_string(team)
        assert "Salamence" in result
        assert "Blissey" in result
        assert "Skarmory" in result


class TestGetPoolInfo:
    def test_returns_list_of_dicts(self) -> None:
        info = get_pool_info(["salamence", "tyranitar"])
        assert len(info) == 2
        assert info[0]["species_id"] == "salamence"
        assert info[0]["species"] == "Salamence"
        assert isinstance(info[0]["types"], list)

    def test_unknown_species_returns_fallback(self) -> None:
        info = get_pool_info(["unknownmon"])
        assert info[0]["species_id"] == "unknownmon"
        assert info[0]["types"] == []


# ---------------------------------------------------------------------------
# Store: teams & draft sessions
# ---------------------------------------------------------------------------

class TestStoreTeams:
    def test_save_and_retrieve_team(self, tmp_path: pytest.TempPathFactory) -> None:
        from nidozo.db.store import BattleStore

        store = BattleStore(tmp_path / "test.db")
        model_id = store.get_or_create_model("lmstudio", "test-model", "v3")

        team_id = store.save_team(
            model_id=model_id,
            tier="ou",
            format_="gen3ou",
            pokemon=["salamence", "tyranitar", "gengar"],
            team_string="Salamence @ ...",
        )
        assert isinstance(team_id, int)
        assert team_id > 0

        teams = store.get_teams_for_model(model_id)
        assert len(teams) == 1
        assert teams[0]["tier"] == "ou"
        assert teams[0]["pokemon"] == ["salamence", "tyranitar", "gengar"]

    def test_save_draft_session(self, tmp_path: pytest.TempPathFactory) -> None:
        from nidozo.db.store import BattleStore

        store = BattleStore(tmp_path / "test.db")
        model_id = store.get_or_create_model("lmstudio", "test-model", "v3")

        session_id = store.save_draft_session(
            model_id=model_id,
            tier="ou",
            pool_size=38,
            picked=["salamence", "tyranitar", "gengar", "swampert", "skarmory", "blissey"],
            prompt_version="v3",
            reasoning="Pick 1 (Salamence): Fast attacker.",
        )
        assert isinstance(session_id, int)

    def test_set_and_get_battle_teams(self, tmp_path: pytest.TempPathFactory) -> None:
        from nidozo.db.store import BattleStore

        store = BattleStore(tmp_path / "test.db")
        p1_id = store.get_or_create_model("lmstudio", "m1", "v3")
        p2_id = store.get_or_create_model("lmstudio", "m2", "v3")

        bid = store.create_battle("tag-abc", "gen3ou", p1_id, p2_id)

        t1 = store.save_team(p1_id, "ou", "gen3ou", ["salamence"], "Salamence @ ...")
        t2 = store.save_team(p2_id, "ou", "gen3ou", ["tyranitar"], "Tyranitar @ ...")

        store.set_battle_teams(bid, t1, t2, "ou")

        p1_team, p2_team = store.get_battle_teams(bid)
        assert p1_team is not None
        assert p1_team["pokemon"] == ["salamence"]
        assert p2_team is not None
        assert p2_team["pokemon"] == ["tyranitar"]

    def test_get_battle_teams_for_random_battle(self, tmp_path: pytest.TempPathFactory) -> None:
        from nidozo.db.store import BattleStore

        store = BattleStore(tmp_path / "test.db")
        p1_id = store.get_or_create_model("random", "random", "v2")
        p2_id = store.get_or_create_model("random", "random", "v2")

        bid = store.create_battle("tag-xyz", "gen3randombattle", p1_id, p2_id)
        p1_team, p2_team = store.get_battle_teams(bid)
        assert p1_team is None
        assert p2_team is None
