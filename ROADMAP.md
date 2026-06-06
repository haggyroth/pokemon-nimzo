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

### v0.9 — Live Pipeline, Replay, Visual Polish & Richer Analysis
- **Live pipeline**: all battles (UI or CLI) routed through the shared EventBus; tournament progress visible in real time
- **Tournament UI**: configure N players and rounds in the browser; cancel individual battles mid-run; live progress bar + final standings overlay
- **Battle Replay**: step through any completed battle turn by turn; HP timeline SVG; scrub slider; keyboard nav (← → Space Esc); auto-play
- **Type-themed card backgrounds**: 18-type colour map; single-type corner wash; dual-type diagonal gradient split
- **Battle animations**: hit flash, sprite shake, heal pulse, faint fade — driven by HP delta tracking with `useRef`
- **Win probability timeline**: team HP ratio per turn; sparkline in analysis drawer and replay HP chart
- **Turning-point detection**: turn with the largest single-turn win-prob swing, highlighted in both replay and analysis
- **Blunder flagging**: suboptimal moves where score gap ≥ 40% of best option flagged with `⚠`; blunders panel in analysis
- **RNG inference**: possible crit / possible miss inferred from actual vs expected HP drop; badges in replay and analysis log
- 154 tests; parser fix for `"switch 1"` identifier form

### v0.10 — Hardening, Quality & Technical Debt
- **Wave R1 — Critical correctness fixes**: test suite stabilised; port 5001 enforced consistently across serve.py, vite config, and README
- **Wave R2 — Frontend lint + CI gate**: all 16 ESLint v10 / react-hooks v7 errors resolved; `npm run lint` added to CI; pytest coverage gate at 65%; `uv.lock` committed for reproducible builds
- **Wave R3 — Robustness**: `failed` battle status wired end-to-end; Pydantic `Field(ge/le)` bounds on all API inputs (422 on bad requests); 6 DB indexes for hot read paths; `finish_battle` + ELO update made fully atomic; CORS restricted to known origins; EventBus queues bounded (256) with drop-oldest overflow; events list capped at 500 in frontend
- **Wave R4 — Test coverage**: 35 new tests across `LLMPlayer`, `StreamingLLMPlayer`, `StreamingRandomBot`, `AnthropicBackend`, `OpenAIBackend`, `BattleStore`, and schema migrations; overall coverage 85%; schema migration bug found and fixed (`migrate()` would crash on v1 databases due to index creation before column existed)
- **Technical debt cleared**:
  - Heuristic status-move annotation replaced with exact `frozenset` lookups; bogus tokens (`"lovecaster"`, `"darkv"`) and Gen 6/7 moves removed
  - `AnthropicBackend` now iterates all content blocks — fixes crash on thinking-model responses where `content[0]` is a thinking block with no `.text`
  - Opponent `ability` field in serializer guarded against `"unknown"` sentinel (matching existing `item` guard)
  - Inline `store._conn.execute()` calls in `app.py` replaced with `BattleStore` methods (`get_turns_basic`, `get_battle_players`, `update_battle_tag`)
  - `serve.py --reload` fixed — now uses `factory=True` + import string so uvicorn hot-reload actually works
- 203 tests

---

## Upcoming

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

---

### Technical Debt & Housekeeping
*Cleared in v0.10 (marked ✅). Remaining items below.*

**Refactoring**
- ✅ Move inline SQL from `app.py` into `BattleStore` methods
- ✅ Replace `serve.py --reload` (now uses `factory=True` + import string)
- Split `app.py` into routing / orchestration / WebSocket layers — still growing

**Correctness**
- ✅ Heuristic status-move bogus tokens fixed; exact `frozenset` lookups
- ✅ `AnthropicBackend` multi-block / thinking-response crash fixed
- ✅ Opponent `ability` hidden-info guard added

**Infrastructure**
- Add structured logging + `/healthz` endpoint with graceful runner shutdown
- Add `mypy` / type-check gate to CI (types are already thorough)
- Add E2E smoke tests (Playwright) covering start → watch → replay → analyze
- Add Dependabot for Python and npm dependency updates
- Add `CHANGELOG.md` (Phase 5 milestone)
