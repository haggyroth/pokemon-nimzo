"""
Start the Nidozo API server.

Requires the local Showdown server to be running:
    ./scripts/start_showdown.sh

Usage:
    uv run python scripts/serve.py
    uv run python scripts/serve.py --port 8080 --db path/to/nidozo.db
"""

import argparse
import os
from pathlib import Path

import uvicorn

from nidozo.api.app import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the Nidozo API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--db", default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    # NIDOZO_DB preferred; NIMZO_DB accepted for backward compat
    db_env = os.environ.get("NIDOZO_DB") or os.environ.get("NIMZO_DB", "nidozo.db")
    db_path = Path(args.db) if args.db else Path(db_env)
    app = create_app(db_path=db_path)

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
