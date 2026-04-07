from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from plugins.weights.subjective_weight_plugin import WeightPluginAssembler

from zentex.agents.manager import AgentManager
from zentex.agents.service import AgentCoordinationService
from zentex.cli.adapter import CliAdapterPlugin
from zentex.cli.service import CliIntegrationService
from zentex.cognition.simulation import CounterfactualSimulationEngine
from zentex.cognition.social_mind import InteractionMindEngine
from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.core.plugin_base import BasePluginSpec, PluginLifecycleStatus
from zentex.memory.consolidation import ConsolidationEngine
from zentex.memory.enhanced import EnhancedMemoryService
from zentex.mcp.adapter import McpAdapterPlugin
from zentex.mcp.service import McpIntegrationService
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession
from zentex.runtime.temporal import CognitiveTemporalEngine
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.safety.conflict_engine import CognitiveConflictEngine
from zentex.tasks.service import TaskManagementService
from zentex.upgrade.evidence import UpgradeEvidenceService
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
from zentex.upgrade.management import UpgradeManagementStore
from zentex.web_console.contracts.plugins import ManagedPluginRecord, PluginFeatureCatalogItem


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


def get_task_service(request: Request) -> TaskManagementService:
    service = getattr(request.app.state, "task_service", None)
    if isinstance(service, TaskManagementService):
        return service
    raise HTTPException(
        status_code=503,
        detail="TaskManagementService is not attached to the app.",
    )


def get_runtime(request: Request) -> BrainRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if isinstance(runtime, BrainRuntime):
        return runtime
    raise HTTPException(
        status_code=503,
        detail="BrainRuntime is not attached to the web console app.",
    )


def get_transcript_store(request: Request) -> BrainTranscriptStore:
    runtime = get_runtime(request)
    store = getattr(runtime, "transcript_store", None)
    if isinstance(store, BrainTranscriptStore):
        return store
    raise HTTPException(
        status_code=503,
        detail="BrainTranscriptStore is not attached to the BrainRuntime.",
    )


def get_cognitive_tool_registry(request: Request) -> CognitiveToolRegistry:
    registry = getattr(request.app.state, "cognitive_tool_registry", None)
    if isinstance(registry, CognitiveToolRegistry):
        return registry
    raise HTTPException(
        status_code=503,
        detail="CognitiveToolRegistry is not attached to the web console app.",
    )


def get_plugin_registry(request: Request) -> AbstractPluginRegistry[Any] | None:
    return getattr(request.app.state, "plugin_registry", None)


def get_managed_plugins(request: Request) -> List[BasePluginSpec]:
    raw_plugins = getattr(request.app.state, "managed_plugins", [])
    if not isinstance(raw_plugins, list):
        return []
    return [plugin for plugin in raw_plugins if isinstance(plugin, BasePluginSpec)]


def get_managed_plugin_records(request: Request) -> Dict[str, ManagedPluginRecord]:
    records = getattr(request.app.state, "managed_plugin_records", None)
    if isinstance(records, dict):
        return records
    return {}


def get_active_model_provider(request: Request) -> ModelProviderSpec:
    """Resolve the active ModelProvider plugin (fail-closed if missing)."""
    for record in get_managed_plugin_records(request).values():
        plugin = getattr(record, "plugin", None)
        if isinstance(plugin, ModelProviderSpec) and plugin.status == PluginLifecycleStatus.ACTIVE:
            return plugin
    raise HTTPException(status_code=503, detail="No active model provider plugin is bound.")


def get_plugin_feature_catalog(request: Request) -> List[PluginFeatureCatalogItem]:
    raw_catalog = getattr(request.app.state, "plugin_feature_catalog", None)
    if not isinstance(raw_catalog, list):
        return []
    return [item for item in raw_catalog if isinstance(item, PluginFeatureCatalogItem)]


def get_upgrade_management_store(request: Request) -> UpgradeManagementStore:
    store = getattr(request.app.state, "upgrade_management_store", None)
    if isinstance(store, UpgradeManagementStore):
        return store
    raise HTTPException(
        status_code=503,
        detail="UpgradeManagementStore is not attached to the web console app.",
    )


def get_plugin_evolution_runtime(request: Request) -> PluginEvolutionRuntime:
    runtime = getattr(request.app.state, "plugin_evolution_runtime", None)
    if isinstance(runtime, PluginEvolutionRuntime):
        return runtime
    raise HTTPException(
        status_code=503,
        detail="PluginEvolutionRuntime is not attached to the web console app.",
    )


def get_upgrade_execution_service(request: Request) -> UpgradeExecutionService:
    service = getattr(request.app.state, "upgrade_execution_service", None)
    if isinstance(service, UpgradeExecutionService):
        return service
    raise HTTPException(
        status_code=503,
        detail="UpgradeExecutionService is not attached to the web console app.",
    )


