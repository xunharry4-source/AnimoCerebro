from __future__ import annotations
"""
Canonical public entrypoint for plugin access in Zentex.

External callers must import plugin governance APIs from this package:
    from zentex.plugins.service import SystemPluginService
"""


import logging
from typing import Any, Optional, Union

from .manager import SystemPluginService
from .registry import CognitiveToolRegistry, ExecutionDomainRegistry, InMemoryAuditSink
from .nine_questions import NineQuestionPluginService, get_service as get_nq_service
from zentex.plugins.models import PluginFeatureCatalogItem

logger = logging.getLogger(__name__)


def _extract_binding_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    data = getattr(payload, "data", None)
    if isinstance(data, list):
        return data
    return []

try:  # pragma: no cover - optional export compatibility
    from zentex.plugins.weights import WeightPluginAssembler, RationalAuditRejectError
except ModuleNotFoundError:  # pragma: no cover - legacy module drift
    WeightPluginAssembler = None  # type: ignore[assignment]
    RationalAuditRejectError = RuntimeError  # type: ignore[assignment]

try:  # pragma: no cover - optional export compatibility
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
        resolve_env_value,
    )
except ModuleNotFoundError:  # pragma: no cover - legacy module drift
    class AuthError(RuntimeError):
        pass

    class ConfigError(RuntimeError):
        pass

    class RateLimitError(RuntimeError):
        pass

    class RemoteServiceError(RuntimeError):
        pass

    class RemoteTimeoutError(RuntimeError):
        pass

    class ResponseParseError(RuntimeError):
        pass

    BaseProviderTool = object  # type: ignore[assignment]
    OpenAICompatibleGatewayTool = object  # type: ignore[assignment]
    ToolInvocationRequest = dict  # type: ignore[assignment]
    ToolInvocationResponse = dict  # type: ignore[assignment]

    def build_default_provider_tools(*args: Any, **kwargs: Any) -> None:
        raise ModuleNotFoundError("zentex.plugins.provider_tools is unavailable in this environment")

    def is_env_var_reference(*args: Any, **kwargs: Any) -> bool:
        return False

    def resolve_env_value(*args: Any, **kwargs: Any) -> Optional[str]:
        return None

def get_default_provider_key() -> str:
    """
    Get the default LLM provider key from environment or config.
    
    Returns:
        Provider key string (e.g., 'openai', 'anthropic', etc.)
    """
    from zentex.plugins.provider_tools import get_default_provider_key as _get_key
    return _get_key()


