"""
Start the Nidozo API server.

Requires the local Showdown server to be running:
    ./scripts/start_showdown.sh

Usage:
    uv run python scripts/serve.py
    uv run python scripts/serve.py --port 8080 --db path/to/nidozo.db
    uv run python scripts/serve.py --reload   # dev hot-reload (uses NIDOZO_DB env var)

Notes:
    --reload uses uvicorn's import-string mode.  The --db flag is ignored when
    --reload is active; set NIDOZO_DB in your environment instead.
    create_app() is called as a factory so each reload picks up code changes.
"""

import argparse
import os
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the Nidozo API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--db", default=None)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Hot-reload on code changes (dev only). Uses NIDOZO_DB env var; --db is ignored.",
    )
    args = parser.parse_args()

    # NIDOZO_DB preferred; NIMZO_DB accepted for backward compat
    db_env = os.environ.get("NIDOZO_DB") or os.environ.get("NIMZO_DB", "nidozo.db")
    db_path = Path(args.db) if args.db else Path(db_env)

    if args.reload:
        # uvicorn reload requires an import string (not an app instance).
        # Propagate the resolved DB path via env var so create_app() picks it up.
        if args.db:
            import warnings
            warnings.warn(
                "--db is ignored in --reload mode; set NIDOZO_DB env var instead.",
                stacklevel=1,
            )
        os.environ.setdefault("NIDOZO_DB", str(db_path))
        uvicorn.run(
            "nidozo.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
        )
    else:
        from nidozo.api.app import create_app
        app = create_app(db_path=db_path)
        uvicorn.run(app, host=args.host, port=args.port)
