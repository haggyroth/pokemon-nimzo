# Roadmap

## Completed

### v0.1 — Foundation
- Repo scaffold, Python project, venv, pyproject.toml
- Local Pokémon Showdown server wired up with poke-env
- Two RandomBots complete a Gen 3 random singles battle end to end

### v0.2 — LLM Decision Layer
- Pluggable model backend: Anthropic + OpenAI cloud APIs
- Local model support via LM Studio (OpenAI-compatible API)
- Battle state serializer with hidden-information enforcement
- System prompt v1: battle state format, legal actions, `ACTION: move N` output schema
- Versioned prompts for correlating changes with ELO shifts
- `LLMPlayer` full loop: state → prompt → backend → action parser → `BattleOrder`

### v0.3 — Heuristic Engine
- Type effectiveness, estimated damage %, stat stages, priority, status annotation
- Switch matchup scoring
- Heuristic scores surfaced to LLM as advisory context (not a hard filter)

### v0.4 — ELO & Persistence
- SQLite schema: battles, turns, elo_ratings, elo_history, models, prompt versions
- ELO calculation (K=32) updated after each battle
- Per-model stats, turn logging, leaderboard CLI

### v0.5 — API & Visualizer
- FastAPI backend with WebSocket live-battle feed (`/ws/battles`)
- REST endpoints: leaderboard, battles, turns, start-battle
- React + Vite frontend: retro CRT dark-theme battlefield visualizer
- Live Pokémon cards with animated HP bars, type badges, status, stat boosts
- Battle log, heuristic advisory drawer, winner banner

### v0.6 — Post-game Analysis
- Per-turn decision quality annotation: optimal / good / suboptimal / fallback
- Analysis compares chosen action against heuristic ranking
- `/api/battles/{id}/analysis` endpoint
- Analysis panel in the UI with quality bars and turn-by-turn breakdown

### v0.7 — Tournament Runner & Real Battles
- Round-robin tournament CLI (`scripts/tournament.py`)
- Per-player model fields in API and UI
- First live LLM battles: Ministral-3-3b vs Granite-4-h-tiny (12-0 result)
- Parser hardened for name-based actions and markdown-wrapped output
- Leaderboard SQL bug fixed (duplicate rows from UNION ALL)

### v0.8 — JSON Outputs, Engine Reliability, UI Polish
- **v2 prompt**: JSON structured output (`{"reasoning","action_type","identifier"}`)
- LM Studio `response_format=json_object` for grammar-sampled valid JSON
- Retry on empty LLM response; logs `finish_reason` for diagnosis
- Thinking events: amber pulsing indicator while model reasons
- Gen 3 sprites via Showdown CDN with pixelated rendering
- Bench row: reserve Pokémon with mini-sprites + HP bars
- Model selector queries LM Studio's `/v1/models` for live chips
- WebSocket keepalive pings (25s) — eliminates reconnection churn
- CI pipeline: ruff lint + pytest + frontend build in parallel
- 123 tests including full API endpoint coverage

---

## Upcoming

### Near-term
- **Expanded model testing** — run more model pairs, build a real ELO ranking
- **Pause / cancel battle** — stop a running battle from the UI
- **Battle replay** — step through a completed battle turn by turn
- **RNG annotation** — flag crits, misses, and secondary effects in post-game analysis so variance is visible and model decisions aren't blamed for luck

### Medium-term
- **Drafted teams** — fixed teams instead of random; includes an LLM-drafted team mode
- **Expanded generation support** — beyond Gen 3 (Gen 4+ mechanics, items, abilities)
- **Tournament brackets** — single-elim, double-elim, scheduled round-robins
- **Richer post-game analysis** — key turning-point detection, blunder annotation

### Long-term
- **Doubles** battles (adds target-selection complexity)
- **Multi-agent reasoning** — let a model consult a "coach" model before deciding
