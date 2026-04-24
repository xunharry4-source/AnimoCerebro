from __future__ import annotations
"""
Plugin Service Thin Adapter — Web Console Layer.

ARCHITECTURE ROLE:
1. Thin Facade: Directs API requests to core domain services (SystemPluginService).
2. Zero Business Logic: Strictly prohibited from implementing plugin merging, 
   overlay rules, lifecycle math, grouping, or relationship queries.
3. Responsibility:
   - [Query Condition Preparation]: Extract parameters from request context.
   - [Result Splicing]: Map plugin_service responses to UI contracts.

DECOUPLING POLICY (Zentex Codex §2):
This module must remain a 'Logic-Free Zone'. All business logic lives in 
`zentex.plugins.service.query.QueryService`.
"""
import logging
from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    ForceEnablePluginResponse,
    FunctionalPluginDetailResponse,
    ManagedPluginRecord,
    PluginFeatureGroupItem,
    PluginRelationshipItem,
)

logger = logging.getLogger(__name__)


def _map_to_cognitive_plugin_status_item(raw: Dict[str, Any]) -> CognitivePluginStatusItem:
    """
    Pure field mapper: converts raw dict from plugin_service to UI contract.
    
    NO business logic, NO calculations, NO conditionals beyond None checks.
    This is Result Splicing only.
    """
    return CognitivePluginStatusItem(
        tool_id=str(raw.get("plugin_id", "")),
        feature_code=str(raw.get("feature_code", raw.get("plugin_id", ""))),
        supports_multiple_plugins=bool(raw.get("supports_multiple_plugins", False)),
        plugin_kind=str(raw.get("category", raw.get("plugin_kind", "unknown"))),
        version=str(raw.get("version", "1.0.0")),
        lifecycle_status=str(raw.get("lifecycle_status", "unknown")),
        operational_status=str(raw.get("operational_status", "unknown")),
        health_status=str(raw.get("health_status")) if raw.get("health_status") else None,
        purpose=str(raw.get("purpose", raw.get("plugin_id", ""))),
        description=str(raw.get("description", raw.get("purpose", ""))),
        used_in=list(raw.get("used_in", []) or []),
        is_default=bool(raw.get("is_default", False)),
        is_official_release=bool(raw.get("is_official_release", True)),
        is_instantiated=bool(raw.get("is_instantiated", False)),
        can_force_enable=bool(raw.get("can_force_enable", False)),
        can_force_disable=bool(raw.get("can_force_disable", False)),
        can_delete=bool(raw.get("can_delete", False)),
        usage_count=int(raw.get("usage_count", 0)),
        failure_count=int(raw.get("failure_count", 0)),
        rollback_conditions=list(raw.get("rollback_conditions", []) or []),
        trigger_conditions=list(raw.get("trigger_conditions", []) or []),
        required_context=list(raw.get("required_context", []) or []),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        started_at=raw.get("started_at"),
        stopped_at=raw.get("stopped_at"),
        last_used_at=raw.get("last_used_at"),
    )


def build_plugin_payloads(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Optional[Dict[str, Any]] = None,
    plugin_service: Any = None,
) -> List[CognitivePluginStatusItem]:
    """
    Thin adapter: delegates to plugin_service, maps results.
    Zero business logic.
    """
    if plugin_service is None:
        return []
    
    # Delegate aggregation and sorting to core
    snapshot = plugin_service.get_sorted_plugin_list(cognitive_registry=cognitive_registry)
    
    # Pure result splicing
    return [_map_to_cognitive_plugin_status_item(raw) for raw in snapshot]


def build_cognitive_plugin_list(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Dict[str, ManagedPluginRecord],
    plugin_service: Any = None,
) -> List[CognitivePluginStatusItem]:
    """Thin adapter: delegates to plugin_service, filters and maps results."""
    if plugin_service is None:
        return []
    
    all_plugins = build_plugin_payloads(cognitive_registry, plugin_registry, managed_records, plugin_service)
    return [item for item in all_plugins if item.plugin_kind == "cognitive_tool"]


def build_functional_plugin_list(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Dict[str, ManagedPluginRecord],
    plugin_service: Any = None,
) -> List[CognitivePluginStatusItem]:
    """Thin adapter: delegates to plugin_service, filters and maps results."""
    if plugin_service is None:
        return []
    
    all_plugins = build_plugin_payloads(cognitive_registry, plugin_registry, managed_records, plugin_service)
    return [item for item in all_plugins if item.plugin_kind != "cognitive_tool"]


def build_plugin_feature_groups(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Any,
    feature_catalog: Any,
    plugin_service: Any = None,
) -> List[PluginFeatureGroupItem]:
    """
    Thin adapter: delegates ALL grouping logic to plugin_service.
    Only maps the returned structure to UI contract.
    """
    if plugin_service is None:
        return []
    
    # Delegate ALL business logic to plugin_service
    grouped_data = plugin_service.get_plugins_grouped_by_feature(
        cognitive_registry=cognitive_registry
    )
    
    # Pure result splicing
    result = []
    for group in grouped_data:
        plugins = [
            _map_to_cognitive_plugin_status_item(raw)
            for raw in group.get("plugins", [])
        ]
        
        result.append(PluginFeatureGroupItem(
            feature_code=group["feature_code"],
            display_name=group.get("display_name", group["feature_code"]),
            plugin_kind=group.get("plugin_kind", "functional"),
            supports_multiple_plugins=group.get("supports_multiple_plugins", False),
            binding_status=group.get("binding_status", "unbound"),
            active_plugin_ids=group.get("active_plugin_ids", []),
            plugins=plugins,
        ))
    
    return result


