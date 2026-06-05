#!/usr/bin/env bash
# Start the local Pokémon Showdown server.
# Run this in a separate terminal before any battle scripts.
# Requires `showdown/` to be cloned and `npm install` run inside it.
# See README.md for full setup steps.
set -euo pipefail

SHOWDOWN_DIR="$(dirname "$0")/../showdown"

if [ ! -d "$SHOWDOWN_DIR" ]; then
  echo "Error: showdown/ directory not found."
  echo "Clone it first: git clone https://github.com/smogon/pokemon-showdown.git showdown"
  exit 1
fi

echo "Starting Pokémon Showdown on port 8000..."
node "$SHOWDOWN_DIR/pokemon-showdown" start --no-security
