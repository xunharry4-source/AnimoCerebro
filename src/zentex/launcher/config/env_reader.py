"""
EnvReader — reads environment variables and populates a StartupConfig.

Each env var overrides a specific field; fields not found in the environment
retain their dataclass defaults.
"""

from __future__ import annotations

import os

from zentex.launcher.config.startup_config import StartupConfig


class EnvReader:
    """Reads process environment variables into a StartupConfig instance."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> StartupConfig:
        """Build a StartupConfig from defaults, then override from env vars."""
        config = StartupConfig()

        # top-level
        env = self._get("ZENTEX_ENV")
        if env is not None:
            config.environment = env

        # database
        db_dir = self._get("ZENTEX_DB_DIR")
        if db_dir is not None:
            config.database.sqlite_dir = db_dir

        transcript_dir = self._get("ZENTEX_TRANSCRIPT_DIR")
        if transcript_dir is not None:
            config.database.transcript_dir = transcript_dir

        # web
        web_host = self._get("ZENTEX_WEB_HOST")
        if web_host is not None:
            config.web.host = web_host

        config.web.port = self._get_int("ZENTEX_WEB_PORT", config.web.port)
        config.web.debug = self._get_bool("ZENTEX_WEB_DEBUG", config.web.debug)

        # llm
        llm_provider = self._get("ZENTEX_LLM_PROVIDER")
        if llm_provider is not None:
            config.llm.provider = llm_provider

        llm_model = self._get("ZENTEX_LLM_MODEL")
        if llm_model is not None:
            config.llm.default_model = llm_model

        config.llm.timeout_seconds = self._get_int(
            "ZENTEX_LLM_TIMEOUT", config.llm.timeout_seconds
        )

        # kernel
        config.kernel.session_timeout_seconds = self._get_int(
            "ZENTEX_SESSION_TIMEOUT", config.kernel.session_timeout_seconds
        )
        config.kernel.working_memory_slots = self._get_int(
            "ZENTEX_WORKING_MEMORY_SLOTS", config.kernel.working_memory_slots
        )

        return config

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, key: str, default: str | None = None) -> str | None:
        """Return the value of an env var, or *default* if not set."""
        return os.environ.get(key, default)

    def _get_int(self, key: str, default: int) -> int:
        """Return an env var parsed as int, falling back to *default* on any error."""
        raw = os.environ.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default

    def _get_bool(self, key: str, default: bool) -> bool:
        """Return an env var parsed as bool.

        Truthy strings: "true", "1", "yes" (case-insensitive).
        Everything else is treated as False; missing key returns *default*.
        """
        raw = os.environ.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"true", "1", "yes"}
