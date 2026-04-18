"""
Web Console Dependency Providers — FastAPI dependency injection entry points.

RESPONSIBILITY:
  Centralises all FastAPI Depends() callables for the web_console layer.
  Route handlers MUST obtain services through these functions, not by directly
  importing or constructing service instances.

CAPABILITIES:
  - Facade-based getters (Phase 0): the authoritative path for new code.
  - Legacy shim getters: backward-compatible delegates to kernel.service for
    routes that have not yet been migrated to the Facade API.

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - Getters that return a service which may be None MUST raise HTTPException(503)
    rather than return None.  Route handlers must never receive None from a
    dependency and silently proceed.
  - Deprecated getters that raise NotImplementedError must NOT be silently
    swallowed by callers; callers must handle or propagate the failure explicitly.

DOES NOT:
  - Own any service state or lifecycle.
  - Implement business logic.
  - Serve as a fallback when the kernel singleton is unreachable; in that case
    it propagates the error to the caller as an HTTP 503.

MIGRATION STATUS:
  Phase 0 Facade getters are the target end-state.
  Legacy shim getters are provided only for gradual migration and will be
  removed once all route handlers are ported to the Facade API.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _get_app_state_service(request: Request, attr_name: str) -> Any:
    return getattr(request.app.state, attr_name, None)


def _get_legacy_kernel_attr(request: Request, attr_name: str) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, attr_name, None)


def _get_state_or_kernel_service(request: Request, attr_name: str) -> Any:
    svc = _get_app_state_service(request, attr_name)
    if svc is not None:
        return svc
    return _get_legacy_kernel_attr(request, attr_name)


def _require_state_or_kernel_service(
    request: Request,
    *,
    attr_name: str,
    error_code: str,
    message: str,
) -> Any:
    svc = _get_state_or_kernel_service(request, attr_name)
    if svc is not None:
        return svc
    logger.error(
        "dependency: %s is None — checked app.state and kernel singleton fallback",
        attr_name,
        extra={"location": "web_console.dependencies", "action": attr_name},
    )
    raise HTTPException(
        status_code=503,
        detail={
            "error": error_code,
            "message": message,
        },
    )


# ========== Phase 0: ONLY Facade-based getters ==========

def get_kernel_service_facade(request: Request) -> Any:
    """Get KernelServiceFacade from DI container
    
    This is the ONLY entry point for web_console dependencies.
    All route handlers must use this Facade to access session manager,
    state manager, event bus, and configuration.
    
    Returns:
        KernelServiceFacade: Unified dependency contract
        
    Raises:
        HTTPException(503): If container not initialized
    """
    from .di_container import WebConsoleContainer
    
    try:
        return WebConsoleContainer.get_kernel_service()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


def get_session_manager(request: Request) -> Any:
    """Get SessionManager from DI container
    
    Replaces: direct access to runtime.active_session
    """
    facade = get_kernel_service_facade(request)
    return facade.get_session_manager()


def get_nine_question_state_manager(request: Request) -> Any:
    """Get NineQuestionStateManager from DI container
    
    Replaces: direct access to runtime.nine_question_state + nine_question_router
    """
    facade = get_kernel_service_facade(request)
    return facade.get_nine_question_state_manager()


def get_event_bus(request: Request) -> Any:
    """Get EventBus from DI container
    
    Replaces: direct manipulation of runtime.nine_question_router
    """
    facade = get_kernel_service_facade(request)
    return facade.get_event_bus()


# ========== TEMPORARY: Legacy runtime access for migration ==========
# 
# These delegates are provided ONLY for gradual migration.
# DO NOT add new code that depends on these - use Facade getters instead.
# All uses of these should be replaced during PhaseN refactoring.
#

def get_runtime(request: Request) -> Any:
    """⚠️ LEGACY - Use get_kernel_service_facade() instead
    
    Temporary shim to support existing route handlers during migration.
    This will be removed after all route handlers are converted to Facade.
    
    Status: Phase 1 migration in progress
    """
    from zentex.kernel.service import get_service as get_kernel_service
    
    # Return the kernel service as a compatibility layer
    # This keeps old code working while we migrate
    return get_kernel_service()


def get_agent_manager(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead
    
    Compatibility shim during migration.
    """
    return _get_state_or_kernel_service(request, "agent_manager")


