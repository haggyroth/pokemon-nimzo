"""Gen 3 Smogon tier definitions and pool helpers.

Species keys use Showdown internal IDs (lowercase, no spaces/special characters).
Tier hierarchy: ubers > ou > uu > nu > lc.  Higher-tier Pokémon may be used in
lower-tier pools if the tournament host specifically allows it, but by default
each tier pool is restricted to Pokémon that belong to that exact tier.

``freeforall`` is a sentinel meaning no tier restriction — the pool is all
Pokémon in the moveset data that have a defined set.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Tier sets — Showdown species IDs
# ---------------------------------------------------------------------------

UBERS: Final[frozenset[str]] = frozenset({
    "groudon",
    "kyogre",
    "rayquaza",
    "mewtwo",
    "lugia",
    "hooh",
    "latias",
    "latios",
    "wobbuffet",
    "jirachi",
})

OU: Final[frozenset[str]] = frozenset({
    "salamence",
    "tyranitar",
    "metagross",
    "gengar",
    "alakazam",
    "blissey",
    "skarmory",
    "swampert",
    "snorlax",
    "zapdos",
    "starmie",
    "dugtrio",
    "jolteon",
    "gyarados",
    "celebi",
    "suicune",
    "forretress",
    "heracross",
    "claydol",
    "breloom",
    "milotic",
    "umbreon",
    "weezing",
    "vaporeon",
    "regice",
    "flygon",
    "machamp",
    "magneton",
    "sceptile",
    "aerodactyl",
    "gardevoir",
    "tauros",
    "tentacruel",
    "jynx",
    "kangaskhan",
    "slaking",
    "moltres",
    "articuno",
    "rhydon",
})

UU: Final[frozenset[str]] = frozenset({
    "arcanine",
    "espeon",
    "slowbro",
    "porygon2",
    "hitmontop",
    "nidoking",
    "nidoqueen",
    "quagsire",
    "omastar",
    "sandslash",
    "hitmonlee",
    "ludicolo",
    "manectric",
    "haunter",
    "donphan",
    "hypno",
    "victreebel",
    "mantine",
    "electrode",
    "granbull",
    "poliwrath",
    "misdreavus",
    "ursaring",
    "scizor",
    "ampharos",
})

NU: Final[frozenset[str]] = frozenset({
    "absol",
    "crawdaunt",
    "lanturn",
    "chimecho",
    "linoone",
    "furret",
    "glalie",
    "wigglytuff",
    "raticate",
})

LC: Final[frozenset[str]] = frozenset({
    "elekid",
    "magby",
    "dratini",
    "trapinch",
    "machop",
    "gastly",
    "larvitar",
    "abra",
    "snorunt",
    "carvanha",
})

# Ordered from most to least restrictive (ascending leniency)
TIER_HIERARCHY: Final[list[str]] = ["lc", "nu", "uu", "ou", "ubers"]

# ---------------------------------------------------------------------------
# Format mapping — Nidozo tier → Pokémon Showdown format string
# ---------------------------------------------------------------------------

TIER_TO_FORMAT: Final[dict[str, str]] = {
    "ubers":      "gen3ubers",
    "ou":         "gen3ou",
    "uu":         "gen3ou",     # Showdown doesn't have gen3uu; use gen3ou with our pool
    "nu":         "gen3ou",     # same
    "lc":         "gen3lc",
    "freeforall": "gen3ubers",  # most permissive; our pool is all sets in JSON
}

# Display names shown in the frontend
TIER_DISPLAY: Final[dict[str, str]] = {
    "ubers":      "Ubers",
    "ou":         "OverUsed (OU)",
    "uu":         "UnderUsed (UU)",
    "nu":         "NeverUsed (NU)",
    "lc":         "Little Cup (LC)",
    "freeforall": "Free-for-All",
    "random":     "Random Battle",
}

# Map tier ID → frozenset (None means "no restriction")
_TIER_POOLS: dict[str, frozenset[str] | None] = {
    "ubers":      UBERS,
    "ou":         OU,
    "uu":         UU,
    "nu":         NU,
    "lc":         LC,
    "freeforall": None,
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_pool(tier: str, all_species: set[str]) -> list[str]:
    """Return the sorted list of legal species for *tier*.

    Args:
        tier:        One of the tier keys or "freeforall".
        all_species: All species IDs available in the moveset data.

    Returns:
        Sorted list of species IDs that are legal for the tier.

    Raises:
        ValueError: If *tier* is not a known tier key.
    """
    if tier not in _TIER_POOLS:
        raise ValueError(
            f"Unknown tier: {tier!r}. Valid tiers: {sorted(_TIER_POOLS)}"
        )
    allowed = _TIER_POOLS[tier]
    if allowed is None:
        # freeforall — everything that has a moveset defined
        return sorted(all_species)
    return sorted(allowed & all_species)


def is_valid_tier(tier: str) -> bool:
    """Return True if *tier* is a known tier key (including 'random')."""
    return tier in _TIER_POOLS or tier == "random"
