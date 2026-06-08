"""Middleware configuration for the Nidozo FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Origins allowed to make cross-origin requests to the API.
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5001",  # serve.py production default
]


def add_cors(app: FastAPI) -> None:
    """Attach CORS middleware to *app*."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
