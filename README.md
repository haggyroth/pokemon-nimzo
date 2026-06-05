# Nidozo

An arena where two LLMs compete in Pokémon battles. The battle engine is [Pokémon Showdown](https://github.com/smogon/pokemon-showdown), accessed via [poke-env](https://github.com/hsahovic/poke-env). Models reason over legal actions each turn and pick their move; an ELO system tracks skill over time.

Sibling project to [Nimzo](https://github.com/haggyroth/nimzo) (the LLM chess arena).

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
# From the repo root
git clone https://github.com/smogon/pokemon-showdown.git showdown
cd showdown
npm install
cp config/config-example.js config/config.js
```

> **Why `--no-security`?** poke-env connects as bots with usernames like `RandomPlayer 1`. The `--no-security` flag disables the login challenge that would normally require a valid Pokémon Showdown account, so bots can connect freely to the local server.

#### Start the server

```bash
# Option A: use the helper script (from repo root)
./scripts/start_showdown.sh

# Option B: run directly
node showdown/pokemon-showdown start --no-security
```

You should see output ending with:
```
Worker 1 now listening on 0.0.0.0:8000
Test your server at http://localhost:8000
```

Leave this terminal running while you play battles.

### 3. Verify the server is reachable

```bash
curl -s http://localhost:8000 | head -5
```

You should get an HTML response from the Showdown lobby.

---

## Running a battle

With the Showdown server running in a separate terminal:

```bash
# Two random bots (no API key needed)
uv run python scripts/run_battle.py

# LLM (Claude) vs random bot
ANTHROPIC_API_KEY=sk-... uv run python scripts/run_battle.py --p1 anthropic

# LLM vs LLM
ANTHROPIC_API_KEY=sk-... uv run python scripts/run_battle.py --p1 anthropic --p2 anthropic

# Local model via LM Studio vs random bot
uv run python scripts/run_battle.py --p1 lmstudio --model "mistral-7b"
```

Example output (random vs random):

```
Starting battle: RandomBot 1 (random) vs RandomBot 2 (random)
  RandomBot 1 [random]: 0W / 1L / 0T
  RandomBot 2 [random]: 1W / 0L / 0T
  Winner: RandomBot 2 (random)  |  Turns: 62

Results saved to nimzo.db
Run `uv run python scripts/leaderboard.py` to see rankings.
```

## Live visualizer

Run the full stack to watch battles in real time:

```bash
# Terminal 1 — Showdown server
./scripts/start_showdown.sh

# Terminal 2 — API server (port 5000)
uv run python scripts/serve.py

# Terminal 3 — React frontend (port 5173)
cd frontend && npm run dev
```

Open `http://localhost:5173`, pick providers, click **▶ START BATTLE**, then switch to **LIVE** to watch.

For a production build (served by FastAPI directly):
```bash
cd frontend && npm run build
uv run python scripts/serve.py   # now serves frontend/dist/ at /
```

## CLI leaderboard

After running battles, view ELO rankings:

```bash
uv run python scripts/leaderboard.py

=== LEADERBOARD ===

#    Model                                    Prompt       ELO  Games     W     L     T
---------------------------------------------------------------------------------------
1    anthropic/claude-sonnet-4-6              v1        1048.2      5     3     2     0
2    random/random                            v1         951.8      5     2     3     0
```

---

## Project structure

```
nidozo/
├── src/nidozo/
│   └── battle/
│       └── bots.py          # RandomBot (baseline) — LLM bots added in v0.2
├── scripts/
│   └── run_battle.py        # Run a local battle end to end
├── tests/
├── showdown/                # Cloned Showdown server (gitignored)
├── pyproject.toml
└── ROADMAP.md
```

---

## Troubleshooting

**`ConnectionRefusedError` when running a battle**
Showdown isn't running. Start it with `node showdown/pokemon-showdown start --no-security`.

**`ModuleNotFoundError: poke_env`**
You're not in the venv. Run `source .venv/bin/activate` or use `uv run python ...`.

**Node version issues**
poke-env's websocket handshake is sensitive to Showdown server state. Showdown works well with Node 18–22. Check with `node --version`; use `nvm` or `brew install node@22` if needed.

**Battle hangs and never finishes**
The bots connected but no battle started. Check that both bots are using `gen3randombattle` format and that the Showdown server console shows incoming connections.

---

## See also

- [ROADMAP.md](ROADMAP.md) — planned features
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [poke-env docs](https://poke-env.readthedocs.io/)
- [Pokémon Showdown source](https://github.com/smogon/pokemon-showdown)
