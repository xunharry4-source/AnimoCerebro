from __future__ import annotations

from typing import Any, Dict, List

from zentex.tasks.models import TaskScope


_EXTERNAL_Q9_MODULE_OWNER_ALIASES: Dict[str, tuple[str, str]] = {
    "gemini": ("cli:gemini", "cli"),
    "notion": ("mcp:notion", "mcp"),
}


def q9_g31a_verification_method(plan_type: str) -> str:
    lane = "external" if plan_type == "external" else "internal"
    return (
        f"G31A task-center {lane} subtask verification: execute through the assigned real executor, "
        "then read back child task status=done, task_outcome.overall_passed=true, non-empty actual_outcome, "
        "and objective executor evidence such as read-after-write/readback, exit_code, stdout/stderr, hash, "
        "mtime, or persisted audit/query records."
    )


def q9_g31a_acceptance_criteria(plan_type: str) -> List[str]:
    lane = "external" if plan_type == "external" else "internal"
    return [
        f"G31A must read back the {lane} child task and confirm status=done.",
        "G31A must read back task_outcome and confirm overall_passed=true with non-empty actual_outcome.",
        "G31A must verify objective executor evidence, not planner self-analysis or success text.",
    ]


def _internal_owner_capability(value: str) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("internal:"):
        return text.split(":", 1)[1].strip()
    return text


def _is_owner_ref(value: str) -> bool:
    return str(value or "").strip().startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:"))


