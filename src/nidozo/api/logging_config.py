"""Structured JSON logging configuration for Nidozo.

Call configure_logging() once at process startup (in serve.py).  All loggers
in the nidozo package — and uvicorn's access/error loggers — will emit
newline-delimited JSON records instead of the default human-readable format.

Example output (one record, pretty-printed for readability):
    {
        "ts":      "2026-06-06T15:42:01.123456Z",
        "level":   "INFO",
        "logger":  "nidozo.api.app",
        "message": "Battle 7 finished — winner=1 turns=34"
    }
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":      datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Wire up JSON logging for nidozo and uvicorn loggers.

    Safe to call multiple times — only takes effect on the first call.

    Args:
        level: Log level string ("DEBUG", "INFO", "WARNING", "ERROR").
               Defaults to "INFO".
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return
    _CONFIGURED = True

    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    # Root logger — catches everything not claimed by a specific logger
    root = logging.getLogger()
    root.setLevel(numeric)
    root.handlers.clear()
    root.addHandler(handler)

    # Uvicorn splits its output across three loggers; align them all
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True  # let root handler emit them