def get_upgrade_audit_store(request: Request) -> UpgradeAuditStore:
    store = getattr(request.app.state, "upgrade_audit_store", None)
    if isinstance(store, UpgradeAuditStore):
        return store
    raise HTTPException(
        status_code=503,
        detail="UpgradeAuditStore is not attached to the web console app.",
    )


def get_upgrade_memory_store(request: Request) -> UpgradeMemoryStore:
    store = getattr(request.app.state, "upgrade_memory_store", None)
    if isinstance(store, UpgradeMemoryStore):
        return store
    raise HTTPException(
        status_code=503,
        detail="UpgradeMemoryStore is not attached to the web console app.",
    )


def get_upgrade_evidence_service(request: Request) -> UpgradeEvidenceService:
    service = getattr(request.app.state, "upgrade_evidence_service", None)
    if isinstance(service, UpgradeEvidenceService):
        return service
    raise HTTPException(
        status_code=503,
        detail="UpgradeEvidenceService is not attached to the web console app.",
    )


def get_active_session(request: Request) -> BrainSession | None:
    session = getattr(request.app.state, "session", None)
    if isinstance(session, BrainSession):
        return session
    return None


def get_temporal_engine(request: Request) -> CognitiveTemporalEngine:
    runtime = get_runtime(request)
    temporal_engine = getattr(runtime, "temporal_engine", None)
    if isinstance(temporal_engine, CognitiveTemporalEngine):
        return temporal_engine
    raise HTTPException(
        status_code=503,
        detail="CognitiveTemporalEngine is not attached to the runtime.",
    )


def get_conflict_engine(request: Request) -> CognitiveConflictEngine:
    runtime = get_runtime(request)
    conflict_engine = getattr(runtime, "conflict_engine", None)
    if isinstance(conflict_engine, CognitiveConflictEngine):
        return conflict_engine
    raise HTTPException(
        status_code=503,
        detail="CognitiveConflictEngine is not attached to the runtime.",
    )


def get_simulation_engine(request: Request) -> CounterfactualSimulationEngine:
    runtime = get_runtime(request)
    simulation_engine = getattr(runtime, "simulation_engine", None)
    if isinstance(simulation_engine, CounterfactualSimulationEngine):
        return simulation_engine
    raise HTTPException(
        status_code=503,
        detail="CounterfactualSimulationEngine is not attached to the runtime.",
    )


def get_interaction_mind_engine(request: Request) -> InteractionMindEngine:
    runtime = get_runtime(request)
    interaction_mind_engine = getattr(runtime, "interaction_mind_engine", None)
    if isinstance(interaction_mind_engine, InteractionMindEngine):
        return interaction_mind_engine
    raise HTTPException(
        status_code=503,
        detail="InteractionMindEngine is not attached to the runtime.",
    )


def get_consolidation_engine(request: Request) -> ConsolidationEngine:
    runtime = get_runtime(request)
    consolidation_engine = getattr(runtime, "consolidation_engine", None)
    if isinstance(consolidation_engine, ConsolidationEngine):
        return consolidation_engine
    raise HTTPException(
        status_code=503,
        detail="ConsolidationEngine is not attached to the runtime.",
    )

def get_enhanced_memory_service(request: Request) -> EnhancedMemoryService:
    service = getattr(request.app.state, "enhanced_memory_service", None)
    if isinstance(service, EnhancedMemoryService):
        return service
    runtime = getattr(request.app.state, "runtime", None)
    runtime_memory_store = getattr(runtime, "runtime_memory_store", None)
    if isinstance(runtime_memory_store, EnhancedMemoryService):
        return runtime_memory_store
    raise HTTPException(
        status_code=503,
        detail="EnhancedMemoryService is not attached to the web console app.",
    )


def get_cli_service(request: Request) -> CliIntegrationService:
    adapter = getattr(request.app.state, "cli_adapter", None)
    if isinstance(adapter, CliAdapterPlugin):
        return CliIntegrationService(adapter)
    raise HTTPException(
        status_code=503,
        detail="CliAdapterPlugin is not attached to the web console app.",
    )


def get_mcp_service(request: Request) -> McpIntegrationService:
    adapter = getattr(request.app.state, "mcp_adapter", None)
    if isinstance(adapter, McpAdapterPlugin):
        return McpIntegrationService(adapter)
    raise HTTPException(
        status_code=503,
        detail="McpAdapterPlugin is not attached to the web console app.",
    )


def get_weight_assembler(scope_owner: Any) -> Optional[WeightPluginAssembler]:
    app = getattr(scope_owner, "app", scope_owner)
    state = getattr(app, "state", None)
    assembler = getattr(state, "weight_assembler", None)
    if isinstance(assembler, WeightPluginAssembler):
        return assembler
    return None
