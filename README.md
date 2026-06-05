# Pokémon Nimzo

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
git clone https://github.com/haggyroth/pokemon-nimzo.git
cd pokemon-nimzo
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
uv run python scripts/run_battle.py
```

This starts two `RandomBot` players, runs one Gen 3 random singles battle, and prints the result:

```
Starting battle: RandomBot 1 vs RandomBot 2
  RandomBot 1: 1W / 0L / 0T  (finished: 1)
  RandomBot 2: 0W / 1L / 0T  (finished: 1)

Winner: RandomBot 1
```

---

## Project structure

```
pokemon-nimzo/
├── src/pokemon_nimzo/
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
