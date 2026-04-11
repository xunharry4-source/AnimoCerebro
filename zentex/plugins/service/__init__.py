"""
Canonical public entrypoint for plugin access in Zentex.

External callers must import plugin governance APIs from this package:
    from zentex.plugins.service import SystemPluginService
"""

from __future__ import annotations

from typing import Any

from .manager import SystemPluginService, PluginGovernanceService
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.weights import WeightPluginAssembler, RationalAuditRejectError
from zentex.plugins.provider_tools import (
    AuthError,
    BaseProviderTool,
    ConfigError,
    OpenAICompatibleGatewayTool,
    RateLimitError,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    ToolInvocationResponse,
    build_default_provider_tools,
    is_env_var_reference,
)

def get_default_provider_key() -> str:
    """
    Get the default LLM provider key from environment or config.
    
    Returns:
        Provider key string (e.g., 'openai', 'anthropic', etc.)
    """
    from zentex.plugins.provider_tools import get_default_provider_key as _get_key
    return _get_key()


def _normalize_status(status: object) -> str:
    return str(getattr(status, "value", status) or "").strip().lower()


def _normalize_layer(layer: object) -> str:
    return str(getattr(layer, "value", layer) or "").strip().lower()


def _normalize_category(record_or_plugin: object) -> str:
    if isinstance(record_or_plugin, dict):
        category = str(record_or_plugin.get("category", "") or "").strip().lower()
        if category:
            return category
        layer = _normalize_layer(record_or_plugin.get("plugin_layer", None))
        if layer == "cognitive":
            return "cognitive"
        if layer == "functional":
            return "functional"
        plugin_kind = str(record_or_plugin.get("plugin_kind", "") or "").strip().lower()
        if plugin_kind == "cognitive_tool":
            return "cognitive"
        if plugin_kind:
            return "functional"
        return ""

    category = str(getattr(record_or_plugin, "category", "") or "").strip().lower()
    if category:
        return category
    layer = _normalize_layer(getattr(record_or_plugin, "plugin_layer", None))
    if layer == "cognitive":
        return "cognitive"
    if layer == "functional":
        return "functional"
    plugin_kind = ""
    plugin_kind_attr = getattr(record_or_plugin, "plugin_kind", None)
    if callable(plugin_kind_attr):
        try:
            plugin_kind = str(plugin_kind_attr() or "").strip().lower()
        except Exception:
            plugin_kind = ""
    if plugin_kind == "cognitive_tool":
        return "cognitive"
    if plugin_kind:
        return "functional"
    return ""


def _is_callable_plugin_status(status: object, *, is_instantiated: bool) -> bool:
    normalized = _normalize_status(status)
    if normalized == PluginLifecycleStatus.ACTIVE.value:
        return True
    if normalized in {PluginLifecycleStatus.REVOKED.value, PluginLifecycleStatus.DEGRADED.value}:
        return False
    # Runtime-instantiated plugins in transitional/legacy states are considered callable.
    return is_instantiated and normalized in {"", "unknown", PluginLifecycleStatus.CANDIDATE.value, PluginLifecycleStatus.SANDBOX_VERIFIED.value}


def _collect_active_plugins_from_instances(
    plugin_service: SystemPluginService,
    *,
    target_category: str,
) -> list[dict[str, Any]]:
    if not hasattr(plugin_service, "list_plugin_instances"):
        return []

    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    try:
        instances = plugin_service.list_plugin_instances()
    except Exception:
        instances = []

    for plugin in instances:
        plugin_id = str(getattr(plugin, "plugin_id", "") or "").strip()
        if not plugin_id or plugin_id in seen_ids:
            continue
        if not _is_callable_plugin_status(getattr(plugin, "status", ""), is_instantiated=True):
            continue
        if _normalize_category(plugin) != target_category:
            continue
        seen_ids.add(plugin_id)
        collected.append(
            {
                "plugin_id": plugin_id,
                "category": target_category,
                "version": str(getattr(plugin, "version", "") or ""),
                "status": PluginLifecycleStatus.ACTIVE.value,
                "behavior_key": str(getattr(plugin, "behavior_key", "") or ""),
                "feature_code": str(getattr(plugin, "feature_code", "") or plugin_id),
                "is_instantiated": True,
            }
        )
    return collected


def _get_active_plugins_by_category(
    plugin_service: SystemPluginService,
    *,
    category: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        raw = plugin_service.query_by_category(category)
        if isinstance(raw, list):
            filtered: list[dict[str, Any]] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                if _normalize_category(item) != category:
                    continue
                if _is_callable_plugin_status(item.get("status", ""), is_instantiated=bool(item.get("is_instantiated", False))):
                    filtered.append(item)
            results = filtered
    except Exception:
        results = []

    by_id: dict[str, dict[str, Any]] = {
        str(item.get("plugin_id") or "").strip(): item
        for item in results
        if str(item.get("plugin_id") or "").strip()
    }
    for item in _collect_active_plugins_from_instances(plugin_service, target_category=category):
        plugin_id = str(item.get("plugin_id") or "").strip()
        if plugin_id and plugin_id not in by_id:
            by_id[plugin_id] = item
    return list(by_id.values())


def get_active_functional_plugins(plugin_service: SystemPluginService) -> list[dict[str, Any]]:
    """Return active functional plugin records from the public plugin service."""
    return _get_active_plugins_by_category(plugin_service, category="functional")


def get_active_cognitive_plugins(plugin_service: SystemPluginService) -> list[dict[str, Any]]:
    """Return active cognitive plugin records from the public plugin service."""
    return _get_active_plugins_by_category(plugin_service, category="cognitive")

__all__ = [
    "SystemPluginService",
    "PluginGovernanceService",
    "WeightPluginAssembler",
    "RationalAuditRejectError",
    "AuthError",
    "BaseProviderTool",
    "ConfigError",
    "OpenAICompatibleGatewayTool",
    "RateLimitError",
    "RemoteServiceError",
    "RemoteTimeoutError",
    "ResponseParseError",
    "ToolInvocationRequest",
    "ToolInvocationResponse",
    "build_default_provider_tools",
    "is_env_var_reference",
    "get_default_provider_key",
    "get_active_functional_plugins",
    "get_active_cognitive_plugins",
]
