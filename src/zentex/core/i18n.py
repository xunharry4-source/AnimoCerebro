"""Bilingual message catalog and CLI locale renderer for Zentex."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Mapping, Sequence


class I18nLocaleError(ValueError):
    """Raised when a locale is unsupported."""


class I18nCatalogError(KeyError):
    """Raised when a message key or interpolation value is missing."""


CATALOG: dict[str, dict[str, str]] = {
    "zh-CN": {
        "system.health": "系统健康：{status}",
        "reasoning.output": "推理输出语言：中文",
        "notification.sent": "通知已发送：{event_id}",
        "llm.fail_closed": "大模型不可用，已按 fail-closed 阻断",
    },
    "en-US": {
        "system.health": "System health: {status}",
        "reasoning.output": "Reasoning output language: English",
        "notification.sent": "Notification sent: {event_id}",
        "llm.fail_closed": "LLM unavailable; fail-closed block applied",
    },
}

DEFAULT_LOCALE = "zh-CN"
_CONFIG_PATH = Path("config/i18n.toml")

LOCALE_ALIASES: dict[str, str] = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "cn": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
}


@dataclass(frozen=True)
class LocaleTranslation:
    """Resolved translation result returned to APIs and CLI callers."""

    locale: str
    message_key: str
    message: str


def _load_i18n_config() -> dict[str, object]:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open("rb") as handle:
        payload = tomllib.load(handle)
    raw_config = payload.get("i18n", {})
    if not isinstance(raw_config, dict):
        raise I18nLocaleError("config/i18n.toml [i18n] must be a table")
    return raw_config


def available_locales() -> list[str]:
    """Return all supported locale identifiers."""

    raw_supported = _load_i18n_config().get("supported_languages")
    if raw_supported is None:
        return list(CATALOG)
    if not isinstance(raw_supported, list):
        raise I18nLocaleError("config/i18n.toml i18n.supported_languages must be a list")

    resolved: list[str] = []
    for raw_locale in raw_supported:
        locale = _normalize_locale_value(str(raw_locale))
        if locale not in CATALOG:
            raise I18nLocaleError(f"Unsupported locale in config/i18n.toml: {raw_locale}")
        if locale not in resolved:
            resolved.append(locale)
    if not resolved:
        raise I18nLocaleError("config/i18n.toml i18n.supported_languages must not be empty")
    return resolved


def default_locale() -> str:
    """Return configured default locale, defaulting to Chinese."""

    raw_locale = _load_i18n_config().get("language", DEFAULT_LOCALE)
    locale = _normalize_locale_value(str(raw_locale))
    if locale not in available_locales():
        raise I18nLocaleError(
            f"Configured i18n language must be one of {available_locales()}: {raw_locale}"
        )
    return locale


def _normalize_locale_value(locale: str | None) -> str:
    raw = str(locale or DEFAULT_LOCALE).strip()
    return LOCALE_ALIASES.get(raw.lower(), raw)


def normalize_locale(locale: str | None) -> str:
    """Normalize a locale alias to a supported catalog locale."""

    raw = str(locale or default_locale()).strip()
    normalized = _normalize_locale_value(raw)
    if normalized not in available_locales():
        raise I18nLocaleError(f"Unsupported locale: {raw}")
    return normalized


def translate(message_key: str, *, locale: str | None = None, params: Mapping[str, object] | None = None) -> LocaleTranslation:
    """Translate a message key with strict parameter interpolation."""

    resolved_locale = normalize_locale(locale)
    messages = CATALOG[resolved_locale]
    if message_key not in messages:
        raise I18nCatalogError(f"Missing i18n message key: {message_key}")
    try:
        message = messages[message_key].format(**dict(params or {}))
    except KeyError as exc:
        raise I18nCatalogError(f"Missing i18n parameter: {exc.args[0]}") from exc
    return LocaleTranslation(locale=resolved_locale, message_key=message_key, message=message)


def render_cli_translation(argv: Sequence[str]) -> LocaleTranslation:
    """Render a translation from CLI-style arguments including ``--locale``."""

    parser = argparse.ArgumentParser(prog="zentex-i18n")
    parser.add_argument("--locale", default=None)
    parser.add_argument("--key", required=True)
    parser.add_argument("--param", action="append", default=[])
    namespace = parser.parse_args(list(argv))
    params: dict[str, object] = {}
    for item in namespace.param:
        if "=" not in item:
            raise I18nCatalogError(f"Invalid --param value: {item}")
        key, value = item.split("=", 1)
        params[key] = value
    return translate(namespace.key, locale=namespace.locale, params=params)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point used by developer tooling."""

    result = render_cli_translation(list(argv or []))
    print(result.message)
    return 0
