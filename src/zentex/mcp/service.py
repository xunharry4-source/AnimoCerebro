from __future__ import annotations

"""Public MCP integration facade used by external callers."""

from typing import Any, Dict, List
from uuid import uuid4

from zentex.mcp.models import (
    McpServerConfig,
    McpServerRuntimeState,
    McpToolBindingConfig,
    McpToolDescriptor,
)
from zentex.mcp.adapter import McpAdapterPlugin, FakeMcpTransportClient, create_mcp_adapter_plugin
from zentex.supervision.service import get_ai_supervisor, VerificationStatus


class McpIntegrationService:
    def __init__(self, adapter: McpAdapterPlugin) -> None:
        self._adapter = adapter

    def list_servers(self) -> List[McpServerRuntimeState]:
        return self._adapter.list_server_states()

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        return self._adapter.register_server(config)

    def test_call(
        self,
        server_id: str,
        *,
        tool_name: str,
        arguments: Dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Dict[str, Any]:
        return self._adapter.invoke_tool(
            server_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            trace_id=trace_id or f"mcp-test:{uuid4().hex}",
        )

    def get_server_detail(self, server_id: str) -> Any:
        # Use local import from core contracts to maintain architectural clean separation
        from zentex.mcp.contracts import McpServerDetailItem, McpServerToolItem

        state = next((s for s in self.list_servers() if s.server_id == server_id), None)
        if not state:
            raise KeyError(f"Server {server_id} not found")

        # Aggregate supervision data
        supervisor = get_ai_supervisor()
        records = [
            r for r in supervisor.execution_records.values()
            if r.parameters.get("server_id") == server_id
        ]
        
        failed_count = sum(1 for r in records if r.status == "failed")
        success_rate = (len(records) - failed_count) / len(records) if records else 1.0
        credit_score = max(0, 100 - (failed_count * 5))
        
        # Calculate uptime based on task records or use placeholder
        # TODO: Add started_at field to McpServerRuntimeState for accurate uptime
        if records:
            # Use the earliest task start time as approximate server start time
            from datetime import datetime, timezone
            earliest_start = min(r.start_time for r in records)
            now = datetime.now(timezone.utc)
            if earliest_start.tzinfo is None:
                earliest_start = earliest_start.replace(tzinfo=timezone.utc)
            uptime = max(0, int((now - earliest_start).total_seconds()))
        else:
            # No tasks yet, use placeholder
            uptime = 3600

        return McpServerDetailItem(
            server_id=state.server_id,
            transport_type=state.transport_type,
            status=state.status,
            tool_count=state.tool_count,
            credit_score=credit_score,
            total_tasks_run=len(records),
            success_rate=success_rate,
            uptime_seconds=uptime,
            error_message=state.error_message,
            tools=[
                McpServerToolItem(
                    tool_name=t.tool_name,
                    description=t.description,
                    mapped_domain=t.mapped_domain,
                    mcp_id=t.mcp_id,
                    feature_code=t.feature_code,
                    execution_domain=t.execution_domain,
                    read_only=t.read_only,
                    side_effect_free=t.side_effect_free,
                    mutates_state=t.mutates_state,
                    requires_cloud_audit=t.requires_cloud_audit,
                    status=t.status,
                )
                for t in state.tools
            ]
        )

    def list_server_tasks(self, server_id: str, status: str | None = None) -> List[Any]:
        from zentex.mcp.contracts import McpTaskSummary

        supervisor = get_ai_supervisor()
        records = [
            r for r in supervisor.execution_records.values()
            if r.parameters.get("server_id") == server_id
        ]
        
        if status:
            records = [r for r in records if r.status == status]
            
        summaries = []
        for r in records:
            duration = None
            if r.end_time:
                duration = (r.end_time - r.start_time).total_seconds()
            
            # Aggregate verification status
            v_status = "passed"
            if any(vs == VerificationStatus.FAILED for vs in r.verification_results.values()):
                v_status = "failed"
            elif any(vs == VerificationStatus.PENDING for vs in r.verification_results.values()):
                v_status = "pending"

            summaries.append(McpTaskSummary(
                record_id=r.record_id,
                task_id=r.task_id,
                action_type=r.action_type,
                status=r.status,
                start_time=r.start_time.isoformat(),
                end_time=r.end_time.isoformat() if r.end_time else None,
                duration_seconds=duration,
                verification_status=v_status,
                error=r.error
            ))
        return sorted(summaries, key=lambda x: x.start_time, reverse=True)

def get_service() -> McpIntegrationService | None:
    """Standard service factory function for launcher assembly.
    
    Returns a configured McpIntegrationService. This factory is resilient
    to missing global dependencies during the early assembly phase.
    """
    try:
        # Use local imports for dependencies
        from zentex.mcp.adapter import create_mcp_adapter_plugin
        from zentex.kernel import BrainTranscriptStore
        from zentex.plugins.service import CognitiveToolRegistry
        
        # MCP routes need a working transcript store / cognitive registry even
        # during assembly; otherwise cognitive MCP tools are silently dropped
        # and list/detail responses lose their tool metadata.
        transcript_store = BrainTranscriptStore(".zentex/mcp_transcript.jsonl")
        cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)

        adapter, _ = create_mcp_adapter_plugin(
            transcript_store=transcript_store,
            cognitive_registry=cognitive_registry,
            defer_sync=True
        )
        return McpIntegrationService(adapter=adapter)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("MCP assembly failed (non-critical): %s", exc)
        return None


__all__ = [
    "McpIntegrationService",
    "McpAdapterPlugin",
    "FakeMcpTransportClient",
    "create_mcp_adapter_plugin",
    "McpServerConfig",
    "McpServerRuntimeState",
    "McpToolBindingConfig",
    "McpToolDescriptor",
]
