# Roadmap

## v0.1 — Foundation (current)
- [x] Repo scaffold: Python project, venv, pyproject.toml
- [x] Local Pokémon Showdown server wired up with poke-env
- [x] Two RandomBots complete a Gen 3 random singles battle end to end

## v0.2 — LLM Decision Layer
- [ ] Pluggable model backend: Anthropic + OpenAI cloud APIs
- [ ] Local model support via LM Studio (OpenAI-compatible API)
- [ ] Battle state serializer with hidden-information enforcement (correctness requirement)
- [ ] System prompt v1: battle state format, legal actions, tagged-action output schema (`ACTION: move 3`)
- [ ] Versioned prompts — correlate prompt changes with ELO shifts
- [ ] `LLMPlayer` wiring the full loop: state → prompt → backend → action parser → `BattleOrder`

## v0.3 — Heuristic Engine
- [ ] Heuristic scorer: type effectiveness, expected damage, speed comparison, stat stages, status value, switch value
- [ ] Scores surfaced to LLM as advisory context (not a hard filter)

## v0.4 — ELO & Persistence
- [ ] SQLite schema: matches, turns, ELO history, team logs, prompt versions
- [ ] ELO calculation and update after each battle
- [ ] Per-model stats and leaderboard CLI output

## v0.5 — API & Visualizer
- [ ] FastAPI backend with WebSocket live-battle feed
- [ ] React frontend: live battlefield visualizer (adapted from Nimzo's pattern)
- [ ] Post-game analysis: annotate RNG swings (crits, misses), key decision points

## Future
- Drafted teams (including LLM-drafted team mode)
- Doubles battles
- Expanded generation support beyond Gen 3
- Tournament brackets and scheduled round-robins
- Richer post-game analysis and blunder detection
- Structured JSON action output schema (`{"type": "move", "slot": 3}`) — more robust for doubles, better for programmatic analysis
- Settle the final project name
