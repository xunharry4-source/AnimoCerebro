from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


EXECUTOR_TYPES = {"cli", "mcp", "external_connector", "agent", "internal_plugin"}


@dataclass(frozen=True)
class ExecutionContext:
    task_id: str
    trace_id: str
    task_scope: str
    executor_type: str
    owner_ref: str
    capability: str
    task_title: str
    objective: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_task: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "task_scope": self.task_scope,
            "executor_type": self.executor_type,
            "owner_ref": self.owner_ref,
            "capability": self.capability,
            "task_title": self.task_title,
            "objective": self.objective,
            "metadata": dict(self.metadata),
            "raw_task": dict(self.raw_task),
        }


def normalize_task_payload(task: Any) -> Dict[str, Any]:
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    if isinstance(task, dict):
        return dict(task)
    return dict(getattr(task, "__dict__", {}) or {})


def metadata_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    metadata = task.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    if isinstance(metadata, str) and metadata.strip():
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def list_value(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def infer_executor_type(task: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    target_id = str(task.get("target_id") or metadata.get("target_id") or "").strip()
    raw = (
        metadata.get("executor_type")
        or metadata.get("external_executor_type")
        or metadata.get("executor_kind")
        or ""
    )
    executor_type = str(raw).strip().lower()
    if executor_type == "connector":
        executor_type = "external_connector"
    if executor_type == "internal":
        executor_type = "internal_plugin"
    if executor_type in EXECUTOR_TYPES:
        return executor_type
    if target_id.startswith("cli:") or metadata.get("cli_tool_name"):
        return "cli"
    if target_id.startswith("mcp:") or metadata.get("mcp_server_id"):
        return "mcp"
    if target_id.startswith(("external_connector:", "connector:")) or metadata.get("external_connector_id"):
        return "external_connector"
    if target_id.startswith("agent:") or metadata.get("agent_id"):
        return "agent"
    if target_id.startswith("internal:") or metadata.get("internal_plugin_id") or metadata.get("internal_executor_plugin_id"):
        return "internal_plugin"
    return ""


def dispatch_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    metadata = metadata_from_task(task)
    target_id = str(task.get("target_id") or metadata.get("target_id") or "").strip()
    executor_type = infer_executor_type(task, metadata)
    task_id = str(task.get("task_id") or "")
    trace_id = str(metadata.get("trace_id") or f"react-task:{task_id}")

    if executor_type == "cli":
        tool_name = str(
            metadata.get("cli_tool_name")
            or metadata.get("tool_name")
            or metadata.get("command_name")
            or (target_id.removeprefix("cli:") if target_id.startswith("cli:") else "")
            or ""
        ).strip()
        return {
            "executor_type": "cli",
            "trace_id": trace_id,
            "tool_name": tool_name,
            "capability": tool_name,
            "arguments": list_value(metadata.get("cli_arguments") if metadata.get("cli_arguments") is not None else metadata.get("arguments")),
            "stdin_input": metadata.get("stdin_input") or metadata.get("cli_stdin_input"),
            "working_directory": metadata.get("working_directory") or metadata.get("cli_working_directory"),
            "timeout_seconds": metadata.get("timeout_seconds") or metadata.get("cli_timeout_seconds"),
            "expected_physical_artifacts": list_value(
                metadata.get("physical_artifacts")
                or metadata.get("expected_physical_artifacts")
                or metadata.get("evidence_paths")
                or metadata.get("artifact_paths")
            ),
        }

    if executor_type == "mcp":
        target_server = ""
        target_tool = ""
        if target_id.startswith("mcp:"):
            parts = target_id.split(":", 2)
            target_server = parts[1] if len(parts) >= 2 else ""
            target_tool = parts[2] if len(parts) == 3 else ""
        arguments = metadata.get("mcp_arguments")
        if arguments is None:
            arguments = metadata.get("arguments")
        return {
            "executor_type": "mcp",
            "trace_id": trace_id,
            "server_id": str(metadata.get("mcp_server_id") or metadata.get("server_id") or target_server or "").strip(),
            "tool_name": str(metadata.get("mcp_tool_name") or metadata.get("tool_name") or target_tool or "").strip(),
            "capability": str(metadata.get("mcp_tool_name") or metadata.get("tool_name") or target_tool or "").strip(),
            "arguments": arguments if isinstance(arguments, dict) else {},
            "response_evidence_path": metadata.get("response_evidence_path") or metadata.get("mcp_response_evidence_path"),
            "query_assertions": metadata.get("query_assertions") or metadata.get("mcp_query_assertions") or [],
        }

    if executor_type == "external_connector":
        connector_id = str(
            metadata.get("external_connector_id")
            or metadata.get("connector_id")
            or (target_id.removeprefix("external_connector:") if target_id.startswith("external_connector:") else "")
            or ""
        ).strip()
        capability = str(
            metadata.get("external_connector_capability")
            or metadata.get("connector_capability")
            or metadata.get("capability")
            or ""
        ).strip()
        arguments = metadata.get("external_connector_arguments")
        if arguments is None:
            arguments = metadata.get("connector_arguments")
        if arguments is None:
            arguments = metadata.get("arguments")
        return {
            "executor_type": "external_connector",
            "trace_id": trace_id,
            "connector_id": connector_id,
            "capability": capability,
            "title": task.get("title"),
            "objective": metadata.get("objective") or task.get("remarks"),
            "remarks": task.get("remarks"),
            "external_plugin_path": metadata.get("external_plugin_path") or metadata.get("plugin_path"),
            "arguments": arguments if isinstance(arguments, dict) else {},
            "allow_legacy_test_call_adapter": bool(metadata.get("allow_legacy_test_call_adapter")),
        }

    if executor_type == "agent":
        agent_id = str(
            metadata.get("agent_id")
            or (target_id.removeprefix("agent:") if target_id.startswith("agent:") else target_id)
            or ""
        ).strip()
        task_payload = metadata.get("agent_task_payload")
        if task_payload is None:
            task_payload = metadata.get("task_payload")
        if task_payload is None:
            task_payload = {"title": task.get("title"), "remarks": task.get("remarks")}
        return {
            "executor_type": "agent",
            "trace_id": trace_id,
            "session_id": str(metadata.get("session_id") or task.get("originator_id") or ""),
            "agent_id": agent_id,
            "capability": str(metadata.get("agent_capability") or agent_id or "agent_dispatch").strip(),
            "agent_scope": list_value(metadata.get("agent_scope") or metadata.get("scope")),
            "task_payload": task_payload if isinstance(task_payload, dict) else {},
            "idempotency_key": task.get("idempotency_key") or metadata.get("idempotency_key"),
            "verification_plan": metadata.get("agent_verification_plan") or metadata.get("verification_plan"),
        }

    if executor_type == "internal_plugin":
        plugin_id = str(
            metadata.get("internal_plugin_id")
            or metadata.get("internal_executor_plugin_id")
            or metadata.get("executor_id")
            or (target_id.removeprefix("internal:") if target_id.startswith("internal:") else "")
            or ""
        ).strip()
        arguments = metadata.get("internal_plugin_arguments")
        if arguments is None:
            arguments = metadata.get("plugin_arguments")
        if arguments is None:
            arguments = metadata.get("arguments")
        return {
            "executor_type": "internal_plugin",
            "trace_id": trace_id,
            "plugin_id": plugin_id,
            "capability": str(metadata.get("internal_plugin_capability") or plugin_id or "").strip(),
            "arguments": arguments if isinstance(arguments, dict) else {},
        }

    return {"executor_type": "", "trace_id": trace_id, "capability": "", "arguments": {}}


def build_execution_context(task: Dict[str, Any], dispatch: Dict[str, Any]) -> ExecutionContext:
    metadata = metadata_from_task(task)
    executor_type = str(dispatch.get("executor_type") or "").strip()
    if executor_type == "cli":
        owner_ref = f"cli:{dispatch.get('tool_name') or ''}"
    elif executor_type == "mcp":
        owner_ref = f"mcp:{dispatch.get('server_id') or ''}:{dispatch.get('tool_name') or ''}"
    elif executor_type == "external_connector":
        owner_ref = f"external_connector:{dispatch.get('connector_id') or ''}"
    elif executor_type == "agent":
        owner_ref = f"agent:{dispatch.get('agent_id') or ''}"
    elif executor_type == "internal_plugin":
        owner_ref = f"internal:{dispatch.get('plugin_id') or ''}"
    else:
        owner_ref = ""
    capability = str(dispatch.get("capability") or "").strip()
    return ExecutionContext(
        task_id=str(task.get("task_id") or ""),
        trace_id=str(dispatch.get("trace_id") or metadata.get("trace_id") or ""),
        task_scope=str(task.get("task_scope") or metadata.get("task_scope") or "internal"),
        executor_type=executor_type,
        owner_ref=owner_ref,
        capability=capability,
        task_title=str(task.get("title") or ""),
        objective=str(metadata.get("objective") or task.get("remarks") or task.get("title") or ""),
        metadata=metadata,
        raw_task=dict(task),
    )
