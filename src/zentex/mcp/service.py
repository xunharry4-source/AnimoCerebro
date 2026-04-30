from __future__ import annotations

"""Public MCP integration facade used by external callers."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.common.storage_paths import get_storage_paths
from zentex.agents.auth import AgentAuthService
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.mcp.models import (
    McpServerConfig,
    McpServerRuntimeState,
    McpToolBindingConfig,
    McpToolDescriptor,
)
from zentex.mcp.adapter import McpAdapterPlugin, create_mcp_adapter_plugin
from zentex.supervision.service import get_ai_supervisor, VerificationStatus
from zentex.tools.documentation_learning import (
    McpDocumentationInput,
    ToolDocumentationLearningError,
    ToolDocumentationLearningService,
)
from zentex.tasks.execution.external_result_bridge import (
    mark_external_execution_started,
    write_external_execution_result,
)

logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        adapter: McpAdapterPlugin,
        task_service: Any = None,
        documentation_learning_service: Optional[ToolDocumentationLearningService] = None,
        llm_service: Any = None,
        auth_service: Optional[AgentAuthService] = None,
        registry_path: Path | str | None = None,
        registry_store: ExternalCapabilityRegistryStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._auth_service = auth_service
        if auth_service is not None and hasattr(self._adapter, "attach_auth_service"):
            self._adapter.attach_auth_service(auth_service)
        self._task_service = task_service
        self._documentation_learning_service = documentation_learning_service or ToolDocumentationLearningService(
            llm_service=llm_service
        )
        self._usage_profiles: Dict[str, Any] = {}
        self._registry_path = Path(registry_path) if registry_path is not None else get_storage_paths().runtime_data_dir / "mcp_servers.json"
        self._registry_store = registry_store or ExternalCapabilityRegistryStore()
        self._restore_errors: Dict[str, str] = {}
        self._restore_registered_servers()

    def store_server_credential(
        self,
        server_id: str,
        *,
        credential_type: str,
        secret_payload: Dict[str, Any],
        credential_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Any:
        if self._auth_service is None:
            raise RuntimeError("MCP auth credential registration requires AgentAuthService")
        return self._auth_service.store_credential(
            agent_id=f"mcp:{server_id}",
            owner_type="mcp",
            owner_id=server_id,
            credential_type=credential_type,
            secret_payload=secret_payload,
            credential_id=credential_id,
            metadata=metadata,
        )

    def attach_task_service(self, task_service: Any) -> None:
        self._task_service = task_service

    def list_servers(self) -> List[McpServerRuntimeState]:
        states = list(self._adapter.list_server_states())
        seen = {state.server_id for state in states}
        for row in self._registry_store.list_current("mcp"):
            if row["asset_id"] in seen:
                continue
            try:
                config = McpServerConfig.model_validate(row["payload"])
                states.append(
                    McpServerRuntimeState(
                        server_id=config.server_id,
                        transport_type=config.transport_type,
                        status="degraded",
                        tool_count=0,
                        error_message=self._restore_errors.get(config.server_id) or "registered MCP server is persisted but not active in runtime",
                        tools=[],
                    )
                )
            except Exception as exc:
                states.append(
                    McpServerRuntimeState(
                        server_id=str(row["asset_id"]),
                        transport_type="stdio",
                        status="degraded",
                        tool_count=0,
                        error_message=f"persisted MCP server payload is invalid: {exc}",
                        tools=[],
                    )
                )
        return states

    def register_server(self, config: McpServerConfig) -> McpServerRuntimeState:
        state = self._adapter.register_server(config)
        self._learn_usage_profiles_after_registration(config=config, state=state)
        restored_state = self._adapter._server_states.get(config.server_id, state) if hasattr(self._adapter, "_server_states") else state
        self._persist_registered_servers()
        self._registry_store.upsert_current(
            "mcp",
            config.server_id,
            config.model_dump(mode="json"),
            status=restored_state.status,
            display_name=config.server_id,
            action="register",
        )
        return restored_state

    def _learn_usage_profiles_after_registration(
        self,
        *,
        config: McpServerConfig,
        state: McpServerRuntimeState,
    ) -> None:
        if not config.documentation_learning_required or not state.tools:
            return
        fetched_doc = ""
        if config.help_doc_url:
            try:
                fetched_doc = self._documentation_learning_service.fetch_mcp_doc(config)
            except Exception:
                fetched_doc = ""
        updated_tools = []
        degraded = False
        for runtime_tool in state.tools:
            schema_snapshot = getattr(self._adapter, "_tool_schema_cache", {}).get(config.server_id, {}).get(runtime_tool.tool_name, {})
            descriptor = McpToolDescriptor(
                tool_name=runtime_tool.tool_name,
                description=runtime_tool.description,
                input_schema=dict(schema_snapshot.get("input_schema") or {}),
                mutates_state=runtime_tool.mutates_state,
                read_only_hint=runtime_tool.read_only,
            )
            try:
                profile = self._documentation_learning_service.learn_mcp_tool_usage_profile(
                    McpDocumentationInput(config=config, tool=descriptor, fetched_doc=fetched_doc)
                )
                self._usage_profiles[f"{config.server_id}:{runtime_tool.tool_name}"] = profile
                updated_tools.append(runtime_tool)
            except Exception as exc:
                if runtime_tool.mutates_state or not runtime_tool.read_only:
                    self._adapter.delete_server(config.server_id)
                    raise ToolDocumentationLearningError(
                        f"documentation learning failed for execution MCP tool "
                        f"'{config.server_id}/{runtime_tool.tool_name}': {exc}"
                    ) from exc
                degraded = True
                updated_tools.append(runtime_tool.model_copy(update={"status": "degraded"}))
        if degraded and hasattr(self._adapter, "_server_states"):
            self._adapter._server_states[config.server_id] = state.model_copy(
                update={
                    "status": "degraded",
                    "error_message": "one or more read-only MCP tools lack learned usage profiles",
                    "tools": updated_tools,
                }
            )

    def get_tool_usage_profile(self, server_id: str, tool_name: str) -> Any:
        profile = self._usage_profiles.get(f"{server_id}:{tool_name}")
        if profile is None:
            raise KeyError(f"{server_id}:{tool_name}")
        return profile

    def list_usage_profiles(self) -> Dict[str, Any]:
        return dict(self._usage_profiles)

    def activate_server(self, server_id: str) -> McpServerRuntimeState:
        return self._adapter.activate_server(server_id)

    def disable_server(self, server_id: str) -> McpServerRuntimeState:
        return self._adapter.disable_server(server_id)

    def delete_server(self, server_id: str) -> bool:
        deleted = self._adapter.delete_server(server_id)
        if deleted:
            prefix = f"{server_id}:"
            for key in list(self._usage_profiles):
                if key.startswith(prefix):
                    self._usage_profiles.pop(key, None)
            self._persist_registered_servers()
            self._registry_store.delete_current("mcp", server_id)
        return deleted

    def _restore_registered_servers(self) -> None:
        if not hasattr(self._adapter, "server_configs"):
            return
        db_rows = self._registry_store.list_current("mcp")
        if db_rows:
            payload = [row["payload"] for row in db_rows]
        elif self._registry_path.exists():
            try:
                payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to read persisted MCP registry from %s: %s", self._registry_path, exc)
                raise RuntimeError(f"failed to read persisted MCP registry: {exc}") from exc
            if not isinstance(payload, list):
                raise RuntimeError("persisted MCP registry must be a list")
        else:
            return
        if not isinstance(payload, list):
            raise RuntimeError("persisted MCP registry must be a list")
        for item in payload:
            config = McpServerConfig.model_validate(item)
            if any(existing.server_id == config.server_id for existing in self._adapter.server_configs):
                continue
            try:
                state = self._adapter.register_server(config)
                self._restore_errors.pop(config.server_id, None)
                if not db_rows:
                    self._registry_store.upsert_current(
                        "mcp",
                        config.server_id,
                        config.model_dump(mode="json"),
                        status=state.status,
                        display_name=config.server_id,
                        action="import_json_registry",
                    )
            except Exception as exc:
                self._restore_errors[config.server_id] = str(exc)
                if not db_rows:
                    self._registry_store.upsert_current(
                        "mcp",
                        config.server_id,
                        config.model_dump(mode="json"),
                        status="degraded",
                        display_name=config.server_id,
                        action="import_json_registry_degraded",
                    )
                logger.warning("Persisted MCP server '%s' restored as degraded: %s", config.server_id, exc)

    def _persist_registered_servers(self) -> None:
        if not hasattr(self._adapter, "server_configs"):
            return
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [config.model_dump(mode="json") for config in self._adapter.server_configs]
        self._registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

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
        started_at = datetime.now(timezone.utc)
        effective_trace_id = trace_id or f"mcp-test:{uuid4().hex}"
        result = self._adapter.invoke_tool(
            server_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            trace_id=effective_trace_id,
        )
        finished_at = datetime.now(timezone.utc)
        
        # 1. Basic type safety
        if not isinstance(result, dict):
            normalized = {
                "status": "failed", 
                "error_code": "malformed_adapter_response", 
                "error_message": "Adapter returned non-dict payload.",
                "raw_result": result,
                "_execution_contract": True
            }
            self._registry_store.append_runtime_log(
                "mcp",
                server_id,
                capability_name=tool_name,
                invocation_type="test_call",
                status="failed",
                request={"tool_name": tool_name, "arguments": dict(arguments or {})},
                response=normalized,
                error_message=normalized["error_message"],
                trace_id=effective_trace_id,
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
            )
            return normalized
        
        # 2. Reify status with contract awareness
        if result.get("_execution_contract") is True:
            # Already a contract, just ensure trace_id is present
            if trace_id and "trace_id" not in result:
                result["trace_id"] = trace_id
            self._registry_store.append_runtime_log(
                "mcp",
                server_id,
                capability_name=tool_name,
                invocation_type="test_call",
                status=str(result.get("status") or "unknown"),
                request={"tool_name": tool_name, "arguments": dict(arguments or {})},
                response=result,
                error_message=result.get("error_message") or result.get("error"),
                trace_id=str(result.get("trace_id") or effective_trace_id),
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
            )
            return result

        # 3. Fallback normalization for non-contract adapters
        status = "completed" if "error" not in result else "failed"
        normalized = {
            "status": status,
            "error_code": result.get("error_code") if status == "failed" else None,
            "error_message": result.get("error_message") or result.get("error") if status == "failed" else None,
            "data": result if status == "completed" else result.get("data", {}),
            "trace_id": trace_id,
            "_execution_contract": True
        }
        self._registry_store.append_runtime_log(
            "mcp",
            server_id,
            capability_name=tool_name,
            invocation_type="test_call",
            status=status,
            request={"tool_name": tool_name, "arguments": dict(arguments or {})},
            response=normalized,
            error_message=normalized.get("error_message"),
            trace_id=effective_trace_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )
        return normalized

    async def execute_task(
        self,
        *,
        task_service: Any,
        task_id: str,
        trace_id: str,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Optional[Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a task-center dispatched MCP call and write back the result.

        This is the Zentex host-side execution path.  task_id and trace_id are
        used for Zentex lifecycle/audit only; only the MCP tool arguments are
        sent to the external MCP server.
        """
        resolved_task_service = task_service or self._task_service
        executor_metadata = {
            "mcp_server_id": server_id,
            "mcp_tool_name": tool_name,
            "executor_type": "mcp",
        }
        await mark_external_execution_started(
            task_service=resolved_task_service,
            task_id=task_id,
            trace_id=trace_id,
            executor_type="mcp",
            executor_metadata=executor_metadata,
        )

        result = await asyncio.to_thread(
            self.test_call,
            server_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            trace_id=trace_id,
        )
        result_payload = dict(result)
        status = str(result_payload.get("status") or "")
        succeeded = status == "completed"
        error_message = None if succeeded else (
            result_payload.get("error_message")
            or result_payload.get("error")
            or f"MCP tool '{server_id}/{tool_name}' failed with status {status or 'unknown'}"
        )

        writeback = await write_external_execution_result(
            task_service=resolved_task_service,
            task_id=task_id,
            trace_id=trace_id,
            executor_type="mcp",
            executor_metadata=executor_metadata,
            result_payload=result_payload,
            succeeded=succeeded,
            error_message=str(error_message) if error_message else None,
        )
        return {
            "succeeded": succeeded,
            "task_center_synchronized": True,
            "task_id": task_id,
            "trace_id": trace_id,
            "executor_type": "mcp",
            "executor_id": f"mcp:{server_id}:{tool_name}",
            "output": result_payload,
            "error": str(error_message) if error_message else None,
            "duration_seconds": 0.0,
            "failure_classification": result_payload.get("error_code"),
            "task_writeback": writeback,
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

def get_service(llm_service: Any = None) -> McpIntegrationService:
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
        if llm_service is None:
            try:
                from zentex.llm.service import get_service as get_llm_service

                llm_service = get_llm_service()
            except Exception:
                llm_service = None
        return McpIntegrationService(
            adapter=adapter,
            llm_service=llm_service,
            auth_service=AgentAuthService(),
        )
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
