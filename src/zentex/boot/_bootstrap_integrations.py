"""Bootstrap module for legacy integrations.

This module contains adapter, registry, and integration initialization functions
that still use direct internal class instantiation. These are concentrated here
for easier migration to service-based APIs in the future.

⚠️ ARCHITECTURAL NOTE: These functions violate the architectural principle that
all external access must flow through service.py. They are kept here temporarily
for backward compatibility while the system transitions to pure service APIs.

Functions in this module should be:
1. Used ONLY during system startup (web_dev.py initialization)
2. Gradually migrated to use service APIs instead
3. NOT used in production runtime critical paths
"""

from __future__ import annotations
from typing import Any, List, Optional, Tuple
from datetime import datetime, timezone

from zentex.runtime.transcript import BrainTranscriptStore
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus

# Legacy imports - these are the architectural violations being isolated
from zentex.plugins.registry import CognitiveToolRegistry
from zentex.plugins.registry import InMemoryAuditSink
from zentex.plugins.registries import TaskRegistry, ExecutionDomainRegistry
from zentex.adapters.mcp_adapter import McpAdapterPlugin, McpServerConfig, McpToolBindingConfig
from zentex.adapters.cli_adapter import CliAdapterPlugin, SubprocessCliTransport, CliToolRegistrationConfig
from zentex.adapters.mcp_client import FakeMcpTransportClient, McpToolDescriptor
from zentex.plugins.weight_assembler import WeightPluginAssembler
from zentex.tasks.service import TaskManagementService
from zentex.tasks.models import (
    LLMTaskDecomposerPlugin,
)

# Public API imports
from zentex.core.model_provider_spec import ModelProviderSpec


def setup_cognitive_registry(
    transcript_store: BrainTranscriptStore,
    asset_store: Optional[Any] = None
) -> CognitiveToolRegistry:
    """
    Initialize the cognitive tool registry for nine questions and analysis tools.
    
    This function builds the core cognitive registry with all builtin plugins
    registered and properly promoted through their lifecycle stages.
    
    Args:
        transcript_store: The transcript store for audit purposes
        asset_store: Optional asset store for persistence
    
    Returns:
        A fully initialized CognitiveToolRegistry
    
    ⚠️ ARCHITECTURAL: This function directly instantiates internal registry classes.
    Should be migrated to CognitiveService API.
    """
    from zentex.admin.bootstrap_plugins import (
        _build_cognitive_tool_spec,
        build_q1_where_am_i_plugin,
        build_q2_who_am_i_plugin,
        build_q3_what_do_i_have_plugin,
        build_q4_what_can_i_do_plugin,
        build_q5_what_am_i_allowed_to_do_plugin,
        build_q6_what_should_i_not_do_plugin,
        build_q7_what_else_can_i_do_plugin,
        build_q8_what_should_i_do_now_plugin,
        build_q9_how_should_i_act_plugin,
        build_memory_extractor_plugin,
        build_reflection_generator_plugin,
    )
    
    startup_audit_sink = InMemoryAuditSink()
    registry = CognitiveToolRegistry(
        transcript_store=startup_audit_sink,
        protected_plugin_ids={
            "risk-comparator",
            "evidence-ranker",
            "decision-summarizer",
        },
        asset_store=asset_store
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-comparator",
            behavior_key="risk_assessment",
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default risk assessment tool (builtin)",
    )
    registry.promote_plugin(
        "risk-comparator",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    registry.promote_plugin(
        "risk-comparator",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="health checks passed",
    )
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="evidence-ranker",
            behavior_key="evidence_ranking",
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default evidence ranking tool (builtin)",
    )
    registry.promote_plugin(
        "evidence-ranker",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    registry.promote_plugin(
        "evidence-ranker",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="staged for runtime failure drill",
    )
    degraded_ranker = registry.get_registration("evidence-ranker")
    degraded_timestamp = datetime.now(timezone.utc)
    degraded_ranker_spec = degraded_ranker.spec.transition_to(
        PluginLifecycleStatus.DEGRADED,
        revocation_reasons=["seeded_degraded_for_web_console_demo"],
    )
    registry._plugins["evidence-ranker"] = degraded_ranker_spec
    registry._registrations["evidence-ranker"] = degraded_ranker.model_copy(
        update={
            "spec": degraded_ranker_spec,
            "failure_count": 3,
            "updated_at": degraded_timestamp,
            "started_at": degraded_ranker.started_at or degraded_timestamp,
        }
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="decision-summarizer",
            behavior_key="decision_summary",
            health_status=PluginHealthStatus.DEGRADED,
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default decision summarizer tool (builtin)",
    )
    registry.revoke_plugin("decision-summarizer", "manual audit revocation")

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="idea-scout",
            behavior_key="risk_assessment",
            trigger_conditions=["inspection"],
            is_official_release=True,
        )
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-lab-preview",
            version="1.3.0-preview",
            behavior_key="risk_assessment",
            trigger_conditions=["inspection"],
            is_official_release=False,
        )
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-comparator-legacy",
            version="0.9.0",
            behavior_key="risk_assessment",
            is_official_release=True,
        ),
        source_kind="builtin",
        description="Legacy risk comparator (builtin rollback candidate)",
    )

    # Core cognitive operators (LLM MANDATORY): nine questions + memory + reflection
    core_plugins = [
        build_q1_where_am_i_plugin(),
        build_q2_who_am_i_plugin(),
        build_q3_what_do_i_have_plugin(),
        build_q4_what_can_i_do_plugin(),
        build_q5_what_am_i_allowed_to_do_plugin(),
        build_q6_what_should_i_not_do_plugin(),
        build_q7_what_else_can_i_do_plugin(),
        build_q8_what_should_i_do_now_plugin(),
        build_q9_how_should_i_act_plugin(),
        build_memory_extractor_plugin(),
        build_reflection_generator_plugin(),
    ]
    for plugin in core_plugins:
        registration = registry.register(
            plugin,
            source_kind="builtin",
            description=f"Core cognitive operator: {plugin.plugin_id}",
        )
        if registration is None:
            continue
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
            audit_reason="web console sandbox verified",
        )
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.ACTIVE,
            audit_reason="web console active for inspection/testing",
        )

    risk_comparator = registry.get_registration("risk-comparator")
    usage_timestamp = datetime.now(timezone.utc)
    registry._registrations["risk-comparator"] = risk_comparator.model_copy(
        update={
            "usage_count": max(1, risk_comparator.usage_count),
            "updated_at": usage_timestamp,
            "last_used_at": usage_timestamp,
            "started_at": risk_comparator.started_at or usage_timestamp,
        }
    )
    return registry


