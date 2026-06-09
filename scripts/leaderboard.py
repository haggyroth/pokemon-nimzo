"""
Print the current ELO leaderboard and recent battle results.

Usage:
    uv run python scripts/leaderboard.py
    uv run python scripts/leaderboard.py --db path/to/nidozo.db
"""

import argparse
import os
from pathlib import Path

from nidozo.db.store import BattleStore


def main(db_path: Path) -> None:
    if not db_path.exists():
        print(f"No database at {db_path} — run some battles first.")
        return

    store = BattleStore(db_path)

    print("\n=== LEADERBOARD ===\n")
    rows = store.leaderboard()
    if not rows:
        print("  No models recorded yet.")
    else:
        header = f"{'#':<4} {'Model':<40} {'Prompt':<8} {'ELO':>7} {'Games':>6} {'W':>5} {'L':>5} {'T':>5}"
        print(header)
        print("-" * len(header))
        for i, r in enumerate(rows, 1):
            label = f"{r['provider']}/{r['model_name']}"
            print(
                f"{i:<4} {label:<40} {r['prompt_version']:<8} "
                f"{r['rating']:>7.1f} {r['games']:>6} "
                f"{r['wins']:>5} {r['losses']:>5} {r['ties']:>5}"
            )

    print("\n=== RECENT BATTLES ===\n")
    battles = store.recent_battles(limit=10)
    if not battles:
        print("  No completed battles yet.")
    else:
        for b in battles:
            w = "p1" if b["winner"] == 1 else ("p2" if b["winner"] == 2 else "tie")
            turns = b["total_turns"] or "?"
            print(
                f"  {b['p1']} vs {b['p2']}  —  winner: {w}  "
                f"turns: {turns}  [{b['finished_at']}]"
            )

    store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show ELO leaderboard")
    parser.add_argument("--db", default=None, help="Path to SQLite DB")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else Path(
        os.environ.get("NIDOZO_DB", "nidozo.db")
    )
    main(db_path)
