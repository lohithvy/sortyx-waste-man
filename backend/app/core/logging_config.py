"""
Sortyx 2.0 — Structured JSON logging configuration.

Provides a ``get_logger(name)`` factory that returns loggers pre-configured
with structured JSON output for production and a readable console format for
local development.  Secrets are **never** logged.
"""

from __future__ import annotations

import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Custom JSON formatter
# ---------------------------------------------------------------------------


class StructuredJSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON object on one line."""

    SENSITIVE_KEYS = frozenset({
        "api_key", "secret_key", "api_secret", "password", "token",
        "authorization", "cookie", "gemini_api_key", "supabase_secret_key",
        "device_api_secret",
    })

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach extra fields if present, scrubbing secrets
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            sanitised = {
                k: "***REDACTED***" if k.lower() in self.SENSITIVE_KEYS else v
                for k, v in record.extra_data.items()
            }
            log_entry["data"] = sanitised

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ReadableConsoleFormatter(logging.Formatter):
    """Human-friendly coloured output for local development."""

    COLOURS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, self.RESET)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        base = (
            f"{colour}[{ts}] {record.levelname:<8}{self.RESET} "
            f"{record.name}: {record.getMessage()}"
        )
        if record.exc_info and record.exc_info[1] is not None:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

_LOGGING_INITIALISED = False


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Initialise the root logger with console (and optionally JSON) output.

    Parameters
    ----------
    level:
        Python log level name (e.g. ``"DEBUG"``, ``"INFO"``).
    json_output:
        When ``True``, console output uses JSON format; otherwise uses
        the human-readable coloured formatter.
    """
    global _LOGGING_INITIALISED
    if _LOGGING_INITIALISED:
        return
    _LOGGING_INITIALISED = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any pre-existing handlers
    root.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    if json_output:
        console.setFormatter(StructuredJSONFormatter())
    else:
        console.setFormatter(ReadableConsoleFormatter())
    root.addHandler(console)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "websockets", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    If ``setup_logging`` has not been called yet, it is initialised with
    defaults so callers always get a usable logger.

    Parameters
    ----------
    name:
        Dotted logger name, typically ``__name__`` of the calling module.
    """
    if not _LOGGING_INITIALISED:
        setup_logging()
    return logging.getLogger(name)
