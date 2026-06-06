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
- LM Studio `response_format=json_schema` for grammar-sampled valid JSON
- `reasoning_content` fallback for Qwen 3 thinking models
- Fuzzy species name matching (`difflib`, cutoff=0.82) for switch typos
- Retry on empty LLM response; logs `finish_reason` for diagnosis
- Thinking events: amber pulsing indicator while model reasons
- Gen 3 sprites via Showdown CDN with pixelated rendering
- Bench row: reserve Pokémon with mini-sprites + HP bars
- Model selector queries LM Studio's `/v1/models` for live chips
- WebSocket keepalive pings (25s) — eliminates reconnection churn
- CI pipeline: ruff lint + pytest + frontend build in parallel
- 127 tests including full API endpoint coverage
- Leaderboard grouped by model (aggregates across prompt versions; `v1`/`v2` pill tags)
- First meaningful ELO results: gemma-4-e2b 7-3 vs ministral-3-3b

---

## Upcoming

---

### Phase 1 — Live Pipeline & UI Foundation
*Goal: the GUI becomes the single point of entry. No terminal required to run or watch battles.*

**Live Battles** (pipeline integration)
- `tournament.py` routes battles through `POST /api/battles/start` instead of running directly
- All battles — scripted or UI-triggered — publish events to the shared WebSocket bus
- Tournament results visible live in the battlefield view, not just in the leaderboard after the fact
- Fix: handle `"identifier":"switch 1"` (model outputs full command string instead of slot number)

**UI as primary interface**
- Tournament launcher in the UI: configure N players, rounds, and format; start from the browser
- All settings and options accessible from the GUI (no CLI required for standard use)
- CLI scripts remain and stay in sync with GUI features, but are the secondary path

**Pause / Cancel Battle**
- Stop button in the battlefield view cancels a running battle gracefully
- Cancelled battles recorded in DB with `status=cancelled`; excluded from ELO

---

### Phase 2 — Replay, Analysis & Visibility
*Goal: every completed battle is fully reviewable and annotated.*

**Battle Replay**
- Step forward/backward through any completed battle turn by turn
- Battlefield view rehydrates from stored `state_json` — same visual layout as live
- Accessible from the Recent Battles panel with a ▶ REPLAY button

**RNG Annotation**
- Flag crits, misses, and secondary effect rolls in the turn log
- Post-game analysis distinguishes "model made a poor call" from "model got unlucky"
- RNG events highlighted in the replay timeline

**Battle Animations**
- Damage flash, shake, and faint animation for the active Pokémon cards
- Animated HP bar drains (smooth transition, not instant snap)
- Heal / status-recovery pulse effect
- Explore Pokémon Showdown's existing animation assets as a source

**Type-themed Card Backgrounds**
- Each Pokémon card gets a background that reflects its type combination
- Single-type: gradient wash in that type's palette (e.g. Fire = deep orange → ember glow)
- Dual-type: diagonal or angular gradient blending both type colours (e.g. Water/Flying = teal → sky violet)
- 18 base type palettes map to the existing `--type-*` CSS variables; dual-type combos are generated at render time
- Background shifts when the active Pokémon switches mid-battle (smooth CSS transition)
- Pairs with the card glow: border and glow colour also keyed to primary type

**Richer Post-game Analysis**
- Key turning-point detection: identify the turn where win probability shifted decisively
- Blunder annotation: flag decisions that were significantly worse than the best available option
- RNG-adjusted quality score: penalise bad decisions, not bad luck

---

### Phase 3 — Model Intelligence
*Goal: models become more interesting players over time.*

**Lessons / Memory**
- After each battle, a model generates a short lesson: what worked, what to avoid
- Lessons stored per model in the DB and injected into future system prompts
- Configurable memory window (last N lessons or last N turns of history)
- Enables cross-battle strategy evolution — models that adapt over time

**Multi-agent Reasoning** (coach / tutor mode)
- Optional: before acting, the player model queries a "coach" model for advice
- Coach receives the same battle state but no output constraints — free analysis
- Player weighs coach advice alongside its own reasoning
- Configurable: which models use a coach, which coach model to use

**Model Stats Pages**
- Dedicated page per model: full W/L/T history, ELO sparkline over time, opponent breakdown
- Decision quality distribution (optimal / good / suboptimal / fallback %)
- Model metadata pulled from Hugging Face API (architecture, parameters, license)
- Model-specific insights: common move preferences, switch frequency, fallback rate

**Win Probability**
- Real-time win probability estimate shown during live battles
- Based on current HP totals, remaining Pokémon, type matchups, speed advantage
- Displayed as a live bar at the top of the battlefield view

---

### Phase 4 — Battle Formats
*Goal: expand the strategic surface area.*

**Drafted Teams**
- Fixed teams defined before battle starts (no more random)
- LLM-drafted team mode: model builds a team from a pool of legal Pokémon
- Team stored in DB, tied to model entry for reproducible matchups

**Tournament Brackets**
- Single-elimination and double-elimination bracket modes
- Scheduled round-robins with configurable cadence
- Bracket visualizer in the UI showing live progression

**Doubles**
- 2v2 format with target selection (adds which-Pokémon-to-hit decision)
- Prompt and action parser extended for `target` field
- Heuristic engine updated for spread moves and partner synergy

---

### Phase 5 — Platform Expansion
*Goal: broaden the competitive scope.*

**Expanded Generation Support**
- Gen 4+ mechanics: held items, abilities, physical/special split
- Incremental: one generation at a time, validated against Showdown rules
- New prompt context for items and abilities (currently hidden from model)

**Deeper Competitive Features**
- Speed tie and priority bracket resolution visible in the battle log
- Weather and terrain strategies tracked in analysis
- Item usage annotated in turn logs
