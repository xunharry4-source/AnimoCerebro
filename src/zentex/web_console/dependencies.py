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
    runtime = get_runtime(request)
    return getattr(runtime, "agent_manager", None)


def get_agent_coordination_service(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead.

    Fail-closed (Zentex Codex §1): prioritizes modern app.state access.
    """
    svc = getattr(request.app.state, "agent_coordination_service", None)
    if svc is not None:
        return svc
        
    runtime = get_runtime(request)
    svc = getattr(runtime, "agent_coordination_service", None)
    if svc is None:
        logger.error(
            "dependency: agent_coordination_service is None — "
            "checked app.state and kernel singleton fallback",
            extra={"location": "web_console.dependencies", "action": "get_agent_coordination_service"},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "agent_coordination_service_unavailable",
                "message": "智能体协调服务未初始化，请检查启动流程。",
            },
        )
    return svc


def get_task_service(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead.

    Fail-closed (Zentex Codex §1): prioritizes modern app.state access.
    """
    svc = getattr(request.app.state, "task_service", None)
    if svc is not None:
        return svc
        
    runtime = get_runtime(request)
    svc = getattr(runtime, "task_service", None)
    if svc is None:
        logger.error(
            "dependency: task_service is None — "
            "checked app.state and kernel singleton fallback",
            extra={"location": "web_console.dependencies", "action": "get_task_service"},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "task_service_unavailable",
                "message": "任务管理服务未初始化，任务功能暂不可用。请检查启动流程。",
            },
        )
    return svc


def get_transcript_store(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead"""
    svc = getattr(request.app.state, "transcript_store", None)
    if svc is not None:
        return svc
    from zentex.kernel.service import get_service as get_kernel_service
    return get_kernel_service().get_transcript_store()


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
    svc = getattr(request.app.state, "plugin_registry", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "plugin_registry", None)


def get_plugin_service(request: Request) -> Any:
    """Returns plugin_service (modern first)."""
    svc = getattr(request.app.state, "plugin_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "plugin_service", None)


def get_managed_plugins(request: Request) -> Any:
    """⚠️ LEGACY - Use Facade instead"""
    runtime = get_runtime(request)
    return getattr(runtime, "managed_plugins", [])


def get_managed_plugin_records(request: Request) -> Any:
    """Get managed plugin records from app.state or runtime"""
    # Prefer app.state (modern approach)
    records = getattr(request.app.state, "managed_plugin_records", None)
    if records is not None:
        return records
        
    # Fallback to runtime (legacy)
    runtime = get_runtime(request)
    return getattr(runtime, "managed_plugin_records", {})


def get_cli_service(request: Request) -> Any:
    """Returns cli_service (modern first)."""
    svc = getattr(request.app.state, "cli_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "cli_service", None)


def get_mcp_service(request: Request) -> Any:
    """Returns McpIntegrationService (modern first)."""
    svc = getattr(request.app.state, "mcp_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "mcp_service", None)


# ========== Additional Legacy Getters (All as Shim Wrappers) ==========
# These all delegate to get_runtime() for backward compatibility
# They will be deleted once all code is migrated to Facade API

def get_active_model_provider(request: Request) -> Any:
    """Returns active_model_provider (modern first)."""
    svc = getattr(request.app.state, "active_model_provider", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "active_model_provider", None)


def get_temporal_engine(request: Request) -> Any:
    """Returns CognitiveTemporalEngine (modern first)."""
    svc = getattr(request.app.state, "temporal_engine", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "temporal_engine", None)


def get_conflict_engine(request: Request) -> Any:
    """Returns CognitiveConflictEngine (modern first)."""
    svc = getattr(request.app.state, "conflict_engine", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "conflict_engine", None)


def get_simulation_engine(request: Request) -> Any:
    """Returns CounterfactualSimulationEngine (modern first)."""
    svc = getattr(request.app.state, "simulation_engine", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "simulation_engine", None)


def get_interaction_mind_engine(request: Request) -> Any:
    """Returns InteractionMindEngine (modern first)."""
    svc = getattr(request.app.state, "interaction_mind_engine", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "interaction_mind_engine", None)


def get_consolidation_engine(request: Request) -> Any:
    """Returns ConsolidationEngine (modern first)."""
    svc = getattr(request.app.state, "consolidation_engine", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "consolidation_engine", None)


def get_enhanced_memory_service(request: Request) -> Any:
    """⚠️ LEGACY"""
    # create_app() stores the service directly on app.state; check there first.
    svc = getattr(request.app.state, "enhanced_memory_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "enhanced_memory_service", None)


def get_workspace_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    # create_app() stores workspace_store directly on app.state.
    svc = getattr(request.app.state, "workspace_store", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "workspace_store", None)


def get_active_session(request: Request) -> Any:
    """Returns active_session (modern first)."""
    svc = getattr(request.app.state, "active_session", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "active_session", None)


def get_upgrade_management_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "upgrade_management_store", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "upgrade_management_store", None)


def get_plugin_evolution_runtime(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "plugin_evolution_runtime", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "plugin_evolution_runtime", None)


def get_upgrade_execution_service(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "upgrade_execution_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "upgrade_execution_service", None)


def get_upgrade_audit_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "upgrade_audit_store", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "upgrade_audit_store", None)


def get_upgrade_memory_store(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "upgrade_memory_store", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "upgrade_memory_store", None)


def get_upgrade_evidence_service(request: Request) -> Any:
    """⚠️ LEGACY — reads app.state first (set by create_app), falls back to runtime."""
    svc = getattr(request.app.state, "upgrade_evidence_service", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "upgrade_evidence_service", None)


def get_plugin_feature_catalog(request: Request) -> Any:
    """Returns plugin_feature_catalog (modern first)."""
    svc = getattr(request.app.state, "plugin_feature_catalog", None)
    if svc is not None:
        return svc
    runtime = get_runtime(request)
    return getattr(runtime, "plugin_feature_catalog", None)


def get_reflection_service(request: Request) -> Any:
    """Returns reflection_service (modern first)."""
    svc = getattr(request.app.state, "reflection_service", None)
    if svc is not None:
        return svc
    from zentex.reflection.service_facade import get_reflection_service as get_legacy_reflection
    return get_legacy_reflection()


def get_learning_service(request: Request) -> Any:
    """Returns learning_service (modern first)."""
    svc = getattr(request.app.state, "learning_service", None)
    if svc is not None:
        return svc
    # There is no global learning service singleton yet, so we return None or raise
    return None


def get_weight_assembler(scope_owner: Any) -> Any:
    """⚠️ LEGACY"""
    app = getattr(scope_owner, "app", scope_owner)
    return getattr(app.state, "weight_assembler", None)
