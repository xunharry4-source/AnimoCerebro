from __future__ import annotations

"""Public MCP integration facade used by external callers."""

from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.common.storage_paths import get_storage_paths
from zentex.mcp.models import (
    McpServerConfig,
    McpServerRuntimeState,
    McpToolBindingConfig,
    McpToolDescriptor,
)
from zentex.mcp.adapter import McpAdapterPlugin, create_mcp_adapter_plugin
from zentex.supervision.service import get_ai_supervisor, VerificationStatus


class _AssemblyFailedAdapter:
    """Fail-closed MCP adapter used when service assembly cannot complete."""

    def __init__(self, error_message: str) -> None:
        self._error_message = error_message

    def list_server_states(self) -> List[McpServerRuntimeState]:
        return [
            McpServerRuntimeState(
                server_id="mcp-assembly",
                transport_type="stdio",
                status="degraded",
                tool_count=0,
                error_message=self._error_message,
                tools=[],
            )
        ]

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        raise RuntimeError(self._error_message)

    def invoke_tool(
        self,
        server_id: str,
        *,
        tool_name: str,
        arguments: Dict[str, Optional[Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "error_code": "SERVICE_UNAVAILABLE",
            "error_message": f"MCP service assembly failed: {self._error_message}",
            "server_id": server_id,
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "trace_id": trace_id,
            "_execution_contract": True,
        }

    def diagnose_mcp_management_closure(self) -> Dict[str, Any]:
        from zentex.mcp.lifecycle_diagnostics import build_mcp_unavailable_diagnostic_report

        return build_mcp_unavailable_diagnostic_report(self._error_message)

    def run_mcp_fault_injection_matrix(self) -> Dict[str, Any]:
        from zentex.mcp.lifecycle_diagnostics import build_mcp_unavailable_fault_report

        return build_mcp_unavailable_fault_report(self._error_message)


class McpIntegrationService:
    def __init__(self, adapter: McpAdapterPlugin) -> None:
        self._adapter = adapter

    def list_servers(self) -> List[McpServerRuntimeState]:
        return self._adapter.list_server_states()

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        return self._adapter.register_server(config)

    def activate_server(self, server_id: str) -> McpServerRuntimeState:
        return self._adapter.activate_server(server_id)

    def disable_server(self, server_id: str) -> McpServerRuntimeState:
        return self._adapter.disable_server(server_id)

    def delete_server(self, server_id: str) -> bool:
        return self._adapter.delete_server(server_id)

    def get_server_health(self, server_id: str) -> Dict[str, Any]:
        return self._adapter.get_server_health(server_id)

    def diagnose_mcp_management_closure(self) -> Dict[str, Any]:
        return self._adapter.diagnose_mcp_management_closure()

    def run_mcp_fault_injection_matrix(self) -> Dict[str, Any]:
        return self._adapter.run_mcp_fault_injection_matrix()

    def test_call(
        self,
        server_id: str,
        *,
        tool_name: str,
        arguments: Dict[str, Optional[Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """G21: Normalize adapter result and respect execution contract."""
        result = self._adapter.invoke_tool(
            server_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            trace_id=trace_id or f"mcp-test:{uuid4().hex}",
        )
        
        # 1. Basic type safety
        if not isinstance(result, dict):
            return {
                "status": "failed", 
                "error_code": "malformed_adapter_response", 
                "error_message": "Adapter returned non-dict payload.",
                "raw_result": result,
                "_execution_contract": True
            }
        
        # 2. Reify status with contract awareness
        if result.get("_execution_contract") is True:
            # Already a contract, just ensure trace_id is present
            if trace_id and "trace_id" not in result:
                result["trace_id"] = trace_id
            return result

        # 3. Fallback normalization for non-contract adapters
        status = "completed" if "error" not in result else "failed"
        return {
            "status": status,
            "error_code": result.get("error_code") if status == "failed" else None,
            "error_message": result.get("error_message") or result.get("error") if status == "failed" else None,
            "data": result if status == "completed" else result.get("data", {}),
            "trace_id": trace_id,
            "_execution_contract": True
        }

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

        # POLICY[no-fake-impl]: all metrics are None when there is no execution history.
        # Callers must treat None as "no data" and never display it as 100 / 1.0.
        if records:
            from datetime import datetime, timezone
            success_rate: Optional[float] = (len(records) - failed_count) / len(records)
            credit_score: Optional[int] = max(0, 100 - (failed_count * 5))
            earliest_start = min(r.start_time for r in records)
            now = datetime.now(timezone.utc)
            if earliest_start.tzinfo is None:
                earliest_start = earliest_start.replace(tzinfo=timezone.utc)
            uptime: Optional[int] = max(0, int((now - earliest_start).total_seconds()))
        else:
            success_rate = None   # no execution history
            credit_score = None   # no execution history
            uptime = None         # no execution history

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

    def list_server_tasks(self, server_id: str, status: Optional[str] = None) -> List[Any]:
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

def get_service() -> McpIntegrationService:
    """Standard service factory function for launcher assembly.
    
    Returns a configured McpIntegrationService. This factory is resilient
    to missing global dependencies during the early assembly phase.
    """
    try:
        from zentex.kernel import AuditEventStore
        from zentex.plugins.service import CognitiveToolRegistry
        
        # MCP routes need a working transcript store / cognitive registry even
        # during assembly; otherwise cognitive MCP tools are silently dropped
        # and list/detail responses lose their tool metadata.
        transcript_store = AuditEventStore(get_storage_paths().mcp_audit_db)
        cognitive_registry = CognitiveToolRegistry(transcript_store=transcript_store)

        adapter, _ = create_mcp_adapter_plugin(
            transcript_store=transcript_store,
            cognitive_registry=cognitive_registry,
            defer_sync=True
        )
        return McpIntegrationService(adapter=adapter)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("MCP assembly failed (degraded): %s", exc)
        return McpIntegrationService(adapter=_AssemblyFailedAdapter(str(exc)))


__all__ = [
    "McpIntegrationService",
    "McpAdapterPlugin",
    "create_mcp_adapter_plugin",
    "McpServerConfig",
    "McpServerRuntimeState",
    "McpToolBindingConfig",
    "McpToolDescriptor",
]
