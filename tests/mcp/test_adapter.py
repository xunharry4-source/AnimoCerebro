from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.mcp import McpServerConfig, McpToolBindingConfig, McpToolDescriptor
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.mcp.adapter import FakeMcpTransportClient, McpAdapterPlugin
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.transcript import BrainTranscriptStore


def build_adapter(
    *,
    configs: list[McpServerConfig],
    transport_factory,
) -> tuple[McpAdapterPlugin, CognitiveToolRegistry, ExecutionDomainRegistry]:
    transcript_store = BrainTranscriptStore(Path("/tmp") / "mcp-adapter-test.jsonl")
    cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)
    execution_registry = ExecutionDomainRegistry()
    adapter = McpAdapterPlugin(
        plugin_id="mcp-adapter-test",
        version="1.0.0",
        feature_code="external.mcp",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_adapter_regression"],
        revocation_reasons=["mcp_adapter_disabled"],
        health_probe_endpoint="mcp://health",
        server_configs=configs,
    )
    adapter.attach_runtime(
        client_factory=transport_factory,
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    return adapter, cognitive_registry, execution_registry


def test_mcp_adapter_blocks_mutating_tool_from_cognitive_domain() -> None:
    config = McpServerConfig(
        server_id="rogue-server",
        transport_type="stdio",
        command="rogue-mcp",
        tool_bindings=[
            McpToolBindingConfig(
                tool_name="write_file",
                domain="cognitive",
                read_only=True,
                side_effect_free=True,
                mutates_state=False,
            )
        ],
    )
    transport = FakeMcpTransportClient(
        tools=[
            McpToolDescriptor(
                tool_name="write_file",
                description="Write content into local file",
                input_schema={"type": "object"},
                mutates_state=True,
                read_only_hint=False,
            )
        ]
    )
    adapter, _, _ = build_adapter(configs=[config], transport_factory=lambda _: transport)

    with pytest.raises(ValidationError):
        adapter.sync_servers()


def test_mcp_adapter_degrades_crashed_server_without_blocking_other_servers() -> None:
    good = McpServerConfig(server_id="good", transport_type="stdio", command="good-mcp")
    bad = McpServerConfig(server_id="bad", transport_type="sse", command="bad-mcp")

    def factory(config: McpServerConfig):
        if config.server_id == "bad":
            return FakeMcpTransportClient(tools=[], fail_with=TimeoutError("mcp transport disconnected"))
        return FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="search_documents",
                    description="Search documents",
                    input_schema={"type": "object"},
                    mutates_state=False,
                )
            ],
            healthy=True,
        )

    adapter, cognitive_registry, _ = build_adapter(configs=[bad, good], transport_factory=factory)

    states = adapter.sync_servers()

    bad_state = next(item for item in states if item.server_id == "bad")
    assert bad_state.status == "degraded"
    assert "disconnected" in str(bad_state.error_message)

    good_state = next(item for item in states if item.server_id == "good")
    assert good_state.status == "online"
    assert good_state.tool_count == 1
    assert adapter.health_probe() == PluginHealthStatus.DEGRADED
    assert any(reg.plugin_id == "mcp:good:search_documents" for reg in cognitive_registry.list_registrations())
