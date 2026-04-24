from __future__ import annotations
"""Startup marker logging utilities.

Purpose
  - Provide a minimal, low-noise console marker when key subsystems are first
    invoked (LLM, nine-questions, reflection, tasks, learning, plugins).

Design
  - Default enabled; can be disabled via env.
  - "Once" semantics to avoid log spam.
  - Safe console logging bootstrap that only applies if the root logger has
    no handlers (so we don't fight uvicorn/logging configs).
"""


import logging
import os
import threading
from typing import Any


_LOCK = threading.Lock()
_SEEN: set[str] = set()


def _truthy_env(key: str, default: str) -> bool:
    raw = str(os.getenv(key, default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def startup_markers_enabled() -> bool:
    """Return True if startup marker logging is enabled."""
    raw = str(os.getenv("ZENTEX_STARTUP_MARKERS", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def startup_markers_verbose() -> bool:
    """If True, marker logs may be emitted on every call."""
    return _truthy_env("ZENTEX_STARTUP_MARKERS_VERBOSE", "0")


def ensure_console_logging_configured() -> None:
    """Ensure basic console logging exists if nothing configured it yet.

    This intentionally avoids overriding existing logging configurations.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    level_raw = str(os.getenv("ZENTEX_LOG_LEVEL", "INFO")).strip().upper()
    level = getattr(logging, level_raw, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    text = str(value)
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) > 240:
        text = text[:240] + "…"
    return text


def log_once(event: str, **fields: Any) -> None:
    """Log a one-time startup marker for *event*.

    Controlled by:
      - ZENTEX_STARTUP_MARKERS (default: 1)
      - ZENTEX_STARTUP_MARKERS_VERBOSE (default: 0)
    """
    if not startup_markers_enabled():
        return

    key = "" if startup_markers_verbose() else str(event)
    if key:
        with _LOCK:
            if key in _SEEN:
                return
            _SEEN.add(key)

    logger = logging.getLogger("zentex.startup")
    parts: list[str] = ["[STARTUP]", f"event={event}"]
    for k, v in fields.items():
        fv = _format_value(v)
        if fv:
            parts.append(f"{k}={fv}")
    logger.info(" ".join(parts))
