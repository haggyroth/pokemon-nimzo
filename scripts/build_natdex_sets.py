"""build_natdex_sets.py — generate data/natdex_movesets.json from Showdown's own data.

Sources (both shipped with the local Showdown install):
  1. showdown/data/random-battles/gen9/factory-sets.json
     Full competitive sets (items, EVs, natures, moves) for ~223 species across
     6 Smogon tiers (Uber / OU / UU / RU / NU / PU).  These are the highest-quality
     entries and are always preferred.

  2. showdown/data/random-battles/gen9/sets.json
     Random-battle sets for ~508 species (includes cross-gen national-dex Pokémon).
     No items / EVs / natures — those are synthesised from the set's "role" tag.

Output schema (same as gen3_movesets.json):
  {
    "<species_id>": {
      "species":  "Displayname",
      "item":     "Leftovers",
      "ability":  "Blaze",
      "nature":   "Modest",
      "evs":      { "HP": 252, "SpA": 252, "Spe": 4 },
      "moves":    ["Flamethrower", "Focus Blast", "Nasty Plot", "Substitute"],
      "types":    ["Fire"],          // informational
      "tier":     "OU",              // informational
      "source":   "factory|synth"   // informational
    }
  }

Run from the repo root:
  python scripts/build_natdex_sets.py
  python scripts/build_natdex_sets.py --out data/natdex_movesets.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT     = Path(__file__).parent.parent
FACTORY_FILE  = REPO_ROOT / "showdown/data/random-battles/gen9/factory-sets.json"
RANDBAT_FILE  = REPO_ROOT / "showdown/data/random-battles/gen9/sets.json"
POKEDEX_FILE  = REPO_ROOT / "showdown/data/pokedex.ts"     # fallback for types
DEFAULT_OUT   = REPO_ROOT / "data/natdex_movesets.json"

# ---------------------------------------------------------------------------
# Stat-key normalisation
# ---------------------------------------------------------------------------

_STAT_MAP = {
    "hp":  "HP",
    "atk": "Atk",
    "def": "Def",
    "spa": "SpA",
    "spd": "SpD",
    "spe": "Spe",
}


def _norm_evs(raw: dict[str, int]) -> dict[str, int]:
    """Normalise lowercase stat keys → Showdown export capitalisation."""
    return {_STAT_MAP.get(k, k): v for k, v in raw.items() if v}


# ---------------------------------------------------------------------------
# Role → item / EVs / nature heuristics (used for synthesised sets only)
# ---------------------------------------------------------------------------

_ROLE_DEFAULTS: dict[str, dict] = {
    "Fast Attacker": {
        "item": "Life Orb",
        "evs": {"HP": 4, "Atk": 252, "Spe": 252},
        "nature": "Jolly",
        "spa_nature": "Timid",
    },
    "Setup Sweeper": {
        "item": "Life Orb",
        "evs": {"HP": 4, "Atk": 252, "Spe": 252},
        "nature": "Jolly",
        "spa_nature": "Timid",
    },
    "Wallbreaker": {
        "item": "Choice Band",
        "evs": {"HP": 4, "Atk": 252, "Spe": 252},
        "nature": "Adamant",
        "spa_nature": "Modest",
    },
    "Choice Item user": {
        "item": "Choice Scarf",
        "evs": {"HP": 4, "Atk": 252, "Spe": 252},
        "nature": "Jolly",
        "spa_nature": "Timid",
    },
    "Bulky Attacker": {
        "item": "Leftovers",
        "evs": {"HP": 252, "Atk": 252, "Def": 4},
        "nature": "Adamant",
        "spa_nature": "Modest",
    },
    "Bulky Support": {
        "item": "Leftovers",
        "evs": {"HP": 252, "Def": 128, "SpD": 128},
        "nature": "Bold",
        "spa_nature": "Calm",
    },
    "Hazard Setter": {
        "item": "Rocky Helmet",
        "evs": {"HP": 252, "Def": 128, "SpD": 128},
        "nature": "Impish",
        "spa_nature": "Calm",
    },
    "Pivot": {
        "item": "Leftovers",
        "evs": {"HP": 252, "Def": 128, "SpD": 128},
        "nature": "Bold",
        "spa_nature": "Calm",
    },
    "Spinner": {
        "item": "Heavy-Duty Boots",
        "evs": {"HP": 252, "Def": 128, "SpD": 128},
        "nature": "Bold",
        "spa_nature": "Calm",
    },
    "Stall": {
        "item": "Leftovers",
        "evs": {"HP": 252, "Def": 252, "SpD": 4},
        "nature": "Bold",
        "spa_nature": "Calm",
    },
    "AV user": {
        "item": "Assault Vest",
        "evs": {"HP": 252, "Atk": 252, "SpD": 4},
        "nature": "Adamant",
        "spa_nature": "Modest",
    },
    "Berry user": {
        "item": "Sitrus Berry",
        "evs": {"HP": 252, "Atk": 252, "Spe": 4},
        "nature": "Adamant",
        "spa_nature": "Modest",
    },
    "Tera Blast user": {
        "item": "Life Orb",
        "evs": {"HP": 4, "SpA": 252, "Spe": 252},
        "nature": "Timid",
        "spa_nature": "Timid",
    },
    "Doubles": {
        "item": "Life Orb",
        "evs": {"HP": 4, "Atk": 252, "Spe": 252},
        "nature": "Jolly",
        "spa_nature": "Timid",
    },
}

_DEFAULT_FALLBACK = {
    "item": "Leftovers",
    "evs": {"HP": 4, "Atk": 252, "Spe": 252},
    "nature": "Jolly",
    "spa_nature": "Timid",
}


def _is_special(movepool: list[str]) -> bool:
    """Heuristic: does this set lean special (> half of moves are special type moves)?"""
    special_keywords = {
        "blast", "beam", "pulse", "ball", "bolt", "flamethrower", "surf",
        "thunderbolt", "icebeam", "psychic", "shadowball", "energyball",
        "moonblast", "dazzlinggleam", "dragonpulse", "focusblast",
        "nastyplot", "calmmind", "auraphere", "darkpulse", "scald",
        "eruption", "waterspout", "spacialtempest", "roaroftime",
        "flashcannon", "thunderwave", "willowisp", "toxic",
    }
    flat = " ".join(m.lower().replace(" ", "") for m in movepool)
    hits = sum(1 for kw in special_keywords if kw in flat)
    return hits >= 2


def _synth_set(role: str, movepool: list[str], abilities: list[str]) -> dict:
    """Synthesise a competitive set from role + movepool when no factory data exists."""
    defs = _ROLE_DEFAULTS.get(role, _DEFAULT_FALLBACK)
    prefer_special = _is_special(movepool)

    item = defs["item"]
    evs  = dict(defs["evs"])
    nature = defs.get("spa_nature", defs["nature"]) if prefer_special else defs["nature"]

    # Adjust EVs for special orientation
    if prefer_special:
        evs = {k.replace("Atk", "SpA"): v for k, v in evs.items()}

    moves = movepool[:4]   # pick first 4 from the pool
    ability = abilities[0] if abilities else ""

    return {
        "item":    item,
        "evs":     evs,
        "nature":  nature,
        "ability": ability,
        "moves":   moves,
    }


# ---------------------------------------------------------------------------
# Species display-name helper
# ---------------------------------------------------------------------------

def _to_display(species_id: str) -> str:
    """Convert 'corviknightmirror' → 'Corviknightmirror' (best-effort title case)."""
    # Showdown IDs are all-lowercase; capitalise first letter only
    return species_id[:1].upper() + species_id[1:]


# ---------------------------------------------------------------------------
# Type extraction from pokedex.ts
# ---------------------------------------------------------------------------

def _load_types_from_pokedex() -> dict[str, list[str]]:
    """Parse species → types from Showdown's pokedex.ts (TypeScript source)."""
    try:
        text = POKEDEX_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    types_map: dict[str, list[str]] = {}
    # Pattern: "species_id": { ... types: ["Type1", "Type2"] ... }
    block_re  = re.compile(r'"?(\w+)"?\s*:\s*\{([^}]+)\}', re.DOTALL)
    types_re  = re.compile(r'types\s*:\s*\[([^\]]+)\]')

    for m in block_re.finditer(text):
        key   = m.group(1).lower()
        body  = m.group(2)
        tm    = types_re.search(body)
        if tm:
            raw_types = [t.strip().strip("'\",") for t in tm.group(1).split(",")]
            types_map[key] = [t.title() for t in raw_types if t]

    return types_map


