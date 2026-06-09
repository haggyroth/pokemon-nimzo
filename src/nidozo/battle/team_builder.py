"""team_builder — convert a list of drafted species into a Showdown team string.

Reads standard Gen 3 movesets from ``data/gen3_movesets.json`` and serialises
a picked team into Pokémon Showdown's human-readable export format so it can be
passed to poke-env's ``Player(team=...)`` parameter.

Usage::

    from nidozo.battle.team_builder import build_team_string, load_movesets

    movesets = load_movesets()
    team_str = build_team_string(["salamence", "tyranitar", "gengar",
                                  "swampert", "skarmory", "blissey"],
                                  movesets)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve data/ relative to the repo root (four directories above this file).
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_MOVESETS_PATH = _REPO_ROOT / "data" / "gen3_movesets.json"

# Cache so we only read the file once per process.
_MOVESET_CACHE: dict[str, Any] | None = None


def load_movesets() -> dict[str, Any]:
    """Return the full moveset dictionary (cached after first call)."""
    global _MOVESET_CACHE
    if _MOVESET_CACHE is None:
        with _MOVESETS_PATH.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        # Strip the doc comment key if present
        data.pop("__comment", None)
        _MOVESET_CACHE = data
    return _MOVESET_CACHE


def all_species(movesets: dict[str, Any] | None = None) -> set[str]:
    """Return the set of all species IDs that have a defined moveset."""
    ms = movesets if movesets is not None else load_movesets()
    return set(ms.keys())


def build_pokemon_block(species_id: str, moveset: dict[str, Any]) -> str:
    """Render one Pokémon's Showdown export block.

    Example output::

        Salamence @ Choice Band
        Ability: Intimidate
        EVs: 4 HP / 252 Atk / 252 Spe
        IVs: 30 HP / 30 Atk / 30 Def / 30 SpA / 30 SpD
        Adamant Nature
        Level: 100
        - Dragon Claw
        - Rock Slide
        - Earthquake
        - Hidden Power [Flying]

    IVs default to 31 in all stats.  Only specify ``ivs`` in the moveset dict
    when a particular IV spread is required (e.g. to obtain a specific Hidden
    Power type).  Only non-31 values need to be listed — the rest are assumed 31.
    """
    species: str = moveset.get("species", species_id.title())
    item: str = moveset.get("item", "Leftovers")
    ability: str = moveset.get("ability", "")
    nature: str = moveset.get("nature", "Serious")
    level: int = moveset.get("level", 100)
    evs: dict[str, int] = moveset.get("evs", {})
    ivs: dict[str, int] = moveset.get("ivs", {})
    moves: list[str] = moveset.get("moves", [])

    lines: list[str] = []

    # Header
    if item:
        lines.append(f"{species} @ {item}")
    else:
        lines.append(species)

    if ability:
        lines.append(f"Ability: {ability}")

    if level != 100:
        lines.append(f"Level: {level}")

    # EVs — only include non-zero stats
    ev_parts = [f"{val} {stat}" for stat, val in evs.items() if val]
    if ev_parts:
        lines.append(f"EVs: {' / '.join(ev_parts)}")

    # IVs — only include non-31 stats (31 is the Showdown default)
    iv_parts = [f"{val} {stat}" for stat, val in ivs.items() if val != 31]
    if iv_parts:
        lines.append(f"IVs: {' / '.join(iv_parts)}")

    lines.append(f"{nature} Nature")

    for move in moves:
        lines.append(f"- {move}")

    return "\n".join(lines)


def build_team_string(
    species_ids: list[str],
    movesets: dict[str, Any] | None = None,
) -> str:
    """Build a full Showdown team export string for the given species list.

    Args:
        species_ids: List of 1–6 Showdown species IDs (e.g. ``["salamence", ...]``).
        movesets:    Optional pre-loaded moveset dict.  Loaded from disk if None.

    Returns:
        A multi-Pokémon Showdown export string (blocks separated by blank lines).

    Raises:
        KeyError: If a species ID is not found in the moveset data.
    """
    ms = movesets if movesets is not None else load_movesets()
    blocks: list[str] = []
    for sid in species_ids:
        if sid not in ms:
            raise KeyError(
                f"No moveset defined for species '{sid}'. "
                f"Add it to data/gen3_movesets.json first."
            )
        blocks.append(build_pokemon_block(sid, ms[sid]))
    return "\n\n".join(blocks)


def get_pool_info(species_ids: list[str], movesets: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return lightweight info dicts for a pool of species (for frontend display).

    Each dict has: ``species_id``, ``species`` (display name), ``types``.
    """
    ms = movesets if movesets is not None else load_movesets()
    result: list[dict[str, Any]] = []
    for sid in species_ids:
        entry = ms.get(sid, {})
        result.append({
            "species_id": sid,
            "species": entry.get("species", sid.title()),
            "types": entry.get("types", []),
        })
    return result
