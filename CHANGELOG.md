# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **Multi-agent coach mode** — before each turn, a configurable "coach" model receives the same battle state (same hidden-information rules) and returns free-form strategic analysis in plain English; that advice is then injected into the player model's prompt before it chooses an action. Configurable per player in both the battle form and the tournament form. Coach advice is stored in the `turns` table (`coach_advice TEXT`), surfaced in the battle-replay turn panel (🎓 toggle), and emitted as typed WebSocket events (`agent: "coach" | "player"`) so the live battlefield shows a distinct teal "COACH ANALYZING" badge. Supports any provider (Anthropic, OpenAI, LM Studio) independently of the player's provider (#50)
- **Tournament brackets** — single-elimination and double-elimination formats alongside existing round-robin. SE: correctly seeded bracket (seed 1 meets seed 2 only in the final) with bye handling for non-power-of-2 player counts. DE: winners bracket + losers bracket with correct WB→LB loser routing, LB survivor vs WB-loser pairing per round, grand final + bracket-reset match (GFR activated if the LB player wins the GF). Brackets are created lazily (one round at a time) so future matchups aren't pre-committed. Champion identity included in `tournament_end` event. Bracket state persisted to SQLite and surfaced via API; `bracket_update` WebSocket event after each match. 27 new bracket unit tests (#51)
- **Bracket visualizer** in TournamentView — "BRACKET" tab (default for elim formats) shows a scrollable match-card grid: seeds, player names, live-pulsing highlight for the running match, winner ✓ / loser dimming, replay button per match. Double-elim shows WB, LB, and Grand Final as separate sections
- **Format selector** in the tournament form — three chips: Round Robin / Single Elimination / Double Elimination; rounds-per-matchup field hidden for elimination formats; battle count estimate updates instantly
- Live win-probability bar in the BattleField view — updates each turn from team HP data; animates with a smooth CSS transition (#48)

### Changed
- DB schema bumped to v8 (non-breaking: v7 adds `tournament_format`/`bracket_state` to `tournaments`; v8 adds `coach_advice TEXT` to `turns`)
- `api/app.py` (1009 lines) split into focused modules: `models.py`, `helpers.py`, `orchestration.py`, `routes.py`, `ws.py`; `app.py` is now a slim factory (#47)

---

## [0.11.0] — 2026-05-24

### Added
- **Cross-battle lessons** — after each battle the LLM generates a short lesson; stored per model in SQLite; injected into future system prompts so models adapt strategy over time
- **Per-model stats page** — W/L/T history, ELO sparkline, opponent breakdown, decision-quality distribution, lesson log — all in-browser
- **Draft critique** — post-game team composition analysis: STAB offensive type spread, shared defensive weaknesses (Gen 3 type chart), coverage gaps, execution quality (blunders + decision_quality_pct); rendered as a new panel in Battle Replay
- **Variance report** — structured tally of all inferred RNG events (crits + misses) with per-player benefit counts and plain-English verdict; rendered as a new panel in Battle Replay
- **Richer post-game analysis** — per-turn key moments list (blunders, RNG events, turning point); key moments are clickable in the UI and seek the replay to the relevant turn
- **Gen 3 pool expansion** — 93 → 153 species with Smogon ADV competitive sets: all missing starters (Blaziken, Charizard, Venusaur, Blastoise), legendaries (Raikou, Entei, Regirock, Registeel), and popular UU/NU picks; all Gen 3 legal
- **Tournament mode** — configure N models and rounds in the browser; round-robin; live progress + standings overlay; cancel individual battles mid-run; full tournament history page

### Changed
- Heuristic engine overhauled: speed-tier awareness (Gen 3 paralysis ×0.25), weather damage modifier, accuracy-adjusted damage estimates, low-PP warnings, battle context block (matchup quality, remaining counts, status impact), switch quality scoring with matchup labels
- Enhanced lesson generation grounds reflection in specific blunders, RNG events, and draft critique rather than generic battle summary
- `mypy --strict` enforced across all 32 source files

### Fixed
- `_load_species_data()` mypy `[no-any-return]` error under `--strict` (explicit local annotation on `json.load()` result)
- Seviper EV total exceeded 510; fixed by removing the stray HP entry

---

## [0.10.0] — 2026-04-12

### Added
- `failed` battle status wired end-to-end (previously battles could silently stall)
- 6 DB indexes for hot read paths (leaderboard, ELO history, turn lookups)
- `uv.lock` committed for reproducible builds
- 35 new tests covering `LLMPlayer`, `StreamingLLMPlayer`, `AnthropicBackend`, `OpenAIBackend`, `BattleStore`, and schema migrations; overall coverage 85%
- Dependabot configuration for Python and npm dependencies

### Changed
- `finish_battle` + ELO update made fully atomic to prevent ELO drift on crash
- EventBus queues bounded (256 events) with drop-oldest overflow
- Frontend events list capped at 500 entries
- CORS restricted to known origins
- Pydantic `Field(ge/le)` bounds on all API inputs (422 on bad requests)

### Fixed
- Schema migration bug: `migrate()` would crash on v1 databases because an index was created before the column it referenced existed
- `AnthropicBackend` multi-block crash on extended thinking responses
- Opponent `ability` leaking through the hidden-information guard
- Heuristic bogus token annotations removed from advisory output
- `serve.py --reload` broken by relative import; fixed

---

## [0.9.0] — 2026-03-18

### Added
- **Battle Replay** — step through any completed battle turn by turn; HP timeline SVG; scrub slider; keyboard nav (← → Space Esc); auto-play
- **Win probability timeline** — team HP ratio per turn; sparkline in the analysis drawer and replay HP chart
- **Turning-point detection** — turn with the largest single-turn win-prob swing, highlighted in replay and analysis
- **Blunder flagging** — suboptimal moves where the score gap ≥ 40% of the best option; blunders panel in analysis with ⚠ badge
- **RNG inference** — possible crit / possible miss inferred from actual vs expected HP drop; badges in replay and analysis log
- **Tournament UI** — configure N players and rounds in the browser; cancel individual battles mid-run; live progress bar + final standings overlay
- **Type-themed card backgrounds** — 18-type colour map; single-type corner wash; dual-type diagonal gradient split
- **Battle animations** — hit flash, sprite shake, heal pulse, faint fade driven by HP delta tracking with `useRef`
- **Live pipeline** — all battles (UI or CLI) routed through the shared EventBus; tournament progress visible in real time

### Fixed
- Parser fix for `"switch 1"` identifier form (numeric switch actions were silently rejected)

---

## [0.8.0] — 2026-02-22

### Added
- **v2 prompt** — JSON structured output (`{"reasoning","action_type","identifier"}`); grammar-sampled on LM Studio and OpenAI for near-certain parse reliability
- `reasoning_content` fallback for Qwen 3 thinking models
- Fuzzy species name matching (`difflib`, cutoff=0.82) for switch typos
- Retry on empty LLM response; logs `finish_reason` for diagnosis
- Thinking events — amber pulsing indicator while the model reasons
- Gen 3 sprites via Showdown CDN with pixelated rendering
- Bench row — reserve Pokémon with mini-sprites + HP bars
- Model selector queries LM Studio `/v1/models` for live chips
- WebSocket keepalive pings (25 s) — eliminates reconnection churn
- CI pipeline — ruff lint + pytest + frontend build in parallel

### Changed
- Leaderboard grouped by model; aggregates across prompt versions with v1/v2 pill tags

### Fixed
- Leaderboard SQL bug: `UNION ALL` produced duplicate rows

---

## [0.7.0] — 2026-01-30

### Added
- Round-robin tournament CLI (`scripts/tournament.py`)
- Per-player model fields in the API and UI
- First live LLM battles: Ministral-3-3b vs Granite-4-h-tiny (12-0 result)

### Fixed
- Parser hardened for name-based actions and markdown-wrapped output
- Leaderboard duplicate-row bug from `UNION ALL`

---

## [0.6.0] — 2025-12-15

### Added
- Per-turn decision quality annotation: optimal / good / suboptimal / fallback
- Analysis compares chosen action against heuristic ranking
- `/api/battles/{id}/analysis` REST endpoint
- Analysis panel in the UI with quality bars and turn-by-turn breakdown

---

## [0.5.0] — 2025-11-28

### Added
- FastAPI backend with WebSocket live-battle feed (`/ws/battles`)
- REST endpoints: leaderboard, battles, turns, start-battle
- React + Vite frontend with retro CRT dark-theme battlefield visualizer
- Live Pokémon cards with animated HP bars, type badges, status, stat boosts
- Battle log, heuristic advisory drawer, winner banner

---

## [0.4.0] — 2025-11-10

### Added
- SQLite schema: battles, turns, elo_ratings, elo_history, models, prompt versions
- ELO calculation (K=32) updated after each battle
- Per-model stats, turn logging, leaderboard CLI

---

## [0.3.0] — 2025-10-25

### Added
- Type effectiveness, estimated damage %, stat stages, priority, status annotation
- Switch matchup scoring
- Heuristic scores surfaced to LLM as advisory context (not a hard filter)

---

## [0.2.0] — 2025-10-08

### Added
- Pluggable model backend: Anthropic + OpenAI cloud APIs
- Local model support via LM Studio (OpenAI-compatible API)
- Battle state serializer with hidden-information enforcement
- System prompt v1: battle state format, legal actions, `ACTION: move N` output schema
- Versioned prompts for correlating changes with ELO shifts
- `LLMPlayer` full loop: state → prompt → backend → action parser → `BattleOrder`

---

## [0.1.0] — 2025-09-20

### Added
- Repo scaffold, Python project, venv, pyproject.toml
- Local Pokémon Showdown server wired up with poke-env
- Two RandomBots complete a Gen 3 random singles battle end to end

[Unreleased]: https://github.com/haggyroth/nidozo/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/haggyroth/nidozo/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/haggyroth/nidozo/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/haggyroth/nidozo/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/haggyroth/nidozo/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/haggyroth/nidozo/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/haggyroth/nidozo/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/haggyroth/nidozo/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/haggyroth/nidozo/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/haggyroth/nidozo/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/haggyroth/nidozo/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/haggyroth/nidozo/releases/tag/v0.1.0
