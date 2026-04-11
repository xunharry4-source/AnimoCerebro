from __future__ import annotations


class InitializationError(RuntimeError):
    """Raised when the web console cannot be started safely."""


class ConfigError(InitializationError):
    """Raised when startup configuration is missing or invalid."""
