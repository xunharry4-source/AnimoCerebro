from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from plugins.weights.subjective_weight_plugin import WeightPluginAssembler

from zentex.agents.manager import AgentManager
from zentex.agents.service import AgentCoordinationService
from zentex.cli.adapter import CliAdapterPlugin
from zentex.cli.service import CliIntegrationService
from zentex.runtime.service import get_runtime_service
from zentex.memory.service import MemoryService
from zentex.web_console.contracts.plugins import ManagedPluginRecord, PluginFeatureCatalogItem
from zentex.runtime.runtime import BrainRuntime


def get_agent_manager(request: Request) -> AgentManager:
    manager = getattr(request.app.state, "agent_manager", None)
    if isinstance(manager, AgentManager):
        return manager
    raise HTTPException(
        status_code=503,
        detail="AgentManager is not attached to the app.",
    )


def get_agent_coordination_service(request: Request) -> AgentCoordinationService:
    service = getattr(request.app.state, "agent_coordination_service", None)
    if isinstance(service, AgentCoordinationService):
        return service
    raise HTTPException(
        status_code=503,
        detail="AgentCoordinationService is not attached to the app.",
    )


def get_runtime(request: Request) -> BrainRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if isinstance(runtime, BrainRuntime):
        return runtime
    raise HTTPException(
        status_code=503,
        detail="BrainRuntime is not attached to the app.",
    )




def get_task_service(request: Request) -> Any:
    service = getattr(request.app.state, "task_service", None)
    return service

def get_transcript_store(request: Request) -> Any:
    # Prioritize app state for testing and scoped runtimes
    store = getattr(request.app.state, "transcript_store", None)
    if store is not None:
        return store
    return get_runtime_service().get_transcript_store()

def get_cognitive_tool_registry(request: Request) -> Any:
    # Prioritize app state for testing and scoped runtimes
    registry = getattr(request.app.state, "cognitive_tool_registry", None)
    if registry is not None:
        return registry
    return get_runtime_service().get_tool_registry()

def get_plugin_registry(request: Request) -> Any:
    return getattr(request.app.state, "plugin_registry", None)

def get_managed_plugins(request: Request) -> List[Any]:
    return getattr(request.app.state, "managed_plugins", [])

def get_managed_plugin_records(request: Request) -> Dict[str, Any]:
    records = getattr(request.app.state, "managed_plugin_records", None)
    if isinstance(records, dict):
        return records
    return {}

def get_active_model_provider(request: Request) -> Any:
    """Resolve the active ModelProvider plugin (fail-closed if missing)."""
    # Using local import to avoid circular dependency and hide internal models
    from zentex.core.plugin_base import PluginLifecycleStatus
    from zentex.core.model_provider_spec import ModelProviderSpec
    for record in get_managed_plugin_records(request).values():
        plugin = getattr(record, "plugin", None)
        if isinstance(plugin, ModelProviderSpec) and plugin.status == PluginLifecycleStatus.ACTIVE:
            return plugin
    raise HTTPException(status_code=503, detail="No active model provider plugin is bound.")

def get_plugin_feature_catalog(request: Request) -> List[Any]:
    return getattr(request.app.state, "plugin_feature_catalog", [])

def get_upgrade_management_store(request: Request) -> Any:
    return getattr(request.app.state, "upgrade_management_store", None)

def get_plugin_evolution_runtime(request: Request) -> Any:
    return getattr(request.app.state, "plugin_evolution_runtime", None)

def get_upgrade_execution_service(request: Request) -> Any:
    return getattr(request.app.state, "upgrade_execution_service", None)

def get_upgrade_audit_store(request: Request) -> Any:
    return getattr(request.app.state, "upgrade_audit_store", None)

def get_upgrade_memory_store(request: Request) -> Any:
    return getattr(request.app.state, "upgrade_memory_store", None)

def get_upgrade_evidence_service(request: Request) -> Any:
    return getattr(request.app.state, "upgrade_evidence_service", None)

def get_active_session(request: Request) -> Any:
    return getattr(request.app.state, "session", None)

def get_temporal_engine(request: Request) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, "temporal_engine", None)

def get_conflict_engine(request: Request) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, "conflict_engine", None)

def get_simulation_engine(request: Request) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, "simulation_engine", None)

def get_interaction_mind_engine(request: Request) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, "interaction_mind_engine", None)

def get_consolidation_engine(request: Request) -> Any:
    runtime = get_runtime(request)
    return getattr(runtime, "consolidation_engine", None)

def get_enhanced_memory_service(request: Request) -> Any:
    service = getattr(request.app.state, "enhanced_memory_service", None)
    if service:
        return service
    # Fallback to runtime memory store via RuntimeService if available
    return get_runtime_service().get_identity_store() # Placeholder for unified memory access

def get_cli_service(request: Request) -> Any:
    from zentex.cli.service import CliIntegrationService
    from zentex.cli.adapter import CliAdapterPlugin
    adapter = getattr(request.app.state, "cli_adapter", None)
    if isinstance(adapter, CliAdapterPlugin):
        transcript_store = getattr(request.app.state, "transcript_store", None)
        task_service = getattr(request.app.state, "task_service", None)
        return CliIntegrationService(adapter, transcript_store=transcript_store, task_service=task_service)
    return None

def get_mcp_service(request: Request) -> Any:
    from zentex.mcp.service import McpIntegrationService
    from zentex.mcp.adapter import McpAdapterPlugin
    adapter = getattr(request.app.state, "mcp_adapter", None)
    if isinstance(adapter, McpAdapterPlugin):
        return McpIntegrationService(adapter)
    return None


def get_weight_assembler(scope_owner: Any) -> Optional[WeightPluginAssembler]:
    app = getattr(scope_owner, "app", scope_owner)
    state = getattr(app, "state", None)
    assembler = getattr(state, "weight_assembler", None)
    if isinstance(assembler, WeightPluginAssembler):
        return assembler
    return None
