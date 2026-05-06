from __future__ import annotations

from typing import Any, Dict, List

from zentex.tasks.execution.assignment_flow import ResourceMatcher
from zentex.tasks.models import TaskStatus, ZentexTask


def metadata_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def candidate_counts_by_registry(candidates: List[Any]) -> Dict[str, int]:
    counts = {
        "functional_plugin": 0,
        "cli": 0,
        "mcp": 0,
        "agent": 0,
        "external_connector": 0,
    }
    for candidate in candidates:
        executor_type = str(getattr(candidate, "executor_type", "") or "")
        if executor_type == "internal":
            counts["functional_plugin"] += 1
        elif executor_type in counts:
            counts[executor_type] += 1
    return counts


def declared_owner_ref(task: ZentexTask, metadata: Dict[str, Any]) -> str:
    target_id = str(getattr(task, "target_id", "") or metadata.get("target_id") or metadata.get("owner_ref") or "").strip()
    if target_id:
        return target_id
    executor_type = str(metadata.get("executor_type") or metadata.get("external_executor_type") or "").strip().lower()
    if executor_type == "internal":
        plugin_id = str(metadata.get("internal_executor_plugin_id") or metadata.get("executor_id") or "").strip()
        return f"internal:{plugin_id}" if plugin_id else ""
    if executor_type == "cli":
        tool_name = str(metadata.get("cli_tool_name") or metadata.get("tool_name") or "").strip()
        return f"cli:{tool_name}" if tool_name else ""
    if executor_type == "mcp":
        server_id = str(metadata.get("mcp_server_id") or metadata.get("server_id") or "").strip()
        tool_name = str(metadata.get("mcp_tool_name") or metadata.get("tool_name") or "").strip()
        return f"mcp:{server_id}:{tool_name}" if server_id and tool_name else ""
    if executor_type == "external_connector":
        connector_id = str(metadata.get("external_connector_id") or metadata.get("connector_id") or "").strip()
        return f"external_connector:{connector_id}" if connector_id else ""
    if executor_type == "agent":
        agent_id = str(metadata.get("agent_id") or "").strip()
        return f"agent:{agent_id}" if agent_id else ""
    return ""


def executor_type_from_owner_ref(owner_ref: str) -> str:
    owner = str(owner_ref or "").strip()
    if owner.startswith("internal:"):
        return "internal"
    if owner.startswith("cli:"):
        return "cli"
    if owner.startswith("mcp:"):
        return "mcp"
    if owner.startswith("external_connector:"):
        return "external_connector"
    if owner.startswith("agent:"):
        return "agent"
    return ""


def validate_execution_assignment(
    *,
    task: ZentexTask,
    plugin_service: Any = None,
    cli_service: Any = None,
    mcp_service: Any = None,
    external_connector_service: Any = None,
    agent_service: Any = None,
) -> Dict[str, Any]:
    metadata = getattr(task, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    required_capabilities = metadata_list(metadata.get("required_capabilities"))
    dispatch_failure = metadata.get("dispatch_failure") if isinstance(metadata.get("dispatch_failure"), dict) else {}
    required_capabilities.extend(
        item for item in metadata_list(dispatch_failure.get("required_capabilities"))
        if item not in required_capabilities
    )
    required_capability = str(metadata.get("required_capability") or "").strip()
    if required_capability and required_capability not in required_capabilities:
        required_capabilities.append(required_capability)
    required_resources = metadata_list(metadata.get("required_resources"))
    declared_owner = declared_owner_ref(task, metadata)
    matcher = ResourceMatcher(
        plugin_service=plugin_service,
        cli_service=cli_service,
        mcp_service=mcp_service,
        external_connector_service=external_connector_service,
        agent_service=agent_service,
    )
    candidates = matcher._collect_candidates()
    checked_registries = candidate_counts_by_registry(candidates)
    if not declared_owner and not required_capabilities and not required_resources:
        status_value = getattr(task.status, "value", task.status)
        assignment_status = "dispatch_blocked" if status_value in {"blocked", "suspended"} else "unassigned"
        return {
            "status": assignment_status,
            "source": "registry_check",
            "executor_id": "",
            "executor_type": "",
            "label": "",
            "checked_registries": checked_registries,
            "candidate_owners": [getattr(item, "owner_ref", "") for item in candidates],
            "missing_resources": ["executor"],
            "required_capabilities": [],
        }

    decision = matcher.match(
        task=task,
        required_capabilities=required_capabilities,
        required_resources=required_resources,
        designated_owner=declared_owner,
    )
    if decision.assigned:
        selected = decision.candidates[0]
        return {
            "status": "assigned",
            "source": getattr(selected, "metadata", {}).get("source") or "registry_check",
            "executor_id": decision.owner_ref,
            "executor_type": decision.executor_type,
            "label": getattr(selected, "label", "") or decision.owner_ref,
            "checked_registries": checked_registries,
            "candidate_owners": decision.candidate_owners,
            "required_capabilities": decision.required_capabilities,
            "matched_by": "G31A.ResourceMatcher",
        }

    status_value = getattr(task.status, "value", task.status)
    assignment_status = "dispatch_blocked" if status_value in {"blocked", "suspended"} or declared_owner else "unassigned"
    return {
        "status": assignment_status,
        "source": "registry_check",
        "executor_id": declared_owner,
        "executor_type": str(metadata.get("executor_type") or executor_type_from_owner_ref(declared_owner) or "").strip(),
        "label": "",
        "checked_registries": checked_registries,
        "candidate_owners": [getattr(item, "owner_ref", "") for item in candidates],
        "missing_resources": decision.missing_resources or [declared_owner or "executor"],
        "required_capabilities": decision.required_capabilities,
        "matched_by": "G31A.ResourceMatcher",
        "resource_gap": True,
    }


def attach_validated_execution_assignment(
    *,
    task: ZentexTask,
    plugin_service: Any = None,
    cli_service: Any = None,
    mcp_service: Any = None,
    external_connector_service: Any = None,
    agent_service: Any = None,
) -> ZentexTask:
    task.execution_assignment = validate_execution_assignment(
        task=task,
        plugin_service=plugin_service,
        cli_service=cli_service,
        mcp_service=mcp_service,
        external_connector_service=external_connector_service,
        agent_service=agent_service,
    )
    return task


__all__ = [
    "metadata_list",
    "candidate_counts_by_registry",
    "declared_owner_ref",
    "executor_type_from_owner_ref",
    "validate_execution_assignment",
    "attach_validated_execution_assignment",
]
