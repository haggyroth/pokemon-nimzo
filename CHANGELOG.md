# Changelog

All notable changes to Nidozo are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Prompt v4** — battle event history (last 3 turns of HP deltas), explicit
  moveset revelation count per opponent mon, opponent threat map (which of your
  mons each revealed opponent threatens), cleaner section layout

---

## [0.12.0] — 2026-06-08

### Added
- **Coach mode** — optional pre-turn advisor: any model can query a separate
  "coach" model before acting; coach advice appended to the player's turn
  prompt; `agent: "coach"|"player"` field in WebSocket thinking events;
  `coach_advice TEXT` column added to turns table (schema v8)
- **Tournament brackets** — single-elimination and double-elimination formats
  with seeded byes for non-power-of-2 fields; lazy battle creation;
  `bracket_update` WebSocket event; `BracketView` React component;
  `tournament_format` and `bracket_state` columns added to tournaments table
  (schema v7)
- **Richer lesson prompting** — draft critique, variance report, and
  win-probability timeline now fully surfaced in the lesson generation prompt;
  lessons grounded in specific blunders and turning-point turns rather than
  generic reflection; new helper functions in `lesson_generator.py`
- **Tier 1 test coverage** — 565 tests at 88% overall coverage; targeted unit
  tests for all pure-Python modules: analyzer RNG inference paths, heuristic
  edge cases, bracket routing, schema migration idempotency, API validation

---

## [0.11.0] — 2026-05

### Added
- **Cross-battle lessons** — LLM generates a 2–3 sentence lesson after each
  battle; stored in SQLite `lessons` table; injected into future system prompts
  so models adapt strategy over time
- **Per-model stats page** — W/L/T history, ELO sparkline, opponent breakdown,
  decision-quality distribution, lesson log
- **Richer post-game analysis** — per-turn key moments (blunders, RNG events,
  turning point); `AnalysisSummary` panel in Battle Replay with clickable
  moments; blunder flagging (≥40% score gap); probable crit/miss inference from
  HP delta; win-probability timeline from team HP ratio
- **Tournament mode** — round-robin with live progress, standings overlay, and
  mid-run cancel support; full tournament history page
- **Drafted teams + Smogon meta tiers** — LLM snake-drafts a 6-mon team from a
  curated pool; 8 tier formats (Random / OU / UU / NU / LC / Ubers /
  Freeforall); DraftPhase UI; `teams` table in DB; rosters on result card
- **Heuristic overhaul** — speed-tier awareness (Gen 3 paralysis ×0.25),
  weather damage modifier, accuracy-adjusted damage estimates, low-PP warnings,
  battle context block, switch quality scoring with matchup labels
- **Draft critique** — team composition analysis: STAB coverage, shared
  weaknesses, coverage gaps, execution quality
- **Variance report** — structured RNG tally with per-player benefit counts and
  plain-English verdict
- **Gen 3 pool expansion** — 93 → 153 species with Smogon ADV sets
- mypy strict mode enforced across all source files; 358 tests

---

## [0.10.0] — 2026-05

### Added
- Frontend ESLint v10 CI gate; pytest coverage gate at 65%
- Pydantic `Field(ge/le)` bounds on all API inputs (422 on bad requests)
- 6 DB indexes for hot read paths
- Atomic `finish_battle` + ELO update; EventBus queues bounded at 256

### Fixed
- `failed` battle status wired end-to-end
- `migrate()` crash on v1 databases (index before column existed)
- `AnthropicBackend` multi-block response crash
- Opponent `ability` hidden-information guard; `serve.py --reload`

### Changed
- Inline SQL consolidated into `BattleStore`; heuristic bogus tokens removed
- 203 tests

---

## [0.9.0] — 2026-04

### Added
- Live pipeline — all battles routed through shared EventBus
- Battle Replay — scrub slider, keyboard nav, auto-play, HP timeline SVG
- Type-themed card backgrounds (18-type colour map, diagonal dual-type gradient)
- Battle animations — hit flash, sprite shake, heal pulse, faint fade
- Win probability timeline, turning-point detection, blunder flagging, RNG
  inference; tournament UI with live progress and cancel

### Fixed
- Parser fix for `"switch 1"` identifier form

### Changed
- 154 tests

---

## [0.8.0] — 2026-04

### Added
- Prompt v2 — JSON structured output; LM Studio grammar sampling
- Fuzzy species name matching (difflib, cutoff 0.82)
- Thinking events (amber pulse), Gen 3 sprites (Showdown CDN), bench row
- Model selector (live LM Studio `/v1/models`), WebSocket keepalive (25 s)
- CI pipeline: ruff + pytest + frontend build in parallel

### Fixed
- `reasoning_content` fallback for Qwen 3 thinking models
- Leaderboard duplicate rows (UNION ALL bug)

### Changed
- 127 tests; first ELO results: gemma-4-e2b 7-3 vs ministral-3-3b

---

## [0.7.0] — 2026-03

### Added
- Round-robin tournament CLI (`scripts/tournament.py`)
- Per-player model fields (separate p1/p2 provider + model in API and UI)
- Parser hardening for name-based actions and markdown-wrapped output

### Changed
- First live LLM battles: Ministral-3-3b vs Granite-4-h-tiny (12-0)

---

## [0.6.0] — 2026-03

### Added
- Post-game analysis: per-turn decision quality annotation (optimal / good /
  suboptimal / fallback); `/api/battles/{id}/analysis`; analysis panel in UI

---

## [0.5.0] — 2026-02

### Added
- FastAPI backend + WebSocket live-battle feed (`/ws/battles`)
- React + Vite frontend: retro CRT dark-theme battlefield visualizer
- Live Pokémon cards (animated HP bars, type badges, status, stat boosts),
  battle log, heuristic advisory drawer, winner banner

---

## [0.4.0] — 2026-02

### Added
- SQLite persistence: battles, turns, elo_ratings, elo_history, models
- ELO calculation (K=32) updated after each battle; leaderboard CLI

---

## [0.3.0] — 2026-01

### Added
- Heuristic engine: type effectiveness, estimated damage %, stat stages,
  priority, status annotation, switch matchup scoring; advisory not prescriptive

---

## [0.2.0] — 2026-01

### Added
- Pluggable model backend: Anthropic + OpenAI cloud; LM Studio local
- Battle state serializer with hidden-information enforcement
- Prompt v1: battle state, legal actions, `ACTION: move N` output format
- Versioned prompts; `LLMPlayer` full loop

---

## [0.1.0] — 2026-01

### Added
- Repo scaffold, Python project (`uv`, `pyproject.toml`)
- Local Pokémon Showdown server wired with poke-env
- Two RandomBots complete a Gen 3 random singles battle end to end
