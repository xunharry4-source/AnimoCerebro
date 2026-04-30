from __future__ import annotations

"""Public CLI integration facade used by web and runtime callers."""

import logging
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from zentex.common.storage_paths import get_storage_paths
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.cli.adapter import CliAdapterPlugin, create_cli_adapter_plugin
from zentex.cli.adapter import SubprocessCliTransport
from zentex.cli.models import CliInvocationResult, CliToolRegistrationConfig, CliToolRuntimeState
from zentex.agents.auth import AgentAuthService
from zentex.foundation.contracts.service_response import ServiceResponse, ServiceErrorCode, ServiceStatus
from zentex.tools.documentation_learning import (
    ToolDocumentationLearningError,
    ToolDocumentationLearningService,
)
from zentex.tasks.execution.external_result_bridge import (
    mark_external_execution_started,
    write_external_execution_result,
)

PLAYWRIGHT_CLI_TOOL_CONFIG = CliToolRegistrationConfig(
    tool_name="playwright-cli",
    command_executable="npx",
    command_args=["--no-install", "playwright-cli"],
    description=(
        "Playwright command-line interface for browser automation, "
        "E2E testing, screenshots, tracing, and related execution tasks."
    ),
    read_only_flag=False,
    help_doc_url="https://github.com/microsoft/playwright-cli",
    project_name="Playwright",
    project_description="Host-side Playwright CLI exposed as a controlled Zentex CLI execution tool.",
    execution_domain="cli",
    health_probe_args=["--version"],
    help_probe_args=["--help"],
    version_probe_args=["--version"],
)


