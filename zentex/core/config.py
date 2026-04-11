from __future__ import annotations

"""
Shared configuration loading utilities for Zentex.

This module centralizes filesystem-based config loading so runtime modules do
not each reimplement their own YAML parsing and error handling.
"""

from pathlib import Path
from typing import Any, Dict

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"


class ConfigLoadError(RuntimeError):
    """Raised when a configuration file or required section cannot be loaded."""


def load_yaml_config(path: str | Path) -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigLoadError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ConfigLoadError(
            f"Configuration file must contain a top-level mapping: {config_path}"
        )
    return payload


def load_required_mapping_section(
    path: str | Path,
    section_name: str,
) -> Dict[str, Any]:
    payload = load_yaml_config(path)
    section = payload.get(section_name)
    if not isinstance(section, dict):
        raise ConfigLoadError(
            f"Configuration file must contain mapping section '{section_name}': {path}"
        )
    return section