def _strip_resource_prefix(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in (
        "功能：",
        "功能:",
        "任务资源：",
        "任务资源:",
        "能力需求：",
        "能力需求:",
        "Functional plugin:",
        "功能插件：",
        "Cognitive plugin:",
        "认知插件：",
        "归属器官：",
        "归属器官:",
        "执行方钦定：",
        "执行方钦定:",
    ):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def q9_effective_step_capability(step_record: Dict[str, Any], fallback_capability: str, plan_type: str = "external") -> str:
    """Choose an explicitly declared capability without guessing from task prose."""
    if plan_type != "external":
        return fallback_capability

    for raw in [
        fallback_capability,
        *[str(item) for item in step_record.get("required_resources") or []],
    ]:
        text = _strip_resource_prefix(raw)
        if text and not _is_owner_ref(text):
            return text
    return fallback_capability


def q9_blueprint_lines(blueprint: Dict[str, Any], plan_type: str) -> List[str]:
    return [record["line"] for record in q9_blueprint_step_records(blueprint, plan_type)]


def dependency_graph_is_dag(dependency_graph: List[Dict[str, Any]]) -> bool:
    graph = {
        str(node.get("task_id") or ""): [str(dep) for dep in node.get("depends_on") or []]
        for node in dependency_graph
        if str(node.get("task_id") or "").strip()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return False
        if node_id in visited:
            return True
        visiting.add(node_id)
        for dependency_id in graph.get(node_id, []):
            if dependency_id in graph and not visit(dependency_id):
                return False
        visiting.remove(node_id)
        visited.add(node_id)
        return True

    return all(visit(node_id) for node_id in graph)


def q9_blueprint_step_records(blueprint: Dict[str, Any], plan_type: str) -> List[Dict[str, Any]]:
    legacy_key = "current_internal_plan" if plan_type == "internal" else "current_external_plan"
    value = blueprint.get("action_steps") or blueprint.get("current_action_plan") or blueprint.get(legacy_key)
    if not isinstance(value, list):
        return []
    records: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            step_description = str(item.get("step_description") or "").strip()
            step_objective = str(item.get("step_objective") or "").strip()
            q9_verification_hint = str(item.get("verification_method") or "").strip()
            modules = item.get("involved_modules")
            involved_modules = [
                str(module or "").strip()
                for module in modules
                if str(module or "").strip()
            ] if isinstance(modules, list) else []
            modules_text = ", ".join(involved_modules)
            text = "；".join(
                part
                for part in (
                    f"步骤说明：{step_description}",
                    f"步骤目标：{step_objective}",
                    f"Q9检查提示：{q9_verification_hint}",
                    f"涉及模块：{modules_text}" if modules_text else "",
                )
                if part and not part.endswith("：")
            )
            title = step_description or text
            objective = step_objective or text
            acceptance_criteria = q9_g31a_acceptance_criteria(plan_type)
            required_resources = involved_modules
        else:
            text = str(item or "").strip()
            title = text
            objective = text
            q9_verification_hint = ""
            acceptance_criteria = q9_g31a_acceptance_criteria(plan_type)
            required_resources = []
        if text:
            records.append(
                {
                    "line": text,
                    "title": title,
                    "objective": objective,
                    "acceptance_criteria": acceptance_criteria,
                    "verification_method": q9_g31a_verification_method(plan_type),
                    "q9_verification_hint": q9_verification_hint,
                    "required_resources": required_resources,
                }
            )
    return records


def q9_blueprint_capabilities(blueprint: Dict[str, Any], plan_type: str) -> List[str]:
    legacy_key = "required_cognitive_resources" if plan_type == "internal" else "required_functional_resources"
    value = blueprint.get("required_resources") or blueprint.get(legacy_key)
    if not isinstance(value, list):
        return []
    capabilities: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        text = _strip_resource_prefix(text)
        if str(item or "").strip().startswith(("执行方钦定：", "执行方钦定:")):
            continue
        if plan_type == "internal":
            text = _internal_owner_capability(text)
        if text:
            capabilities.append(text)
    return list(dict.fromkeys(capabilities))


def q9_blueprint_designated_executors(blueprint: Dict[str, Any]) -> List[str]:
    execution_target = str(blueprint.get("execution_target") or "").strip()
    if execution_target.startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:")):
        return [execution_target]
    value = blueprint.get("required_resources")
    if not isinstance(value, list):
        return []
    executors: List[str] = []
    for item in value:
        text = str(item or "").strip()
        for prefix in ("执行方钦定：", "执行方钦定:"):
            if text.startswith(prefix):
                executor = text[len(prefix):].strip()
                if executor:
                    executors.append(executor)
                break
        if text.startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:")):
            executors.append(text)
    return list(dict.fromkeys(executors))


def q9_executor_for_designation(designation: str, plan_type: str, capability: str = "") -> Dict[str, Any]:
    normalized = str(designation or "").strip()
    lowered = normalized.lower()
    capability = _internal_owner_capability(capability) if plan_type == "internal" else str(capability or "").strip()
    if not normalized:
        return q9_executor_for_capability(capability, plan_type)
    if plan_type == "internal":
        if lowered.startswith("internal:"):
            target_id = normalized
        elif "thoughtsandbox" in lowered or lowered.startswith("b4") or "sandbox" in lowered or "沙盒" in lowered:
            target_id = "internal:thought_sandbox"
        elif "memory" in lowered or "记忆" in lowered:
            target_id = "internal:memory_engine"
        elif "learning" in lowered or "学习" in lowered:
            target_id = "internal:learning_engine"
        elif "reflection" in lowered or "反思" in lowered:
            target_id = "internal:reflection_engine"
        else:
            target_id = f"internal:{normalized}"
        return {
            "task_scope": TaskScope.INTERNAL,
            "target_id": target_id,
            "executor_type": "internal",
            "required_capabilities": [capability] if capability else [normalized],
        }

    if lowered.startswith(("cli:", "mcp:", "agent:", "external_connector:", "connector:")):
        target_id = normalized
        executor_type = normalized.split(":", 1)[0]
        if executor_type == "connector":
            executor_type = "external_connector"
            target_id = f"external_connector:{normalized.split(':', 1)[1]}"
    elif "cli" in lowered or "executor" in lowered:
        target_id = f"cli:{normalized}"
        executor_type = "cli"
    elif "mcp" in lowered:
        target_id = f"mcp:{normalized}"
        executor_type = "mcp"
    elif "agent" in lowered:
        target_id = f"agent:{normalized}"
        executor_type = "agent"
    else:
        target_id = f"external_connector:{normalized}"
        executor_type = "external_connector"
    return {
        "task_scope": TaskScope.EXTERNAL,
        "target_id": target_id,
        "executor_type": executor_type,
        "required_capabilities": [capability] if capability else [normalized],
    }


def q9_executor_for_capability(capability: str, plan_type: str) -> Dict[str, Any]:
    normalized = str(capability or "").strip()
    lowered = normalized.lower()
    if lowered == "execution_local_system" or "local_system" in lowered or "本地系统" in lowered:
        return {
            "task_scope": TaskScope.INTERNAL,
            "target_id": "internal:execution_local_system",
            "executor_type": "internal",
            "required_capabilities": ["execution_local_system"],
        }
    if plan_type == "internal":
        if lowered.startswith("internal:"):
            target_id = normalized
            normalized = _internal_owner_capability(normalized)
            lowered = normalized.lower()
        elif "semantic" in lowered or "cluster" in lowered or "聚类" in lowered:
            target_id = "internal:semantic_clusterer"
        elif "sandbox" in lowered or "thought" in lowered or "b4" in lowered or "沙盒" in lowered:
            target_id = "internal:thought_sandbox"
        elif "memory" in lowered or "记忆" in lowered:
            target_id = "internal:memory_engine"
        elif "learning" in lowered or "lesson" in lowered or "学习" in lowered:
            target_id = "internal:learning_engine"
        elif "reflection" in lowered or "audit" in lowered or "logic" in lowered or "反思" in lowered:
            target_id = "internal:task_constraint_checker"
        else:
            target_id = "internal:task_constraint_checker"
        return {
            "task_scope": TaskScope.INTERNAL,
            "target_id": target_id,
            "executor_type": "internal",
            "required_capabilities": [normalized] if normalized else ["task.constraint_checking"],
        }

    alias = _EXTERNAL_Q9_MODULE_OWNER_ALIASES.get(lowered)
    if alias is not None:
        target_id, executor_type = alias
    elif "code_repository" in lowered or "github" in lowered or "repository" in lowered:
        target_id = "external_connector:github"
        executor_type = "external_connector"
    elif "host_cli" in lowered or "cli" in lowered:
        target_id = "cli:host"
        executor_type = "cli"
    elif "http" in lowered or "network" in lowered:
        target_id = "external_connector:http"
        executor_type = "external_connector"
    elif "agent" in lowered:
        target_id = "agent:default"
        executor_type = "agent"
    elif "file" in lowered or "write" in lowered:
        target_id = "external_connector:file_writer"
        executor_type = "external_connector"
    else:
        target_id = ""
        executor_type = "external_connector"
    return {
        "task_scope": TaskScope.EXTERNAL,
        "target_id": target_id,
        "executor_type": executor_type,
        "required_capabilities": [normalized] if normalized else ["external.execution"],
    }


def q9_executor_runtime_metadata(
    *,
    executor_type: str,
    target_id: str,
    required_capabilities: List[str],
    trace_id: str,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "executor_type": executor_type,
        "target_id": target_id,
        "trace_id": trace_id,
        "required_capabilities": list(required_capabilities),
        "worker_dispatch_enabled": True,
    }
    if executor_type == "cli":
        tool_name = target_id.removeprefix("cli:") if target_id.startswith("cli:") else target_id
        metadata["cli_tool_name"] = tool_name
    elif executor_type == "mcp":
        parts = target_id.split(":", 2)
        if len(parts) >= 2:
            metadata["mcp_server_id"] = parts[1]
        if len(parts) == 3:
            metadata["mcp_tool_name"] = parts[2]
    elif executor_type == "external_connector":
        connector_id = target_id.removeprefix("external_connector:") if target_id.startswith("external_connector:") else target_id
        metadata["external_connector_id"] = connector_id
        connector_owner_ref = f"external_connector:{connector_id}"
        explicit_capabilities = [
            item
            for item in required_capabilities
            if item and item != connector_owner_ref and not str(item).startswith("external_connector:")
        ]
        if explicit_capabilities:
            metadata["external_connector_capability"] = explicit_capabilities[0]
    elif executor_type == "agent":
        metadata["agent_id"] = target_id.removeprefix("agent:") if target_id.startswith("agent:") else target_id
    return metadata


__all__ = [
    "q9_blueprint_lines",
    "q9_g31a_verification_method",
    "q9_g31a_acceptance_criteria",
    "q9_effective_step_capability",
    "dependency_graph_is_dag",
    "q9_blueprint_step_records",
    "q9_blueprint_capabilities",
    "q9_blueprint_designated_executors",
    "q9_executor_for_designation",
    "q9_executor_for_capability",
    "q9_executor_runtime_metadata",
]
