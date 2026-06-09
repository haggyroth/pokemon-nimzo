#!/usr/bin/env bash
# Kill any hanging Nidozo API or Pokémon Showdown processes.
#
# Use this when a previous run didn't exit cleanly and the next
# start fails with EADDRINUSE or a stale poke-env connection.
#
# Usage:
#   ./scripts/stop.sh            # kill both servers
#   ./scripts/stop.sh --api      # kill only the Python API (port 5001)
#   ./scripts/stop.sh --showdown # kill only the Showdown server (port 8000)

set -euo pipefail

kill_port() {
  local port="$1"
  local label="$2"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Stopping $label (port $port, PID $pids)..."
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    # Give it a moment; escalate to SIGKILL if still alive.
    sleep 1
    remaining=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [ -n "$remaining" ]; then
      echo "$remaining" | xargs kill -KILL 2>/dev/null || true
      echo "  Force-killed $label."
    else
      echo "  $label stopped."
    fi
  else
    echo "$label not running on port $port."
  fi
}

do_api=true
do_showdown=true

for arg in "$@"; do
  case "$arg" in
    --api)      do_showdown=false ;;
    --showdown) do_api=false ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

$do_api      && kill_port 5001 "Nidozo API"
$do_showdown && kill_port 8000 "Pokémon Showdown"
