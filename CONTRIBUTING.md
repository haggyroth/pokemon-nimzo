# Contributing

Thanks for your interest in contributing to Pokémon Nimzo.

## Getting started

1. Fork the repo and clone your fork.
2. Follow the setup steps in the README to get the Showdown server running and the Python environment installed.
3. Create a branch: `git checkout -b <type>/<short-description>` (e.g. `feat/llm-player`, `fix/reconnect-logic`).

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):
```
<type>(<scope>): <short description>
```
Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`. Keep the subject under 72 characters and use the imperative mood.

## Pull requests

- Open a PR against `main` for every change, even small ones.
- Describe **what**, **why**, and **how you tested it**.
- All PRs are squash-merged.

## Code style

- Python 3.12+, formatted with `ruff` (run `uv run ruff format .` before committing).
- No secrets, `.env` files, or credentials committed.
- The battle engine layer (`src/pokemon_nimzo/battle/`) must remain correct with respect to Showdown mechanics — bugs there corrupt every downstream result.

## Hidden information

If you touch prompt construction or battle-state serialization, be extremely careful about hidden information: a model must never see the opponent's unrevealed moves, items, or stats. Treat any leak as a correctness bug.
