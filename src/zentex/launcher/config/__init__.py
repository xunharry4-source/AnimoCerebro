from __future__ import annotations
"""Public config entrypoint for zentex.launcher.

This package owns startup-time configuration loading and validation.
Migration note: legacy `zentex.core.config` now bridges into this module.
"""


from pathlib import Path
from typing import Any, Union

import yaml

from zentex.launcher.config.startup_config import (
    DatabaseConfig,
    KernelConfig,
    LLMConfig,
    PluginConfig,
    StartupConfig,
    WebConfig,
)
from zentex.launcher.config.env_reader import EnvReader
from zentex.launcher.config.config_validator import ConfigValidator, ValidationResult

CONFIG_DIR = Path("config")


class ConfigLoadError(RuntimeError):
    """Raised when launcher-owned configuration cannot be loaded safely."""


def load_yaml_config(config_path: Union[str, Path]) -> dict[str, Any]:
    """Load a YAML mapping from disk using the launcher config boundary."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigLoadError(f"Configuration file not found: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigLoadError(f"Failed to load configuration file: {path}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        print(f"DEBUG: Config load failed for {path}. Type: {type(payload)}. Payload: {payload}")
        raise ConfigLoadError(f"Configuration root must be a mapping: {path}")
    return payload


def load_required_mapping_section(config_path: Union[str, Path], section: str) -> dict[str, Any]:
    """Return a required mapping section from a launcher-managed config file."""
    payload = load_yaml_config(config_path)
    value = payload.get(section)
    if not isinstance(value, dict):
        raise ConfigLoadError(f"Required mapping section '{section}' missing in {config_path}")
    return value

__all__ = [
    "StartupConfig",
    "DatabaseConfig",
    "LLMConfig",
    "KernelConfig",
    "WebConfig",
    "PluginConfig",
    "EnvReader",
    "ConfigValidator",
    "ValidationResult",
    "CONFIG_DIR",
    "ConfigLoadError",
    "load_yaml_config",
    "load_required_mapping_section",
]
