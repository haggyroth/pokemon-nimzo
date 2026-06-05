# Nidozo

[![CI](https://github.com/haggyroth/nidozo/actions/workflows/ci.yml/badge.svg)](https://github.com/haggyroth/nidozo/actions/workflows/ci.yml)

An arena where two LLMs compete in Pokémon battles. The battle engine is [Pokémon Showdown](https://github.com/smogon/pokemon-showdown), accessed via [poke-env](https://github.com/hsahovic/poke-env). Models reason over legal actions each turn, pick their move, and an ELO system tracks skill over time.

Sibling project to [Nimzo](https://github.com/haggyroth/nimzo) (the LLM chess arena).

---

## Features

- **Gen 3 Random Battles** — fully rules-correct via a local Showdown server
- **Pluggable LLM backends** — Anthropic, OpenAI, or any local model via LM Studio
- **JSON structured outputs** (v2 prompt) — models respond with `{"reasoning":"…","action_type":"move","identifier":"thunderbolt"}`, grammar-sampled for 100% parse reliability
- **Heuristic advisory** — type effectiveness, estimated damage, priority, status scoring surfaced to the model as context (non-binding)
- **Hidden-information enforcement** — each model sees only what a human player would legitimately know
- **ELO rankings** — updated after every battle, persisted in SQLite
- **Post-game analysis** — per-turn decision quality annotated against heuristic rankings
- **Live visualizer** — React frontend with Gen 3 sprites, animated HP bars, thinking indicators, bench display, and a real-time battle log
- **Tournament runner** — CLI round-robin across any set of models

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 | `brew install python@3.12` or via [uv](https://docs.astral.sh/uv/) |
| Node.js | 18+ | `brew install node` |
| uv | any | `brew install uv` |

---

## Setup

### 1. Clone the repo and install Python dependencies

```bash
git clone https://github.com/haggyroth/nidozo.git
cd nidozo
uv venv --python 3.12
uv pip install -e ".[dev]"
```

### 2. Set up the local Pokémon Showdown server

The Showdown server is **not** included in this repo (it's in `.gitignore`). Clone and set it up once:

```bash
git clone https://github.com/smogon/pokemon-showdown.git showdown
cd showdown
npm install
cp config/config-example.js config/config.js
```

> **Why `--no-security`?** poke-env connects as bots with generated usernames. `--no-security` disables the login challenge so bots can connect freely to the local server.

#### Start the server

```bash
# From the repo root
./scripts/start_showdown.sh
```

You should see:
```
Worker 1 now listening on 0.0.0.0:8000
```

Leave this terminal running.

### 3. (Optional) Set up LM Studio for local models

Install [LM Studio](https://lmstudio.ai/), load a model, and start the local server on port 1234. The UI will auto-discover loaded models via the `/v1/models` endpoint.

---

## Running battles

### Live visualizer (recommended)

```bash
# Terminal 1 — Showdown server
./scripts/start_showdown.sh

# Terminal 2 — API + WebSocket server (port 5000)
uv run python scripts/serve.py

# Terminal 3 — React frontend (port 5173)
cd frontend && npm run dev
```

Open `http://localhost:5173`, select models, and click **▶ START BATTLE**. Switch to **LIVE** to watch turn by turn — the UI shows Gen 3 sprites, HP bars, a thinking indicator while the model reasons, and the full bench.

### Tournament runner (CLI)

```bash
uv run python scripts/tournament.py \
  --player lmstudio:ibm/granite-4-h-tiny \
  --player lmstudio:mistralai/ministral-3-3b \
  --rounds 3
```

Each model pair plays both sides each round. Results are persisted to `nidozo.db` and an ELO table is printed at the end.

### Single battle (CLI)

```bash
# Two random bots (no API key needed)
uv run python scripts/run_battle.py

# LLM vs random
ANTHROPIC_API_KEY=sk-... uv run python scripts/run_battle.py --p1 anthropic

# Local model via LM Studio
uv run python scripts/run_battle.py --p1 lmstudio --model "ibm/granite-4-h-tiny"
```

---

## Project structure

```
nidozo/
├── src/nidozo/
│   ├── api/            FastAPI app, EventBus, /api/lmstudio/models proxy
│   ├── analysis/       Per-turn decision quality annotator
│   ├── battle/         LLMPlayer, StreamingPlayer, ActionParser, heuristics, serializer
│   ├── db/             BattleStore (SQLite), ELO, schema migrations
│   └── llm/            ModelBackend protocol, AnthropicBackend, OpenAIBackend
│       └── prompts/
│           ├── v1/     Legacy text prompt (ACTION: move N)
│           └── v2/     JSON structured output (default)
├── frontend/           Vite + React live battlefield visualizer
├── scripts/
│   ├── serve.py        uvicorn entrypoint (port 5000)
│   ├── tournament.py   Round-robin CLI runner
│   ├── run_battle.py   Single-battle CLI
│   └── start_showdown.sh
├── tests/              123 tests, no Showdown required
└── showdown/           Cloned Showdown server (gitignored)
```

---

## Prompt versions

| Version | Format | Default |
|---------|--------|---------|
| `v2` | JSON: `{"reasoning":"…","action_type":"move","identifier":"thunderbolt"}` | ✓ |
| `v1` | Text: `ACTION: move thunderbolt` | — |

Pass `--prompt-version v1` to the tournament runner or API to use the legacy format.

---

## Troubleshooting

**`ConnectionRefusedError` when running a battle**
Showdown isn't running. Start it: `./scripts/start_showdown.sh`

**`ModuleNotFoundError: nidozo`**
Run `uv pip install --reinstall-package nidozo -e ".[dev]"` to regenerate the editable install `.pth` file.

**Models returning empty responses**
Check LM Studio is running and the model is loaded. The server retries once automatically and logs the `finish_reason` on failure.

**Showdown `EADDRINUSE 8000`**
A previous Showdown process is still running. Kill it: `pkill -f pokemon-showdown`

**Node version issues**
Showdown works with Node 18–22. Check with `node --version`.

---

## See also

- [ROADMAP.md](ROADMAP.md) — planned features
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [poke-env docs](https://poke-env.readthedocs.io/)
- [Pokémon Showdown source](https://github.com/smogon/pokemon-showdown)
