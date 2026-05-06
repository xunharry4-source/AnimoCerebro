from __future__ import annotations

from typing import Any

from .context_builder import build_external_task_context
from .validator import validate_external_task_plan


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector"}
EXTERNAL_PREFIXES = ("agent:", "cli:", "mcp:", "external_connector:", "connector:")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _derive_executor_type(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    executor_type = _text(task.get("executor_type") or metadata.get("executor_type")).lower()
    if executor_type in EXTERNAL_EXECUTOR_TYPES:
        return executor_type
    target_id = _text(task.get("target_id") or metadata.get("target_id")).lower()
    for prefix in EXTERNAL_PREFIXES:
        if target_id.startswith(prefix):
            return prefix.removesuffix(":")
    return ""


def _externalize_task(task: dict[str, Any], *, queue_name: str, index: int, executor_type: str) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    target_id = _text(task.get("target_id") or metadata.get("target_id"))
    capabilities = list(metadata.get("required_capabilities") or task.get("required_capabilities") or [])
    if not isinstance(capabilities, list):
        capabilities = [str(capabilities)]
    if executor_type == "cli":
        tool_name = _text(metadata.get("cli_tool_name") or metadata.get("tool_name") or target_id.removeprefix("cli:"))
        capabilities.extend(["external.cli"] + ([f"cli.{tool_name}"] if tool_name else []))
        metadata = {**metadata, "cli_tool_name": tool_name}
    elif executor_type == "mcp":
        parts = target_id.split(":", 2) if target_id.startswith("mcp:") else []
        server_id = _text(metadata.get("mcp_server_id") or (parts[1] if len(parts) >= 2 else ""))
        tool_name = _text(metadata.get("mcp_tool_name") or (parts[2] if len(parts) == 3 else ""))
        capabilities.extend(["external.mcp"] + ([f"mcp.{server_id}.{tool_name}"] if server_id and tool_name else []))
        metadata = {**metadata, "mcp_server_id": server_id, "mcp_tool_name": tool_name}
    elif executor_type in {"external_connector", "connector"}:
        connector_id = _text(
            metadata.get("external_connector_id")
            or metadata.get("connector_id")
            or target_id.removeprefix("external_connector:")
        )
        capability = _text(metadata.get("external_connector_capability") or metadata.get("connector_capability") or metadata.get("capability"))
        capabilities.extend(
            ["external.external_connector"]
            + ([f"external_connector.{connector_id}.{capability}"] if connector_id and capability else [])
        )
        metadata = {
            **metadata,
            "external_connector_id": connector_id,
            "external_connector_capability": capability,
        }
        executor_type = "external_connector"
    elif executor_type == "agent":
        agent_id = _text(metadata.get("agent_id") or target_id.removeprefix("agent:"))
        capabilities.extend(["external.agent"] + ([f"agent.{agent_id}"] if agent_id else []))
        metadata = {**metadata, "agent_id": agent_id}
    capabilities = list(dict.fromkeys(str(item).strip() for item in capabilities if str(item).strip()))
    normalized = dict(task)
    normalized["task_id"] = _text(task.get("task_id") or task.get("id") or f"external-{queue_name}-{index}")
    normalized["title"] = _text(task.get("title") or task.get("task") or normalized["task_id"])
    normalized["task_scope"] = "external"
    normalized["executor_type"] = executor_type
    normalized["required_capabilities"] = capabilities
    normalized["metadata"] = {
        **metadata,
        "task_scope": "external",
        "executor_type": executor_type,
        "external_executor_type": executor_type,
        "target_id": target_id,
        "required_capabilities": capabilities,
        "source_chain": "external_q8",
    }
    if target_id:
        normalized["target_id"] = target_id
    return normalized


def build_external_task_plan(
    *,
    question_snapshot: dict[str, Any],
    raw_task_queue: dict[str, Any],
) -> dict[str, Any]:
    context = build_external_task_context(question_snapshot=question_snapshot)
    tasks: list[dict[str, Any]] = []
    for queue_name in ("next_self_tasks", "blocked_self_tasks", "proactive_actions"):
        raw_items = raw_task_queue.get(queue_name)
        if not isinstance(raw_items, list):
            continue
        for index, item in enumerate(raw_items):
            task = item if isinstance(item, dict) else {"title": item}
            executor_type = _derive_executor_type(task)
            if not executor_type:
                continue
            tasks.append(_externalize_task(task, queue_name=queue_name, index=index, executor_type=executor_type))

    plan = {
        "planner": "q8_external_task_planner",
        "context": context,
        "tasks": tasks,
        "generated": len(tasks),
        "follow_up_events": [],
    }
    return validate_external_task_plan(plan)