def build_cognitive_plugin_detail(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Any,
    plugin_service: Any,
    plugin_id: str,
) -> CognitivePluginDetailResponse:
    """
    Thin adapter: delegates ALL detail assembly to plugin_service.
    Only maps the returned structure to UI contract.
    """
    if plugin_service is None:
        raise KeyError(f"Plugin service unavailable")
    
    # Delegate ALL business logic to plugin_service
    detail_data = plugin_service.get_cognitive_plugin_full_detail(
        plugin_id,
        cognitive_registry=cognitive_registry
    )
    
    # Pure result splicing
    plugin_item = _map_to_cognitive_plugin_status_item(detail_data["plugin"])
    
    related_versions = [
        _map_to_cognitive_plugin_status_item(raw)
        for raw in detail_data.get("related_versions", [])
    ]
    
    functional_plugins = [
        PluginRelationshipItem(
            plugin=_map_to_cognitive_plugin_status_item(fp["plugin"]),
            role=fp.get("role", "primary"),
            priority=fp.get("priority", 1),
            fallback_id=fp.get("fallback_id"),
        )
        for fp in detail_data.get("functional_plugins", [])
    ]
    
    return CognitivePluginDetailResponse(
        plugin=plugin_item,
        related_versions=related_versions,
        functional_plugins=functional_plugins,
    )


def build_functional_plugin_detail(
    cognitive_registry: Any,
    plugin_registry: Any,
    managed_records: Any,
    plugin_service: Any,
    plugin_id: str,
) -> FunctionalPluginDetailResponse:
    """Thin adapter: delegates to plugin_service, maps results."""
    if plugin_service is None:
        raise KeyError(f"Plugin service unavailable")
    
    detail_data = plugin_service.get_functional_plugin_full_detail(
        plugin_id,
        cognitive_registry=cognitive_registry
    )
    
    plugin_item = _map_to_cognitive_plugin_status_item(detail_data["plugin"])
    
    cognitive_plugins = [
        PluginRelationshipItem(
            plugin=_map_to_cognitive_plugin_status_item(cp["plugin"]),
            role=cp.get("role", "primary"),
            priority=cp.get("priority", 1),
        )
        for cp in detail_data.get("cognitive_plugins", [])
    ]
    
    return FunctionalPluginDetailResponse(
        plugin=plugin_item,
        cognitive_plugins=cognitive_plugins,
    )


async def run_managed_plugin_test(
    plugin_service: Any, 
    plugin_id: str, 
    test_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Delegate plugin test execution to plugin service.
    
    NOTE: SystemPluginService does not have a generic run_plugin_test method.
    We fall back to run_health_check which is the closest functional equivalent
    for verifying a plugin instance.
    """
    if plugin_service is None:
        raise RuntimeError("plugin_service_unavailable")
    
    try:
        # run_health_check is async in SystemPluginService
        report = await plugin_service.run_health_check(plugin_id)
        
        # Convert HealthReport dataclass to dict for web response
        from dataclasses import asdict
        return asdict(report)
    except Exception as exc:
        logger.exception("run_managed_plugin_test failed for %s", plugin_id)
        raise


def force_enable_managed_plugin(
    plugin_service: Any, 
    plugin_id: str,
    reason: str = "Web Console Force-Enable"
) -> None:
    """Delegate enable to plugin service."""
    if plugin_service is not None:
        try:
            plugin_service.enable_plugin(plugin_id, reason=reason)
        except Exception as exc:
            # Do not swallow force-enable failures. Pretending the control operation
            # completed while only logging a warning makes the plugin page lie.
            logger.exception("force_enable_managed_plugin failed for %s", plugin_id)
            raise


def force_disable_managed_plugin(
    plugin_service: Any, 
    plugin_id: str,
    reason: str = "Web Console Force-Disable"
) -> None:
    """Delegate disable to plugin service."""
    if plugin_service is not None:
        try:
            plugin_service.disable_plugin(plugin_id, reason=reason)
        except Exception as exc:
            # Do not swallow force-disable failures. Warning-only behavior fakes a
            # successful control action while the runtime state stays unchanged.
            logger.exception("force_disable_managed_plugin failed for %s", plugin_id)
            raise


def build_force_enable_response(
    plugin_service: Any,
    plugin_id: str,
) -> ForceEnablePluginResponse:
    """Thin adapter: delegates to plugin_service, maps results."""
    if plugin_service is None:
        raise RuntimeError("Plugin service unavailable")
    
    # Delegate to plugin_service
    response_data = plugin_service.get_force_enable_result(plugin_id)
    
    # Pure result splicing
    plugin_item = _map_to_cognitive_plugin_status_item(response_data["plugin"])
    
    return ForceEnablePluginResponse(
        plugin=plugin_item,
        auto_disabled_plugin_ids=response_data.get("auto_disabled_plugin_ids", []),
        requires_override_warning=response_data.get("requires_override_warning", False),
        message=response_data.get("message", f"Plugin {plugin_id} force-enabled successfully."),
    )
