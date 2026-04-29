"""Bilingual message catalog and CLI locale renderer for Zentex."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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


def available_locales() -> list[str]:
    """Return all supported locale identifiers."""

    return sorted(CATALOG)


def normalize_locale(locale: str | None) -> str:
    """Normalize a locale alias to a supported catalog locale."""

    raw = str(locale or "zh-CN").strip()
    normalized = LOCALE_ALIASES.get(raw.lower(), raw)
    if normalized not in CATALOG:
        raise I18nLocaleError(f"Unsupported locale: {raw}")
    return normalized


def translate(message_key: str, *, locale: str | None = "zh-CN", params: Mapping[str, object] | None = None) -> LocaleTranslation:
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
    parser.add_argument("--locale", default="zh-CN")
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