# ---------------------------------------------------------------------------
# Process factory-sets.json
# ---------------------------------------------------------------------------

def _process_factory(factory_data: dict) -> dict[str, dict]:
    """
    Convert factory-sets structure to our flat species dict.

    Factory structure:
      { "Uber": { "zacian": { "weight": 8, "sets": [{ "species": "Zacian",
          "item": [...], "ability": [...], "evs": {...}, "nature": [...],
          "moves": [[opt1, opt2], [only], ...] }] } } }
    """
    result: dict[str, dict] = {}
    tier_order = ["Uber", "OU", "UU", "RU", "NU", "PU"]

    for tier in tier_order:
        tier_data = factory_data.get(tier, {})
        for species_id, species_block in tier_data.items():
            sid = species_id.lower()
            if sid in result:
                continue  # already added from higher tier

            sets = species_block.get("sets", [])
            if not sets:
                continue

            # Take the first (highest-weight) set
            s = sets[0]
            display = s.get("species", _to_display(sid))

            # Items: take first option
            items = s.get("item", ["Leftovers"])
            item  = items[0] if items else "Leftovers"

            # Abilities: take first
            abils = s.get("ability", [""])
            ability = abils[0] if abils else ""

            # EVs: normalise keys
            evs = _norm_evs(s.get("evs", {}))

            # Natures: take first
            natures = s.get("nature", ["Hardy"])
            nature  = natures[0] if natures else "Hardy"

            # Moves: each slot is a list of options — pick first per slot
            raw_moves: list[list[str]] = s.get("moves", [])
            moves = [slot[0] for slot in raw_moves if slot][:4]

            result[sid] = {
                "species": display,
                "item":    item,
                "ability": ability,
                "nature":  nature,
                "evs":     evs,
                "moves":   moves,
                "tier":    tier,
                "source":  "factory",
            }

    return result


