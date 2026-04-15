from __future__ import annotations
import itertools
from datetime import datetime, timezone
from typing import Any, Callable
from zentex.plugins.contracts import PluginLifecycleStatus, ManagedPluginRecord

# Counter for tracking in-memory record revisions during a single runtime session
_MANAGED_PLUGIN_INTERNAL_REVISION = itertools.count(1)

def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to get a value from an object (attribute) or a dictionary (key)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _lifecycle_value(plugin: Any) -> str:
    """Extract lifecycle status string from a plugin object or row."""
    val = _get_val(plugin, "lifecycle_status")
    if val is None:
        val = _get_val(plugin, "status", "unknown")
    return str(getattr(val, "value", val) or "unknown")

def _operational_status(plugin: Any) -> str:
    """Alias for _operational_value — extract operational status string."""
    return _operational_value(plugin)


def _operational_value(plugin: Any) -> str:
    """Extract operational status string (enabled, stopped, etc.)."""
    val = str(_get_val(plugin, "operational_status", "") or "").strip().lower()
    if val:
        return val
    # Fallback to lifecycle status mapping
    if _lifecycle_value(plugin) == PluginLifecycleStatus.ACTIVE.value:
        return "enabled"
    return "unavailable"

def _plugin_kind(plugin: Any) -> str:
    """Determine the kind of plugin (cognitive_tool, functional, etc.)."""
    kind = _get_val(plugin, "plugin_kind")
    if callable(kind):
        try:
            return str(kind() or "unknown")
        except Exception:
            return "unknown"
    return str(kind or "unknown")

def derive_feature_code(plugin: Any) -> str:
    """Derive feature code from various potential attribute names."""
    return str(
        getattr(plugin, "feature_code", "") 
        or getattr(plugin, "behavior_key", "") 
        or getattr(plugin, "plugin_id", "")
    )

def build_managed_plugin_record(
    plugin: Any,
    *,
    feature_code: str | None = None,
    supports_multiple_plugins: bool | None = None,
    is_default: bool = False,
    is_official_release: bool = True,
    source_kind: str = "builtin",
    description: str | None = None,
) -> ManagedPluginRecord:
    """Canonical builder for in-memory plugin records, moved from web_console."""
    timestamp = datetime.now(timezone.utc)
    return ManagedPluginRecord(
        plugin=plugin,
        internal_revision_id=next(_MANAGED_PLUGIN_INTERNAL_REVISION),
        source_kind=source_kind,  # type: ignore[arg-type]
        description=(description or getattr(plugin, "purpose", "") or getattr(plugin, "plugin_id", "")).strip(),
        feature_code=feature_code or derive_feature_code(plugin),
        supports_multiple_plugins=bool(getattr(plugin, "supports_multiple_plugins", False)) if supports_multiple_plugins is None else supports_multiple_plugins,
        is_default=is_default,
        is_official_release=is_official_release,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp if _lifecycle_value(plugin) == PluginLifecycleStatus.ACTIVE.value else None,
        stopped_at=timestamp if _lifecycle_value(plugin) in {PluginLifecycleStatus.REVOKED.value, PluginLifecycleStatus.DEGRADED.value} else None,
    )
