"""
Start the Pokémon Nimzo API server.

Requires the local Showdown server to be running:
    ./scripts/start_showdown.sh

Usage:
    uv run python scripts/serve.py
    uv run python scripts/serve.py --port 8080 --db path/to/nimzo.db
"""

import argparse
import os
from pathlib import Path

import uvicorn

from nidozo.api.app import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the Nimzo API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--db", default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else Path(os.environ.get("NIMZO_DB", "nimzo.db"))
    app = create_app(db_path=db_path)

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
