"""
Config loading, env resolution, and API key helpers shared by all providers.
"""
from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

from .base import (
    ConfigError,
    DEFAULT_PROVIDER_CONFIG_PATH,
    DEFAULT_DOTENV_PATH,
    ProviderToolConfig,
)


def is_env_var_reference(value: Optional[str]) -> bool:
    """Return True if *value* looks like a bare env-var name (e.g. ``OPENAI_API_KEY``)."""
    candidate = str(value or "").strip()
    if not candidate:
        return False
    return (
        candidate.replace("_", "").isalnum()
        and candidate.upper() == candidate
        and "-" not in candidate
    )


def is_placeholder_secret(value: Optional[str]) -> bool:
    """Return True if *value* is a well-known placeholder that should be ignored."""
    candidate = str(value or "").strip().lower()
    if not candidate:
        return True
    known_placeholders = {
        "your-openai-key-here",
        "your-claude-key-here",
        "replace-me",
        "changeme",
    }
    return candidate in known_placeholders


@functools.lru_cache(maxsize=1)
def load_project_dotenv(
    dotenv_path: Union[str, os.PathLike[str], None] = None,
) -> Dict[str, str]:
    path = Path(dotenv_path) if dotenv_path is not None else DEFAULT_DOTENV_PATH
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_env_value(name: str) -> Optional[str]:
    key = str(name or "").strip()
    if not key:
        return None

    value = os.getenv(key)
    if value and not is_placeholder_secret(value):
        return value

    dotenv_values = load_project_dotenv()
    if key in dotenv_values and dotenv_values[key] and not is_placeholder_secret(dotenv_values[key]):
        return dotenv_values[key]

    # Gemini setups often use GOOGLE_API_KEY while config names GEMINI_API_KEY.
    aliases: Dict[str, tuple[str, ...]] = {
        "GEMINI_API_KEY": ("GOOGLE_API_KEY",),
    }
    for alias in aliases.get(key, ()):
        alias_value = os.getenv(alias) or dotenv_values.get(alias)
        if alias_value and not is_placeholder_secret(alias_value):
            return alias_value
    return None


def resolve_provider_api_key(config: ProviderToolConfig) -> str:
    env_name = str(config.api_key_env or "").strip()
    env_value = resolve_env_value(env_name) if env_name else None
    if env_value:
        return env_value
    if env_name and not is_env_var_reference(env_name):
        return env_name
    raise ConfigError(
        f"Missing API key for tool provider {config.provider_name}: {config.api_key_env}"
    )


@functools.lru_cache(maxsize=1)
def load_provider_tool_configs(
    config_path: Union[str, os.PathLike[str]] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> Dict[str, ProviderToolConfig]:
    from zentex.launcher.config import load_required_mapping_section

    try:
        providers = load_required_mapping_section(config_path, "providers")
    except Exception as exc:
        raise ConfigError(str(exc)) from exc

    configs: Dict[str, ProviderToolConfig] = {}
    for provider_key, provider_payload in providers.items():
        if not isinstance(provider_payload, dict):
            raise ConfigError(f"Provider entry must be a mapping: {provider_key}")
        configs[str(provider_key)] = ProviderToolConfig.model_validate(provider_payload)
    return configs


def get_default_provider_key(
    config_path: Union[str, Path] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> str:
    """Resolve default provider key.

    Precedence:
    1. ``ZENTEX_DEFAULT_PROVIDER`` env var
    2. ``default_provider`` key in ``config/provider_tools.yml``
    3. ``openai`` if ``OPENAI_API_KEY`` is set, else ``openai_compat``
    """
    env_default = resolve_env_value("ZENTEX_DEFAULT_PROVIDER")
    if env_default and env_default.strip():
        return env_default.strip()

    try:
        from zentex.launcher.config import load_yaml_config
        payload = load_yaml_config(config_path)
        config_default = payload.get("default_provider")
        if config_default and isinstance(config_default, str) and config_default.strip():
            return config_default.strip()
    except Exception:
        logger.exception("Failed to load default provider from config path %s", config_path)

    return "openai" if resolve_env_value("OPENAI_API_KEY") else "openai_compat"


@functools.lru_cache(maxsize=1)
def get_maintenance_llm_config(
    config_path: Union[str, Path] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> Dict[str, Any]:
    """Return the optional maintenance LLM config block from provider_tools.yml."""
    try:
        from zentex.launcher.config import load_yaml_config

        payload = load_yaml_config(config_path)
        block = payload.get("maintenance")
        return dict(block) if isinstance(block, dict) else {}
    except Exception:
        logger.warning(
            "get_maintenance_llm_config: failed to read config; using provider defaults",
            exc_info=True,
        )
        return {}