def get_agent_coordination_service(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead.

    Fail-closed (Zentex Codex §1): prioritizes modern app.state access.
    """
    return _require_state_or_kernel_service(
        request,
        attr_name="agent_coordination_service",
        error_code="agent_coordination_service_unavailable",
        message="智能体协调服务未初始化，请检查启动流程。",
    )


def get_task_service(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead.

    Fail-closed (Zentex Codex §1): prioritizes modern app.state access.
    """
    return _require_state_or_kernel_service(
        request,
        attr_name="task_service",
        error_code="task_service_unavailable",
        message="任务管理服务未初始化，任务功能暂不可用。请检查启动流程。",
    )


def get_transcript_store(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead"""
    svc = _get_app_state_service(request, "transcript_store")
    if svc is not None:
        return svc
    facade = get_kernel_service_facade(request)
    return facade.get_transcript_store()


def get_cognitive_tool_registry(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead"""
    from zentex.plugins.service import SystemPluginService
    # Cognitive tools are now managed by plugins.service
    # This is a temporary shim - should use plugin_service.query_cognitive_tools()
    raise NotImplementedError(
        "get_cognitive_tool_registry is deprecated. "
        "Use plugin_service.query_cognitive_tools() or KernelServiceFacade.get_cognitive_tools() instead."
    )


def get_plugin_registry(request: Request) -> Any:
    """Returns plugin_registry (modern first)."""
    return _get_state_or_kernel_service(request, "plugin_registry")


def get_plugin_service(request: Request) -> Any:
    """Returns plugin_service (modern first)."""
    return _get_state_or_kernel_service(request, "plugin_service")


def get_managed_plugins(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead"""
    return _get_state_or_kernel_service(request, "managed_plugins") or []


def get_managed_plugin_records(request: Request) -> Any:
    """Get managed plugin records from app.state or runtime"""
    return _get_state_or_kernel_service(request, "managed_plugin_records") or {}


def get_cli_service(request: Request) -> Any:
    """Returns cli_service (modern first)."""
    return _get_state_or_kernel_service(request, "cli_service")


def get_mcp_service(request: Request) -> Any:
    """Returns McpIntegrationService (modern first)."""
    return _get_state_or_kernel_service(request, "mcp_service")


# ========== Additional Legacy Getters (All as Shim Wrappers) ==========
# These all delegate to get_runtime() for backward compatibility
# They will be deleted once all code is migrated to Facade API

def get_active_model_provider(request: Request) -> Any:
    """Returns active_model_provider (modern first)."""
    return _get_state_or_kernel_service(request, "active_model_provider")


def get_temporal_engine(request: Request) -> Any:
    """Returns CognitiveTemporalEngine (modern first)."""
    return _get_state_or_kernel_service(request, "temporal_engine")


def get_conflict_engine(request: Request) -> Any:
    """Returns CognitiveConflictEngine (modern first)."""
    return _get_state_or_kernel_service(request, "conflict_engine")


def get_simulation_engine(request: Request) -> Any:
    """Returns CounterfactualSimulationEngine (modern first)."""
    return _get_state_or_kernel_service(request, "simulation_engine")


def get_interaction_mind_engine(request: Request) -> Any:
    """Returns InteractionMindEngine (modern first)."""
    return _get_state_or_kernel_service(request, "interaction_mind_engine")


def get_consolidation_engine(request: Request) -> Any:
    """Returns ConsolidationEngine (modern first)."""
    return _get_state_or_kernel_service(request, "consolidation_engine")


def get_enhanced_memory_service(request: Request) -> Any:
    """⚠️ LEGACY"""
    return _get_state_or_kernel_service(request, "enhanced_memory_service")


def get_workspace_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "workspace_store")


def get_active_session(request: Request) -> Any:
    """Returns active_session (modern first)."""
    return _get_state_or_kernel_service(request, "active_session")


def get_upgrade_management_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "upgrade_management_store")


def get_plugin_evolution_runtime(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "plugin_evolution_runtime")


def get_upgrade_execution_service(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "upgrade_execution_service")


def get_upgrade_audit_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "upgrade_audit_store")


def get_upgrade_memory_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "upgrade_memory_store")


def get_upgrade_evidence_service(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    return _get_state_or_kernel_service(request, "upgrade_evidence_service")


def get_plugin_feature_catalog(request: Request) -> Any:
    """Returns plugin_feature_catalog (modern first)."""
    return _get_state_or_kernel_service(request, "plugin_feature_catalog")


def get_reflection_service(request: Request) -> Any:
    """Returns reflection_service (modern first)."""
    return _get_state_or_kernel_service(request, "reflection_service")


def get_learning_service(request: Request) -> Any:
    """Returns learning_service (modern first)."""
    return _get_state_or_kernel_service(request, "learning_service")


def get_weight_assembler(scope_owner: Any) -> Any:
    """⚠️ LEGACY"""
    app = getattr(scope_owner, "app", scope_owner)
    return getattr(app.state, "weight_assembler", None)