class CliIntegrationService:
    def __init__(
        self,
        adapter: CliAdapterPlugin,
        transcript_store: Any = None,
        task_service: Any = None,
        documentation_learning_service: Optional[ToolDocumentationLearningService] = None,
        llm_service: Any = None,
        auth_service: Optional[AgentAuthService] = None,
        registry_path: Path | str | None = None,
        registry_store: ExternalCapabilityRegistryStore | None = None,
    ) -> None:
        self._adapter = adapter
        if auth_service is not None:
            self._adapter.attach_auth_service(auth_service)
        self._transcript_store = transcript_store
        self._task_service = task_service
        self._documentation_learning_service = documentation_learning_service or ToolDocumentationLearningService(
            llm_service=llm_service
        )
        self._usage_profiles: Dict[str, Any] = {}
        self._registry_path = Path(registry_path) if registry_path is not None else get_storage_paths().runtime_data_dir / "cli_tools.json"
        self._registry_store = registry_store or ExternalCapabilityRegistryStore()
        self._restore_registered_tools()

    def attach_task_service(self, task_service: Any) -> None:
        self._task_service = task_service

    def list_tools(self) -> List[CliToolRuntimeState]:
        return self._adapter.list_tool_states()

    def register_tool(self, config: CliToolRegistrationConfig) -> ServiceResponse:
        try:
            state = self._adapter.register_tool(config)
            self._learn_usage_profile_after_registration(config=config, state=state)
            state = next(
                (item for item in self._adapter.list_tool_states() if item.command_name == config.tool_name),
                state,
            )
            self._persist_registered_tools()
            self._registry_store.upsert_current(
                "cli",
                config.tool_name,
                config.model_dump(mode="json"),
                status=state.status,
                display_name=config.tool_name,
                action="register",
            )
            return ServiceResponse.ok(data=state)
        except (FileNotFoundError, ValueError, ToolDocumentationLearningError) as e:
            if isinstance(e, ValueError) and "already registered" in str(e):
                existing_config = getattr(self._adapter, "_registered_tools", {}).get(config.tool_name)
                if existing_config is not None and existing_config.model_dump(mode="json") == config.model_dump(mode="json"):
                    state = next(
                        (item for item in self._adapter.list_tool_states() if item.command_name == config.tool_name),
                        None,
                    )
                    if state is not None:
                        if config.tool_name not in self._usage_profiles:
                            self._learn_usage_profile_after_registration(config=config, state=state)
                        self._persist_registered_tools()
                        self._registry_store.upsert_current(
                            "cli",
                            config.tool_name,
                            config.model_dump(mode="json"),
                            status=state.status,
                            display_name=config.tool_name,
                            action="register_idempotent",
                        )
                        return ServiceResponse.ok(data=state)
            # Validation / reachability failures are expected; log at WARNING.
            message = str(e)
            error_code = (
                ServiceErrorCode.STATE_CONFLICT
                if isinstance(e, ValueError) and "already registered" in message
                else ServiceErrorCode.INVALID_ARGUMENT
            )
            logger.warning(
                "CLI tool registration rejected for '%s': %s",
                config.tool_name,
                e,
            )
            return ServiceResponse.error(
                code=error_code,
                message=f"Failed to register CLI tool '{config.tool_name}': {e}",
            )
        except Exception as e:
            logger.error(
                "CLI tool registration failed unexpectedly for '%s'",
                config.tool_name, exc_info=True,
            )
            return ServiceResponse.error(
                code=ServiceErrorCode.INVALID_ARGUMENT,
                message=f"Failed to register CLI tool '{config.tool_name}': {e}",
            )

    def _learn_usage_profile_after_registration(
        self,
        *,
        config: CliToolRegistrationConfig,
        state: CliToolRuntimeState,
    ) -> None:
        if not config.documentation_learning_required:
            return
        try:
            doc_input = self._documentation_learning_service.collect_cli_input(config)
            profile = self._documentation_learning_service.learn_cli_usage_profile(doc_input)
        except Exception as exc:
            if state.mutates_state or not state.read_only:
                self._adapter.delete_tool(config.tool_name)
                raise ToolDocumentationLearningError(
                    f"documentation learning failed for execution CLI tool '{config.tool_name}': {exc}"
                ) from exc
            degraded = state.model_copy(update={"status": "degraded"})
            if hasattr(self._adapter, "_tool_states"):
                self._adapter._tool_states[config.tool_name] = degraded
            elif hasattr(self._adapter, "states"):
                self._adapter.states[config.tool_name] = degraded
            logger.warning(
                "CLI tool '%s' registered as degraded because documentation learning failed: %s",
                config.tool_name,
                exc,
            )
            return
        self._usage_profiles[config.tool_name] = profile

    def get_usage_profile(self, tool_name: str) -> Any:
        profile = self._usage_profiles.get(tool_name)
        if profile is None:
            raise KeyError(tool_name)
        return profile

    def list_usage_profiles(self) -> Dict[str, Any]:
        return dict(self._usage_profiles)

    def test_call(
        self,
        tool_name: str,
        *,
        arguments: List[Optional[str]] = None,
        stdin_input: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> ServiceResponse:
        started_at = datetime.now(timezone.utc)
        result = self._adapter.invoke_tool(
            tool_name,
            arguments=arguments,
            stdin_input=stdin_input,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        finished_at = datetime.now(timezone.utc)
        self._registry_store.append_runtime_log(
            "cli",
            tool_name,
            capability_name=tool_name,
            invocation_type="test_call",
            status=result.status,
            request={
                "arguments": arguments or [],
                "stdin_supplied": stdin_input is not None,
                "working_directory": working_directory,
                "timeout_seconds": timeout_seconds,
            },
            response=result.model_dump(mode="json"),
            error_message=result.stderr if result.status != "success" else None,
            trace_id=result.trace_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=result.duration_ms,
        )
        return self._map_invocation_result(result)

    async def execute_task(
        self,
        *,
        task_service: Any,
        task_id: str,
        trace_id: str,
        tool_name: str,
        arguments: List[Optional[str]] = None,
        stdin_input: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """Execute a task-center dispatched CLI call and write back the result.

        This method is for Zentex internal task dispatch only.  task_id and
        trace_id stay inside Zentex and are never forwarded to the external CLI.
        """
        resolved_task_service = task_service or self._task_service
        executor_metadata = {
            "cli_tool_name": tool_name,
            "executor_type": "cli",
        }
        await mark_external_execution_started(
            task_service=resolved_task_service,
            task_id=task_id,
            trace_id=trace_id,
            executor_type="cli",
            executor_metadata=executor_metadata,
        )

        started_at = datetime.now(timezone.utc)
        result = self._adapter.invoke_tool(
            tool_name,
            arguments=arguments,
            stdin_input=stdin_input,
            trace_id=trace_id,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        finished_at = datetime.now(timezone.utc)
        result_payload = result.model_dump(mode="json")
        succeeded = result.status == "success"
        error_message = None if succeeded else (result.stderr or f"CLI tool '{tool_name}' failed with status {result.status}")
        self._registry_store.append_runtime_log(
            "cli",
            tool_name,
            capability_name=tool_name,
            invocation_type="execute_task",
            status=result.status,
            request={
                "arguments": arguments or [],
                "stdin_supplied": stdin_input is not None,
                "working_directory": working_directory,
                "timeout_seconds": timeout_seconds,
                "task_id": task_id,
            },
            response=result_payload,
            error_message=error_message,
            trace_id=trace_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=result.duration_ms,
        )

        writeback = await write_external_execution_result(
            task_service=resolved_task_service,
            task_id=task_id,
            trace_id=trace_id,
            executor_type="cli",
            executor_metadata=executor_metadata,
            result_payload=result_payload,
            succeeded=succeeded,
            error_message=error_message,
        )
        return {
            "succeeded": succeeded,
            "task_center_synchronized": True,
            "task_id": task_id,
            "trace_id": trace_id,
            "executor_type": "cli",
            "executor_id": f"cli:{tool_name}",
            "output": result_payload,
            "error": error_message,
            "duration_seconds": float(result.duration_ms or 0) / 1000.0,
            "failure_classification": result.failure_category,
            "task_writeback": writeback,
        }

    def _map_invocation_result(self, result: CliInvocationResult) -> ServiceResponse:
        """Map raw CLI invocation result to standardized ServiceResponse."""
        if result.status == "success":
            return ServiceResponse.ok(data=result)
        
        if result.status == "timeout":
            return ServiceResponse(
                status=ServiceStatus.timeout,
                code=ServiceErrorCode.SERVICE_TIMEOUT.value,
                message=result.stderr,
                data=result,
                trace_id=result.trace_id,
            )
        
        if result.status == "transport_error":
            return ServiceResponse.error(
                code=ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
                message=f"CLI transport failed for '{result.tool_name}': {result.stderr}",
                data=result
            )
            
        # Default failed status (non-zero exit code or unexpected error)
        return ServiceResponse.error(
            code=ServiceErrorCode.INTERNAL_UNRECOVERABLE,
            message=f"CLI tool '{result.tool_name}' failed with status '{result.status}'",
            data=result
        )

    def get_tool_detail(self, tool_name: str) -> Optional[CliToolRuntimeState]:
        """获取工具详细信息"""
        tools = self._adapter.list_tool_states()
        for tool in tools:
            if tool.command_name == tool_name:
                return tool
        return None

    def activate_tool(self, tool_name: str) -> CliToolRuntimeState:
        return self._adapter.activate_tool(tool_name)

    def disable_tool(self, tool_name: str) -> CliToolRuntimeState:
        return self._adapter.disable_tool(tool_name)

    def delete_tool(self, tool_name: str) -> bool:
        deleted = self._adapter.delete_tool(tool_name)
        if deleted:
            self._usage_profiles.pop(tool_name, None)
            self._persist_registered_tools()
            self._registry_store.delete_current("cli", tool_name)
        return deleted

    def _restore_registered_tools(self) -> None:
        if not hasattr(self._adapter, "_registered_tools"):
            return
        db_rows = self._registry_store.list_current("cli")
        if db_rows:
            payload = [row["payload"] for row in db_rows]
        elif self._registry_path.exists():
            try:
                payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to read persisted CLI registry from %s: %s", self._registry_path, exc)
                raise RuntimeError(f"failed to read persisted CLI registry: {exc}") from exc
            if not isinstance(payload, list):
                raise RuntimeError("persisted CLI registry must be a list")
        else:
            return
        if not isinstance(payload, list):
            raise RuntimeError("persisted CLI registry must be a list")
        for item in payload:
            config = CliToolRegistrationConfig.model_validate(item)
            if config.tool_name in getattr(self._adapter, "_registered_tools", {}):
                continue
            try:
                state = self._adapter.register_tool(config)
                if not db_rows:
                    self._registry_store.upsert_current(
                        "cli",
                        config.tool_name,
                        config.model_dump(mode="json"),
                        status=state.status,
                        display_name=config.tool_name,
                        action="import_json_registry",
                    )
            except Exception as exc:
                logger.warning("Persisted CLI tool '%s' could not be restored: %s", config.tool_name, exc)

    def _persist_registered_tools(self) -> None:
        if not hasattr(self._adapter, "_registered_tools"):
            return
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        configs = list(getattr(self._adapter, "_registered_tools", {}).values())
        payload = [config.model_dump(mode="json") for config in sorted(configs, key=lambda item: item.tool_name)]
        self._registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def get_tool_health(self, tool_name: str) -> Dict[str, Any]:
        return self._adapter.get_tool_health(tool_name)

    def diagnose_cli_execution_closure(self) -> Dict[str, Any]:
        return self._adapter.diagnose_cli_execution_closure()

    def run_cli_fault_injection_matrix(self) -> Dict[str, Any]:
        return self._adapter.run_cli_fault_injection_matrix()

    def get_tool_tasks_by_status(self, tool_name: str, status_filter: str) -> List[Dict[str, Any]]:
        """根据状态获取工具相关任务"""
        if not self._task_service:
            return []
        
        # 获取所有任务
        all_tasks = self._task_service.list_tasks()
        
        # 过滤与 CLI 工具相关的任务（通过 metadata 或 title 匹配）
        related_tasks = []
        for task in all_tasks:
            task_dict = task.model_dump(mode="json") if hasattr(task, 'model_dump') else task
            
            # 检查任务是否与 CLI 工具相关
            metadata = task_dict.get("metadata", {})
            title = task_dict.get("title", "")
            
            if (metadata.get("cli_tool_name") == tool_name or 
                tool_name in title):
                
                # 根据状态过滤
                task_status = task_dict.get("status", "")
                if status_filter == "in_progress" and task_status == "in_progress":
                    related_tasks.append(task_dict)
                elif status_filter == "pending" and task_status in ["todo", "blocked"]:
                    related_tasks.append(task_dict)
                elif status_filter == "failed" and task_status == "failed":
                    related_tasks.append(task_dict)
        
        return related_tasks

    def get_tool_execution_history(self, tool_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取工具执行历史记录"""
        db_logs = self._registry_store.list_runtime_logs("cli", tool_name, limit=limit)
        if db_logs:
            return [
                {
                    "trace_id": item.get("trace_id") or "",
                    "tool_name": tool_name,
                    "status": item.get("status", "unknown"),
                    "exit_code": (item.get("response") or {}).get("exit_code", -1),
                    "stdout": (item.get("response") or {}).get("stdout", ""),
                    "stderr": (item.get("response") or {}).get("stderr", ""),
                    "command_line": (item.get("response") or {}).get("command_line", []),
                    "working_directory": (item.get("response") or {}).get("working_directory"),
                    "executed_at": item.get("started_at"),
                    "duration_ms": item.get("duration_ms"),
                    "failure_category": (item.get("response") or {}).get("failure_category"),
                    "preflight_blocked": bool((item.get("response") or {}).get("preflight_blocked", False)),
                }
                for item in db_logs
            ]

        if not self._transcript_store:
            return []
        
        # 从 transcript store 中查询该工具的审计记录
        entries = []
        if hasattr(self._transcript_store, 'list_entries'):
            entries = self._transcript_store.list_entries(
                session_id=None,
                entry_type="plugin_audit_event",
                limit=limit
            )
        
        # 过滤出与该工具相关的记录
        history = []
        for entry in entries:
            payload = entry.get("payload", {}) if isinstance(entry, dict) else getattr(entry, 'payload', {})
            source = entry.get("source", "") if isinstance(entry, dict) else getattr(entry, "source", "")
            if payload.get("tool_name") == tool_name:
                if source != "cli.adapter.test_call":
                    continue
                history.append({
                    "trace_id": entry.get("trace_id", "") if isinstance(entry, dict) else getattr(entry, "trace_id", ""),
                    "tool_name": tool_name,
                    "status": payload.get("status", "unknown"),
                    "exit_code": payload.get("exit_code", -1),
                    "stdout": payload.get("stdout", ""),
                    "stderr": payload.get("stderr", ""),
                    "command_line": payload.get("command_line", []),
                    "working_directory": payload.get("working_directory"),
                    "executed_at": entry.get("timestamp", datetime.now(timezone.utc).isoformat())
                    if isinstance(entry, dict)
                    else getattr(entry, "timestamp", datetime.now(timezone.utc).isoformat()),
                    "duration_ms": payload.get("duration_ms"),
                    "failure_category": payload.get("failure_category"),
                    "preflight_blocked": bool(payload.get("preflight_blocked", False)),
                })
        
        return history[:limit]

    def calculate_credit_score(self, tool_name: str) -> Dict[str, Any]:
        """计算工具信用分"""
        history = self.get_tool_execution_history(tool_name, limit=1000)
        
        total_executions = len(history)
        if total_executions == 0:
            # POLICY[no-fake-impl]: return zero-based scores, not an optimistic default.
            # "unrated" signals to callers that there is no real execution data yet.
            return {
                "total_score": 0.0,
                "success_rate": 0.0,
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "average_response_time_ms": None,
                "error_rate": 0.0,
                "usage_frequency": "low",
                "credit_level": "unrated",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        
        successful = sum(1 for h in history if h.get("status") == "success")
        failed = total_executions - successful
        success_rate = successful / total_executions if total_executions > 0 else 0.0
        error_rate = failed / total_executions if total_executions > 0 else 0.0
        
        # 计算平均响应时间（如果有数据）
        durations = [h.get("duration_ms") for h in history if h.get("duration_ms") is not None]
        avg_response_time = sum(durations) / len(durations) if durations else None
        
        # 使用频率评估
        if total_executions > 100:
            usage_frequency = "high"
        elif total_executions > 20:
            usage_frequency = "medium"
        else:
            usage_frequency = "low"
        
        # 计算信用分（0-100）
        # 成功率占 60%，使用频率占 20%，响应时间占 20%
        score_from_success_rate = success_rate * 60
        score_from_usage = {"high": 20, "medium": 15, "low": 10}.get(usage_frequency, 10)
        score_from_response = 20  # 默认满分，如果有响应时间数据可以调整
        
        if avg_response_time is not None:
            if avg_response_time < 100:
                score_from_response = 20
            elif avg_response_time < 500:
                score_from_response = 15
            elif avg_response_time < 1000:
                score_from_response = 10
            else:
                score_from_response = 5
        
        total_score = score_from_success_rate + score_from_usage + score_from_response
        total_score = min(max(total_score, 0), 100)  # 限制在 0-100 之间
        
        # 确定信用等级
        if total_score >= 85:
            credit_level = "excellent"
        elif total_score >= 70:
            credit_level = "good"
        elif total_score >= 50:
            credit_level = "fair"
        else:
            credit_level = "poor"
        
        return {
            "total_score": round(total_score, 2),
            "success_rate": round(success_rate, 4),
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": failed,
            "average_response_time_ms": round(avg_response_time, 2) if avg_response_time else None,
            "error_rate": round(error_rate, 4),
            "usage_frequency": usage_frequency,
            "credit_level": credit_level,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def get_task_statistics(self, tool_name: str) -> Dict[str, int]:
        """获取任务统计数据"""
        if not self._task_service:
            return {
                "in_progress": 0,
                "pending": 0,
                "failed": 0,
                "completed": 0,
                "total": 0
            }
        
        all_tasks = self._task_service.list_tasks()
        stats = {
            "in_progress": 0,
            "pending": 0,
            "failed": 0,
            "completed": 0,
            "total": 0
        }
        
        for task in all_tasks:
            task_dict = task.model_dump(mode="json") if hasattr(task, 'model_dump') else task
            metadata = task_dict.get("metadata", {})
            title = task_dict.get("title", "")
            
            if (metadata.get("cli_tool_name") == tool_name or 
                tool_name in title):
                
                stats["total"] += 1
                status = task_dict.get("status", "")
                
                if status == "in_progress":
                    stats["in_progress"] += 1
                elif status in ["todo", "blocked"]:
                    stats["pending"] += 1
                elif status == "failed":
                    stats["failed"] += 1
                elif status == "done":
                    stats["completed"] += 1
        
        return stats


def get_service(transcript_store: Any = None, llm_service: Any = None) -> CliIntegrationService:
    """Standard service factory function for launcher assembly."""
    # Build default adapter
    adapter = create_cli_adapter_plugin(transcript_store=transcript_store)
    if llm_service is None:
        try:
            from zentex.llm.service import get_service as get_llm_service

            llm_service = get_llm_service()
        except Exception:
            llm_service = None
    service = CliIntegrationService(
        adapter=adapter,
        transcript_store=transcript_store,
        llm_service=llm_service,
        auth_service=AgentAuthService(),
    )
    _register_builtin_tools_via_service(service)
    return service


def _register_builtin_tools_via_service(service: CliIntegrationService) -> None:
    response = service.register_tool(PLAYWRIGHT_CLI_TOOL_CONFIG)
    if response.status != ServiceStatus.ok:
        logger.warning("Built-in CLI tool registration failed for playwright-cli: %s", response.message)


__all__ = [
    "CliIntegrationService",
    "CliAdapterPlugin",
    "create_cli_adapter_plugin",
    "SubprocessCliTransport",
    "CliToolRegistrationConfig",
    "CliInvocationResult",
    "CliToolRuntimeState",
    "PLAYWRIGHT_CLI_TOOL_CONFIG",
    "get_service",
]
