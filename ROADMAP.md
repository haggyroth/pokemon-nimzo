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
- **Technical debt cleared**: heuristic bogus tokens removed; `AnthropicBackend` multi-block crash fixed; opponent `ability` hidden-info guard; inline SQL moved to `BattleStore`; `serve.py --reload` fixed
- 203 tests

### v0.11 — Memory, Intelligence, Drafted Teams & Deep Analysis
- **Cross-battle lessons**: after each battle the LLM generates a short lesson (what worked, what to avoid); stored per model in SQLite; injected into future system prompts so models evolve strategy across battles
- **Per-model stats page**: full W/L/T history, ELO sparkline, opponent breakdown, decision-quality distribution, lesson log — all in-browser
- **Richer post-game analysis**: per-turn key moments list (blunders, RNG events, turning point); enhanced lesson generation grounded in specific blunders; `AnalysisSummary` panel in Battle Replay with clickable moments that seek to the turn
- **Tournament mode**: configure N models and rounds in the browser; round-robin; live progress + standings overlay; cancel individual battles mid-run; full tournament history page
- **Drafted teams + Smogon meta tiers**: LLM snake-drafts a 6-mon team from a curated pool; 8 tier formats (Random / OU / UU / NU / LC / Ubers / Freeforall); DraftPhase UI with animated pick reveal; `teams` table in DB; drafted team rosters shown on post-battle result card
- **Tier context in UI**: tier badges throughout battlefield, leaderboard, tournament scoreboard; tier filter tabs on leaderboard
- **Heuristic overhaul**: speed-tier awareness (Gen 3 paralysis ×0.25), weather damage modifier, accuracy-adjusted damage estimates, low-PP warnings, battle context block (matchup quality, remaining counts, status impact), switch quality scoring with matchup labels
- **Draft critique**: team composition analysis — STAB offensive type spread, shared defensive weaknesses (Gen 3 type chart), coverage gaps, execution quality (blunders + decision_quality_pct)
- **Variance report**: structured tally of all inferred RNG events (crits + misses) with per-player benefit counts and plain-English verdict; new `VarianceReport` and `DraftCritiqueSection` panels in Battle Replay
- **Gen 3 pool expansion**: 93 → 153 species with Smogon ADV competitive sets covering all missing starters (Blaziken, Charizard, Venusaur, Blastoise), legends (Raikou, Entei, Regirock, Registeel), and popular UU/NU picks; all Gen 3 legal (no Gen 4+ moves)
- 358 tests; mypy strict enforced across all source files

### v0.12 — Coach Mode, Brackets & Richer Lessons
- **Multi-agent coach mode**: optional pre-turn coach model queries the same battle state with no output constraints; coach advice appended to player prompt; `agent: "coach"|"player"` thinking events in the UI; `coach_advice` column in turns table (schema v8)
- **Tournament brackets**: single-elimination and double-elimination bracket modes with seeded byes for non-power-of-2 fields; lazy battle creation; `bracket_update` WebSocket event; `BracketView` UI with bracket progression visualizer; `tournament_format` and `bracket_state` columns (schema v7)
- **Richer lesson prompting**: draft critique, variance report, and win-probability data now fully surfaced in the lesson prompt; lesson grounded in specific blunders and turning-point turns rather than generic reflection
- **Tier 1 test coverage**: 564 tests at 88% coverage; targeted unit tests for analyzer, heuristics, bracket, store, schema, serializer, action parser, and API routes

---

## Upcoming

---

### Near Term — LLM Intelligence & Viewing Experience

~~**Prompt v4 — Structured opponent knowledge + battle history**~~ ✅ *shipped in v0.13.0*

~~**Head-to-head matchup matrix**~~ ✅ *shipped in v0.13.0*

~~**Live win-probability bar**~~ ✅ *shipped in v0.9.0*

~~**Season concept**~~ ✅ *shipped in v0.14.0*
- Named seasons with a fixed participant list, round-robin scheduling, and isolated per-season ELO
- Live standings page, progress bar, and battle history per season
- Season history panel in the leaderboard; start/cancel from the UI

---

### Phase 5 — Platform Expansion
*Goal: broaden the competitive scope and polish.*

**Doubles**
- 2v2 format with target selection (adds which-Pokémon-to-hit decision)
- Prompt and action parser extended for `target` field
- Heuristic engine updated for spread moves and partner synergy

**Expanded Generation Support**
- Gen 4+ mechanics: held items, abilities, physical/special split
- Incremental: one generation at a time, validated against Showdown rules

**Deeper Competitive Features**
- Battle event annotation: item activations (Leftovers, Lum Berry), ability procs (Intimidate, Synchronize), status cures shown inline in the battle log and replay
- Speed tie and priority bracket resolution visible in the battle log
- Weather and terrain strategies tracked in analysis

---

### Technical Debt & Housekeeping

**Refactoring**
- Split `app.py` into routing / orchestration / WebSocket layers — still growing

**Test Coverage**
- *Tier 1 complete at 88%* — pure unit tests for analysis, heuristics, bracket, store, schema, API routes (565 tests)
- ~~**Tier 2**~~ ✅ *shipped — async mock-heavy tests for `api/events.py`, `api/ws.py`, `api/helpers.py`, `api/app.py`; 649 tests at 89% coverage*
- **Tier 3** — integration tests for `battle/orchestration.py` and `llm/draft.py` that require a live local Showdown server; intended to run in a separate CI job with a `[integration]` marker; estimated ~333 lines, would push total past 95%

**Infrastructure**
- Add E2E smoke tests (Playwright) covering start → watch → replay → analyze
- Add Dependabot for Python and npm dependency updates