# ---------------------------------------------------------------------------
# Process randbat sets.json (supplemental)
# ---------------------------------------------------------------------------

def _process_randbat(randbat_data: dict, existing: set[str]) -> dict[str, dict]:
    """
    Synthesise sets for species in randbat data that aren't already covered.

    Randbat structure:
      { "venusaur": { "level": 84, "sets": [{ "role": "Bulky Support",
          "movepool": [...], "abilities": [...], "teraTypes": [...] }] } }
    """
    result: dict[str, dict] = {}

    for species_id, species_block in randbat_data.items():
        sid = species_id.lower()
        if sid in existing:
            continue

        sets = species_block.get("sets", [])
        if not sets:
            continue

        # Pick the first set
        s     = sets[0]
        role  = s.get("role", "")
        pool  = s.get("movepool", [])
        abils = s.get("abilities", [])

        synth = _synth_set(role, pool, abils)

        result[sid] = {
            "species": _to_display(sid),
            "item":    synth["item"],
            "ability": synth["ability"],
            "nature":  synth["nature"],
            "evs":     synth["evs"],
            "moves":   synth["moves"],
            "tier":    "randbat",
            "source":  "synth",
        }

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(out_path: Path) -> None:
    print(f"Loading factory sets from {FACTORY_FILE} …")
    with FACTORY_FILE.open(encoding="utf-8") as f:
        factory_data = json.load(f)

    print(f"Loading randbat sets from {RANDBAT_FILE} …")
    with RANDBAT_FILE.open(encoding="utf-8") as f:
        randbat_data = json.load(f)

    print("Loading type data from pokedex.ts …")
    types_map = _load_types_from_pokedex()

    # Build from factory first (highest quality), then supplement with randbat
    factory_entries = _process_factory(factory_data)
    randbat_entries = _process_randbat(randbat_data, set(factory_entries.keys()))

    combined: dict[str, dict] = {**factory_entries, **randbat_entries}

    # Attach type data where available
    for sid, entry in combined.items():
        types = types_map.get(sid, [])
        if types:
            entry["types"] = types

    # Sort by species name for readability
    combined = dict(sorted(combined.items()))

    stats = {
        "factory": sum(1 for e in combined.values() if e["source"] == "factory"),
        "synth":   sum(1 for e in combined.values() if e["source"] == "synth"),
        "total":   len(combined),
        "with_types": sum(1 for e in combined.values() if e.get("types")),
    }
    print("\nResults:")
    print(f"  Factory (competitive quality): {stats['factory']}")
    print(f"  Synthesised (from randbat):     {stats['synth']}")
    print(f"  Total species:                  {stats['total']}")
    print(f"  With type data:                 {stats['with_types']}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nWrote {stats['total']} species to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build national dex movesets JSON from Showdown data")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output path (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()
    build(args.out)
