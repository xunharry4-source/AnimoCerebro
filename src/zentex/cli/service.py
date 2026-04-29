from __future__ import annotations

"""Public CLI integration facade used by web and runtime callers."""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from zentex.cli.adapter import CliAdapterPlugin, create_cli_adapter_plugin
from zentex.cli.adapter import SubprocessCliTransport
from zentex.cli.models import CliInvocationResult, CliToolRegistrationConfig, CliToolRuntimeState
from zentex.foundation.contracts.service_response import ServiceResponse, ServiceErrorCode, ServiceStatus


class CliIntegrationService:
    def __init__(self, adapter: CliAdapterPlugin, transcript_store: Any = None, task_service: Any = None) -> None:
        self._adapter = adapter
        self._transcript_store = transcript_store
        self._task_service = task_service

    def list_tools(self) -> List[CliToolRuntimeState]:
        return self._adapter.list_tool_states()

    def register_tool(self, config: CliToolRegistrationConfig) -> ServiceResponse:
        try:
            state = self._adapter.register_tool(config)
            return ServiceResponse.ok(data=state)
        except (FileNotFoundError, ValueError) as e:
            # Validation / reachability failures are expected; log at WARNING.
            logger.warning(
                "CLI tool registration rejected for '%s': %s",
                config.tool_name, e, exc_info=True,
            )
            return ServiceResponse.error(
                code=ServiceErrorCode.INVALID_ARGUMENT,
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

    def test_call(
        self,
        tool_name: str,
        *,
        arguments: List[Optional[str]] = None,
        stdin_input: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> ServiceResponse:
        result = self._adapter.invoke_tool(
            tool_name,
            arguments=arguments,
            stdin_input=stdin_input,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        return self._map_invocation_result(result)

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
        return self._adapter.delete_tool(tool_name)

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
            if payload.get("tool_name") == tool_name:
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


def get_service(transcript_store: Any = None) -> CliIntegrationService:
    """Standard service factory function for launcher assembly."""
    # Build default adapter
    adapter = create_cli_adapter_plugin(transcript_store=transcript_store)
    return CliIntegrationService(adapter=adapter, transcript_store=transcript_store)


__all__ = [
    "CliIntegrationService",
    "CliAdapterPlugin",
    "create_cli_adapter_plugin",
    "SubprocessCliTransport",
    "CliToolRegistrationConfig",
    "CliInvocationResult",
    "CliToolRuntimeState",
    "get_service",
]