def query_all_plugins_by_lifecycle(
    plugin_service: SystemPluginService,
    *,
    category: Optional[str] = None,
    lifecycle_status: Optional[str] = None,
    behavior_key: Optional[str] = None,
    feature_code: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query all plugins by lifecycle phase via the canonical public service package."""
    return plugin_service.query_plugins_by_lifecycle(
        category=category,
        lifecycle_status=lifecycle_status,
        behavior_key=behavior_key,
        feature_code=feature_code,
        limit=limit,
    )


def query_all_plugins_by_operational_status(
    plugin_service: SystemPluginService,
    *,
    category: Optional[str] = None,
    operational_status: Optional[str] = None,
    behavior_key: Optional[str] = None,
    feature_code: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query all plugins by runtime status via the canonical public service package."""
    return plugin_service.query_plugins_by_operational_status(
        category=category,
        operational_status=operational_status,
        behavior_key=behavior_key,
        feature_code=feature_code,
        limit=limit,
    )


def query_cognitive_plugin_functionals_by_lifecycle(
    plugin_service: SystemPluginService,
    cognitive_plugin_id: str,
    *,
    lifecycle_status: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query one cognitive plugin's functional plugins by lifecycle."""
    return plugin_service.query_cognitive_functionals_by_lifecycle(
        cognitive_plugin_id,
        lifecycle_status=lifecycle_status,
        role=role,
        limit=limit,
    )


def query_cognitive_plugin_functionals_by_operational_status(
    plugin_service: SystemPluginService,
    cognitive_plugin_id: str,
    *,
    operational_status: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query one cognitive plugin's functional plugins by runtime status."""
    return plugin_service.query_cognitive_functionals_by_operational_status(
        cognitive_plugin_id,
        operational_status=operational_status,
        role=role,
        limit=limit,
    )


def query_enabled_cognitive_plugin_functionals(
    plugin_service: SystemPluginService,
    cognitive_plugin_id: str,
    *,
    role: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query one cognitive plugin's enabled functional plugins."""
    bindings: Any = None
    if callable(getattr(plugin_service, "query_enabled_functional_plugins_for_cognitive", None)):
        bindings = _extract_binding_rows(
            plugin_service.query_enabled_functional_plugins_for_cognitive(
                cognitive_plugin_id,
                role=role,
                limit=limit,
            )
        )
    if not isinstance(bindings, list) and callable(
        getattr(plugin_service, "query_cognitive_functionals_by_status", None)
    ):
        bindings = plugin_service.query_cognitive_functionals_by_status(
            cognitive_plugin_id,
            operational_status="enabled",
            role=role,
            limit=limit,
        )
    if not isinstance(bindings, list) and callable(
        getattr(plugin_service, "query_cognitive_functionals_by_operational_status", None)
    ):
        bindings = plugin_service.query_cognitive_functionals_by_operational_status(
            cognitive_plugin_id,
            operational_status="enabled",
            role=role,
            limit=limit,
        )
    resolved = bindings if isinstance(bindings, list) else []
    if resolved:
        return resolved

    # Real runtime bootstrap path: if bindings exist but are still candidate/stopped,
    # activate them on demand through the canonical management API.
    try:
        lifecycle_bindings = plugin_service.query_cognitive_functionals_by_lifecycle(
            cognitive_plugin_id,
            role=role,
            limit=limit,
        )
        if isinstance(lifecycle_bindings, list) and lifecycle_bindings:
            for binding in lifecycle_bindings:
                plugin_id = str(binding.get("plugin_id") or "").strip()
                if not plugin_id:
                    continue
                try:
                    plugin_service.enable_plugin(
                        plugin_id,
                        reason=f"Auto-activate functional binding for {cognitive_plugin_id}",
                    )
                except Exception:
                    logger.exception(
                        "[Plugins] Failed auto-activating functional binding %s for %s",
                        plugin_id,
                        cognitive_plugin_id,
                    )
            rebound = _extract_binding_rows(
                plugin_service.query_enabled_functional_plugins_for_cognitive(
                    cognitive_plugin_id,
                    role=role,
                    limit=limit,
                )
            )
            if rebound:
                return rebound
    except Exception:
        logger.exception(
            "[Plugins] Failed resolving enabled functional bindings for cognitive plugin %s",
            cognitive_plugin_id,
        )
    return []


def query_cognitive_tools(
    plugin_service: SystemPluginService,
    *,
    operational_status: Optional[str] = "enabled",
    feature_code: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return cognitive-tool-like plugin rows through the canonical plugins service."""
    return plugin_service.query_plugins_by_operational_status(
        category="cognitive",
        operational_status=operational_status,
        feature_code=feature_code,
        limit=limit,
    )


def query_plugin_records(
    plugin_service: SystemPluginService,
    *,
    category: Optional[str] = None,
    operational_status: Optional[str] = None,
    feature_code: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return generic plugin records without exposing an internal registry instance."""
    return plugin_service.query_plugins_by_operational_status(
        category=category,
        operational_status=operational_status,
        feature_code=feature_code,
        limit=limit,
    )


def execute_enabled_cognitive_plugin_functionals(
    plugin_service: SystemPluginService,
    cognitive_plugin_id: str,
    *,
    parameters_by_plugin_id: dict[str, dict[str, Optional[Any]]] = None,
    default_parameters: dict[str, Optional[Any]] = None,
    trace_id: str,
    originator_id: str,
    caller_plugin_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query enabled functional bindings and execute them through the public service."""
    bindings: Any = None
    if callable(getattr(plugin_service, "query_enabled_functional_plugins_for_cognitive", None)):
        bindings = query_enabled_cognitive_plugin_functionals(
            plugin_service,
            cognitive_plugin_id,
            role=role,
            limit=limit,
        )
    if not isinstance(bindings, list) and callable(
        getattr(plugin_service, "query_cognitive_functionals_by_status", None)
    ):
        bindings = plugin_service.query_cognitive_functionals_by_status(
            cognitive_plugin_id,
            operational_status="enabled",
            role=role,
            limit=limit,
        )
    if not isinstance(bindings, list) and callable(
        getattr(plugin_service, "query_cognitive_functionals_by_operational_status", None)
    ):
        bindings = plugin_service.query_cognitive_functionals_by_operational_status(
            cognitive_plugin_id,
            operational_status="enabled",
            role=role,
            limit=limit,
        )
    if not isinstance(bindings, list):
        bindings = []

    results: list[dict[str, Any]] = []
    for binding in bindings:
        functional_plugin_id = str(binding.get("plugin_id") or "").strip()
        if not functional_plugin_id:
            continue
        parameters = dict(default_parameters or {})
        parameters.update((parameters_by_plugin_id or {}).get(functional_plugin_id, {}))
        feedback = plugin_service.execute_plugin_once_sync(
            plugin_id=functional_plugin_id,
            task_id=f"{trace_id}:{functional_plugin_id}",
            parameters=parameters,
            trace_id=trace_id,
            originator_id=originator_id,
            caller_plugin_id=caller_plugin_id or cognitive_plugin_id,
        )
        results.append(
            {
                **binding,
                "status": getattr(feedback, "status", None),
                "error": getattr(feedback, "error", None),
                "remarks": getattr(feedback, "remarks", None),
                "result": unwrap_plugin_feedback_result(getattr(feedback, "result", None)),
            }
        )
    return results


def unwrap_plugin_feedback_result(result: Any) -> Any:
    """Unwrap TaskFeedback.result when the execution layer had to box non-dict values."""
    if isinstance(result, dict) and set(result.keys()) == {"value"}:
        return result["value"]
    return result


def execute_cognitive_plugin(
    plugin_service: SystemPluginService,
    *,
    plugin_id: str,
    context: dict[str, Any],
    session_id: str = "",
    turn_id: str = "",
    trace_id: str = "",
    originator_id: str = "",
):
    """Execute one cognitive plugin through the canonical public service package."""
    return plugin_service.execute_cognitive_plugin(
        plugin_id=plugin_id,
        context=context,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        originator_id=originator_id,
    )


def query_enabled_functional_plugins_for_cognitive(
    plugin_service: SystemPluginService,
    cognitive_plugin_id: str,
    *,
    role: Optional[str] = None,
    limit: int = 200,
    trace_id: str = "",
):
    """Query enabled functional plugins bound to one cognitive plugin."""
    return plugin_service.query_enabled_functional_plugins_for_cognitive(
        cognitive_plugin_id,
        role=role,
        limit=limit,
        trace_id=trace_id,
    )


def execute_functional_plugin(
    plugin_service: SystemPluginService,
    *,
    plugin_id: str,
    context: dict[str, Any],
    caller_plugin_id: str,
    trace_id: str = "",
    originator_id: str = "",
):
    """Execute one functional plugin through the canonical public service package."""
    return plugin_service.execute_functional_plugin(
        plugin_id=plugin_id,
        context=context,
        caller_plugin_id=caller_plugin_id,
        trace_id=trace_id,
        originator_id=originator_id,
    )


def register_discovered_plugins(
    plugin_service: SystemPluginService,
) -> dict[str, int]:
    """Register discovered plugin units into storage through the public service."""
    return plugin_service.register_discovered_plugins()


def rehydrate_registered_plugins(
    plugin_service: SystemPluginService,
) -> dict[str, int]:
    """Load already-registered plugins from storage into runtime memory."""
    return plugin_service.rehydrate_registered_plugins()


def ensure_default_plugin_relationships(
    plugin_service: SystemPluginService,
) -> dict[str, int]:
    """Create built-in default plugin relations through the public service."""
    return plugin_service.ensure_default_relationships()


def scan_orphaned_plugin_records(
    plugin_service: SystemPluginService,
) -> list[dict[str, Any]]:
    """List database plugin records whose implementations are no longer discoverable."""
    return plugin_service.scan_orphaned_plugin_records()


def reconcile_orphaned_plugin_records(
    plugin_service: SystemPluginService,
    *,
    reason: str,
) -> dict[str, Any]:
    """Mark orphaned plugin records unavailable without deleting history."""
    return plugin_service.reconcile_orphaned_plugin_records(reason=reason)

__all__ = [
    "SystemPluginService",
    "PluginFeatureCatalogItem",
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
    "resolve_env_value",
    "get_default_provider_key",
    "query_all_plugins_by_lifecycle",
    "query_all_plugins_by_operational_status",
    "query_cognitive_plugin_functionals_by_lifecycle",
    "query_cognitive_plugin_functionals_by_operational_status",
    "query_enabled_cognitive_plugin_functionals",
    "execute_enabled_cognitive_plugin_functionals",
    "unwrap_plugin_feedback_result",
    "execute_cognitive_plugin",
    "query_enabled_functional_plugins_for_cognitive",
    "execute_functional_plugin",
    "register_discovered_plugins",
    "rehydrate_registered_plugins",
    "ensure_default_plugin_relationships",
    "scan_orphaned_plugin_records",
    "reconcile_orphaned_plugin_records",
    "NineQuestionPluginService",
    "get_nq_service",
]


# Global singleton instance for plugins service
_default_service: Optional[SystemPluginService] = None


def get_service() -> SystemPluginService:
    """Standard service factory function for launcher assembly.
    
    Returns the global SystemPluginService instance, creating it if necessary.
    This function is required by the SystemAssembler to initialize the plugins service.
    """
    global _default_service
    if _default_service is None:
        from zentex.common.storage_paths import get_storage_paths

        default_db_path = str(get_storage_paths().core_db)
        _default_service = SystemPluginService(db_path=default_db_path)
    return _default_service