def setup_mcp_adapter(
    transcript_store: BrainTranscriptStore,
    cognitive_registry: CognitiveToolRegistry,
    asset_store: Optional[Any] = None,
    *,
    defer_sync: bool = False,
) -> Tuple[McpAdapterPlugin, ExecutionDomainRegistry]:
    """
    Initialize the MCP (Model Context Protocol) adapter.
    
    This function creates and configures the MCP adapter plugin with fake
    transport clients for demo/testing purposes.
    
    Args:
        transcript_store: The transcript store for audit
        cognitive_registry: The cognitive tool registry
        asset_store: Optional asset store
        defer_sync: Whether to defer server sync to background
    
    Returns:
        Tuple of (McpAdapterPlugin, ExecutionDomainRegistry)
    
    ⚠️ ARCHITECTURAL: Directly instantiates McpAdapterPlugin and related classes.
    Should be migrated to McpIntegrationService API.
    """
    from threading import Thread
    import logging
    
    logger = logging.getLogger(__name__)
    
    execution_registry = ExecutionDomainRegistry(asset_store=asset_store)
    server_configs = [
        McpServerConfig(
            server_id="knowledge-hub",
            transport_type="stdio",
            command="uvx",
            args=["knowledge-hub-mcp"],
            env={"KNOWLEDGE_ENV": "dev"},
            tool_bindings=[
                McpToolBindingConfig(
                    tool_name="search_documents",
                    domain="cognitive",
                    read_only=True,
                    side_effect_free=True,
                    mutates_state=False,
                )
            ],
        ),
        McpServerConfig(
            server_id="ops-bridge",
            transport_type="sse",
            command="https://ops.example.invalid/mcp",
            args=[],
            env={},
        ),
    ]

    transports = {
        "knowledge-hub": FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="search_documents",
                    description="Search indexed runbooks and incident notes",
                    input_schema={"type": "object"},
                    mutates_state=False,
                    read_only_hint=True,
                )
            ],
            invocations={
                "search_documents": {
                    "summary": "knowledge search completed",
                    "context_updates": {"knowledge_hits": ["runbook-42"]},
                }
            },
            healthy=True,
        ),
        "ops-bridge": FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="update_ticket",
                    description="Update incident ticket in external system",
                    input_schema={"type": "object"},
                    mutates_state=True,
                    read_only_hint=False,
                )
            ],
            invocations={"update_ticket": {"summary": "ticket updated", "receipt_id": "ops-991"}},
            healthy=True,
        ),
    }

    adapter = McpAdapterPlugin(
        plugin_id="mcp-adapter-core",
        version="1.0.0",
        feature_code="external.mcp",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_adapter_regression"],
        revocation_reasons=["mcp_adapter_disabled"],
        health_probe_endpoint="mcp://health",
        server_configs=server_configs,
    )
    adapter.attach_runtime(
        client_factory=lambda config: transports[config.server_id],
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    if defer_sync:
        def _sync_bg():
            try:
                adapter.sync_servers()
            except Exception:
                logger.exception("Deferred MCP sync failed")
        Thread(target=_sync_bg, name="mcp-bg-sync", daemon=True).start()
    else:
        adapter.sync_servers()
    return adapter, execution_registry


def setup_cli_adapter(
    transcript_store: BrainTranscriptStore,
    cognitive_registry: CognitiveToolRegistry,
    execution_registry: ExecutionDomainRegistry,
    asset_store: Optional[Any] = None,
) -> CliAdapterPlugin:
    """
    Initialize the CLI adapter plugin.
    
    Args:
        transcript_store: The transcript store for audit
        cognitive_registry: The cognitive tool registry
        execution_registry: The execution domain registry
        asset_store: Optional asset store
    
    Returns:
        Initialized CliAdapterPlugin
    
    ⚠️ ARCHITECTURAL: Directly instantiates CliAdapterPlugin and related classes.
    Should be migrated to CliIntegrationService API.
    """
    adapter = CliAdapterPlugin(
        plugin_id="cli-adapter-dev",
        version="1.0.0",
        feature_code="external.cli",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["cli_adapter_regression"],
        revocation_reasons=["cli_adapter_disabled"],
    )
    adapter.attach_runtime(
        transport=SubprocessCliTransport(),
        transcript_store=transcript_store,
    )
    adapter.register_tool(
        CliToolRegistrationConfig(
            tool_name="repo_echo_probe",
            command_executable="/bin/echo",
            description="Read-only shell probe for CLI integration smoke tests.",
            read_only_flag=True,
            project_path=".",
            project_name="AnimoCerebro",
            project_description="Zentex workspace shell probe",
        )
    )
    return adapter


def setup_weight_assembler() -> WeightPluginAssembler:
    """
    Initialize the weight plugin assembler.
    
    Returns:
        Configured WeightPluginAssembler
    
    ⚠️ ARCHITECTURAL: Directly instantiates WeightPluginAssembler.
    Should be migrated to a WeightService API.
    """
    from unittest.mock import Mock
    from zentex.plugins.audit_client import RationalAuditRejectError
    from zentex.admin.bootstrap_plugins import build_creative_exploration_weight
    
    audit_client = Mock()
    audit_client.evaluate.side_effect = RationalAuditRejectError(
        "G25 rejected the candidate weight plugin due to unsafe creative drift."
    )
    assembler = WeightPluginAssembler(audit_client=audit_client)
    assembler.mount_plugin(build_creative_exploration_weight())
    return assembler


def setup_task_management(
    transcript_store: BrainTranscriptStore,
    *,
    managed_plugins: List[object],
    asset_store: Optional[Any] = None,
) -> TaskManagementService:
    """
    Initialize the task management service.
    
    Args:
        transcript_store: The transcript store for audit
        managed_plugins: List of managed plugins
        asset_store: Optional asset store
    
    Returns:
        Configured TaskManagementService
    
    ⚠️ ARCHITECTURAL: Directly instantiates TaskRegistry.
    Should use pure TaskManagementService API.
    """
    registry = TaskRegistry()
    # Prefer LLM-backed mission decomposition for task splitting
    model_provider = next(
        record.plugin
        for record in managed_plugins
        if getattr(record.plugin, "plugin_kind", lambda: "")() == "model_provider"
    )
    service = TaskManagementService(
        registry,
        transcript_store,
        decomposer=LLMTaskDecomposerPlugin(
            model_provider=model_provider,
            transcript_store=transcript_store,
        ),
        store=asset_store,
    )
    return service


def create_mcp_and_cli_services(
    mcp_adapter: Optional[Any] = None,
    cli_adapter: Optional[Any] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Create MCP and CLI integration services from adapters.
    
    This encapsulates the service instantiation to prevent web_dev.py from
    directly importing McpIntegrationService and CliIntegrationService.
    
    Args:
        mcp_adapter: Optional MCP adapter instance
        cli_adapter: Optional CLI adapter instance
        
    Returns:
        Tuple of (mcp_service, cli_service)
        
    ⚠️ ARCHITECTURAL: This isolates direct imports from zentex.mcp.service
    and zentex.cli.service to maintain module isolation principles.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    mcp_service = None
    cli_service = None
    
    try:
        from zentex.mcp.service import McpIntegrationService
        from zentex.cli.service import CliIntegrationService
        
        if mcp_adapter is not None:
            mcp_service = McpIntegrationService(adapter=mcp_adapter)
            # Log MCP server count for debugging
            mcp_servers = mcp_service.list_servers()
            logger.info(f"[Nine Questions Q3] MCP servers count: {len(mcp_servers)}")
            if len(mcp_servers) > 0:
                for srv in mcp_servers:
                    logger.info(f"  - MCP Server: {srv.get('server_id')} ({srv.get('tool_count')} tools)")
            else:
                logger.warning("[Nine Questions Q3] No MCP servers registered. Q3 data may be incomplete.")
        
        if cli_adapter is not None:
            cli_service = CliIntegrationService(adapter=cli_adapter)
            # Log CLI tools count for debugging
            cli_tools = cli_service.list_tools()
            logger.info(f"[Nine Questions Q3] CLI tools count: {len(cli_tools)}")
            if len(cli_tools) > 0:
                for tool in cli_tools:
                    logger.info(f"  - CLI Tool: {tool.get('command_name')} -> {tool.get('plugin_id')}")
    except Exception as exc:
        logger.warning(f"Failed to create MCP/CLI integration services: {exc}")
    
    return mcp_service, cli_service
