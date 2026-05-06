from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from zentex.nine_questions.q8_evaluation_planner import (
    apply_evaluation_profile_to_task_priority,
    derive_q8_evaluation_plan,
)
from zentex.nine_questions.q8_phase_b_realtime_gate import (
    evaluate_q8_phase_b_realtime_task_gate,
    resolve_phase_b_realtime_gate_config,
)
from zentex.tasks.models import TaskContract, TaskPriority, TaskScope, TaskStatus, TaskType, ZentexTask
from zentex.tasks.verification.models import (
    VerificationStrategy,
    VerificationType,
)
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks import build_external_task_plan
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks import build_internal_task_plan


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def normalize_q8_task_rows(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("task") or item.get("task_id") or item.get("id") or "").strip()
            if not title:
                continue
            normalized_item = dict(item)
            normalized_item.update(
                {
                    "task_id": str(item.get("task_id") or item.get("id") or f"q8-task-{index}"),
                    "title": title,
                    "reason": str(item.get("reason") or "").strip(),
                    "priority": item.get("priority"),
                    "expected_outcome": _dict_value(item.get("expected_outcome")),
                    "success_criteria": _string_list(item.get("success_criteria")),
                    "acceptance_conditions": _string_list(item.get("acceptance_conditions")),
                    "verification_method": str(item.get("verification_method") or "").strip(),
                    "risk_assessment": _dict_value(item.get("risk_assessment")),
                    "pause_conditions": _string_list(item.get("pause_conditions")),
                    "escalation_conditions": _string_list(item.get("escalation_conditions")),
                }
            )
            normalized.append(normalized_item)
        else:
            title = str(item or "").strip()
            if title:
                normalized.append(
                    {
                        "task_id": f"q8-task-{index}",
                        "title": title,
                        "reason": "",
                        "priority": None,
                        "expected_outcome": {},
                        "success_criteria": [],
                        "acceptance_conditions": [],
                        "verification_method": "",
                        "risk_assessment": {},
                        "pause_conditions": [],
                        "escalation_conditions": [],
                    }
                )
    return normalized


def stable_task_suffix(task: dict[str, Any], index: int) -> str:
    base = str(task.get("task_id") or task.get("title") or index).strip().lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in base)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or f"task-{index}"


def coerce_task_priority(value: object, default_priority: TaskPriority) -> TaskPriority:
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }
        return mapping.get(normalized, default_priority)
    if isinstance(value, int):
        if value >= 90:
            return TaskPriority.CRITICAL
        if value >= 70:
            return TaskPriority.HIGH
        if value >= 40:
            return TaskPriority.MEDIUM
        return TaskPriority.LOW
    return default_priority


def _task_executor_type(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(task.get("executor_type") or metadata.get("executor_type") or "").strip().lower()


def _q8_task_title(item: dict[str, Any], *, queue_name: str) -> str:
    raw = str(item.get("title") or item.get("task") or "").strip()
    generic = {"planned task", "q8 generated task", "task", "todo", "next task"}
    if raw and raw.lower() not in generic:
        return raw
    generated_id = str(item.get("task_id") or item.get("id") or "").strip()
    if generated_id:
        return f"Q8 {queue_name} task: {generated_id}"
    return f"Q8 {queue_name} task"


def _q8_internal_target_id(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(
        item.get("target_id")
        or metadata.get("target_id")
        or "internal:task_constraint_checker"
    ).strip()


def _q8_internal_required_capabilities(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    explicit = _string_list(item.get("required_capabilities")) or _string_list(metadata.get("required_capabilities"))
    plugin_id = _q8_internal_executor_plugin_id(item)
    return list(dict.fromkeys((explicit or ["task.constraint_checking"]) + ([plugin_id] if plugin_id else [])))


def _q8_internal_executor_plugin_id(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    target_id = _q8_internal_target_id(item)
    return str(
        item.get("internal_executor_plugin_id")
        or item.get("executor_id")
        or metadata.get("internal_executor_plugin_id")
        or metadata.get("executor_id")
        or (target_id.removeprefix("internal:") if target_id.startswith("internal:") else "")
        or "task_constraint_checker"
    ).strip()


def _q8_external_executor_type(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    executor_type = str(
        item.get("executor_type")
        or metadata.get("executor_type")
        or metadata.get("external_executor_type")
        or ""
    ).strip().lower()
    if executor_type == "connector":
        return "external_connector"
    if executor_type:
        return executor_type
    target_id = str(item.get("target_id") or metadata.get("target_id") or "").strip().lower()
    if target_id.startswith("cli:"):
        return "cli"
    if target_id.startswith("mcp:"):
        return "mcp"
    if target_id.startswith(("external_connector:", "connector:")):
        return "external_connector"
    if target_id.startswith("agent:"):
        return "agent"
    return ""


def _q8_external_target_id(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    target_id = str(item.get("target_id") or metadata.get("target_id") or "").strip()
    if target_id:
        return target_id
    executor_type = _q8_external_executor_type(item)
    if executor_type == "cli":
        tool = str(item.get("cli_tool_name") or metadata.get("cli_tool_name") or metadata.get("tool_name") or "").strip()
        return f"cli:{tool}" if tool else ""
    if executor_type == "mcp":
        server = str(item.get("mcp_server_id") or metadata.get("mcp_server_id") or metadata.get("server_id") or "").strip()
        tool = str(item.get("mcp_tool_name") or metadata.get("mcp_tool_name") or metadata.get("tool_name") or "").strip()
        return f"mcp:{server}:{tool}" if server and tool else ""
    if executor_type == "external_connector":
        connector = str(
            item.get("external_connector_id")
            or metadata.get("external_connector_id")
            or metadata.get("connector_id")
            or ""
        ).strip()
        return f"external_connector:{connector}" if connector else ""
    if executor_type == "agent":
        agent = str(item.get("agent_id") or metadata.get("agent_id") or "").strip()
        return f"agent:{agent}" if agent else ""
    return ""


def _q8_external_executor_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    executor_type = _q8_external_executor_type(item)
    target_id = _q8_external_target_id(item)
    normalized: dict[str, Any] = {
        "executor_type": executor_type,
        "external_executor_type": executor_type,
        "target_id": target_id,
    }
    capabilities = _string_list(item.get("required_capabilities")) or _string_list(metadata.get("required_capabilities"))
    if executor_type == "cli":
        tool = str(
            item.get("cli_tool_name")
            or metadata.get("cli_tool_name")
            or metadata.get("tool_name")
            or (target_id.removeprefix("cli:") if target_id.startswith("cli:") else "")
        ).strip()
        normalized["cli_tool_name"] = tool
        capabilities += ["external.cli"] + ([f"cli.{tool}"] if tool else [])
    elif executor_type == "mcp":
        server = str(item.get("mcp_server_id") or metadata.get("mcp_server_id") or "").strip()
        tool = str(item.get("mcp_tool_name") or metadata.get("mcp_tool_name") or "").strip()
        if target_id.startswith("mcp:"):
            parts = target_id.split(":", 2)
            server = server or (parts[1] if len(parts) >= 2 else "")
            tool = tool or (parts[2] if len(parts) == 3 else "")
        normalized.update({"mcp_server_id": server, "mcp_tool_name": tool})
        capabilities += ["external.mcp"] + ([f"mcp.{server}.{tool}"] if server and tool else [])
    elif executor_type == "external_connector":
        connector = str(
            item.get("external_connector_id")
            or metadata.get("external_connector_id")
            or metadata.get("connector_id")
            or (target_id.removeprefix("external_connector:") if target_id.startswith("external_connector:") else "")
        ).strip()
        capability = str(
            item.get("external_connector_capability")
            or metadata.get("external_connector_capability")
            or metadata.get("connector_capability")
            or metadata.get("capability")
            or ""
        ).strip()
        normalized.update({"external_connector_id": connector, "external_connector_capability": capability})
        capabilities += ["external.external_connector"] + (
            [f"external_connector.{connector}.{capability}"] if connector and capability else []
        )
    elif executor_type == "agent":
        agent_id = str(
            item.get("agent_id")
            or metadata.get("agent_id")
            or (target_id.removeprefix("agent:") if target_id.startswith("agent:") else "")
        ).strip()
        normalized["agent_id"] = agent_id
        capabilities += ["external.agent"] + ([f"agent.{agent_id}"] if agent_id else [])
    normalized["required_capabilities"] = list(dict.fromkeys(capabilities))
    return normalized


def _q8_runtime_instruction_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    allowed_keys = (
        "arguments",
        "cli_arguments",
        "stdin_input",
        "cli_stdin_input",
        "working_directory",
        "cli_working_directory",
        "timeout_seconds",
        "cli_timeout_seconds",
        "physical_artifacts",
        "expected_physical_artifacts",
        "evidence_paths",
        "artifact_paths",
        "expected_evidence_type",
        "side_effect_type",
        "contract",
        "verification_contract",
        "dataset_id",
        "dataset_fingerprint",
        "learned_rules_applied",
        "source_learning_trace_id",
        "source_reflection_id",
        "operator_approval",
        "is_recovery_task",
        "gap_type",
        "missing_path",
        "instructions_for_human",
        "mcp_arguments",
        "mcp_response_evidence_path",
        "response_evidence_path",
        "query_assertions",
        "mcp_query_assertions",
        "replacement_target_id",
        "replacement_target_ids",
        "preferred_replacement_target_id",
        "preferred_replacement_target_ids",
        "replacement_mcp_server_id",
        "replacement_authorization",
        "replacement_authorizations",
        "replacement_q5_q6",
        "schema_snapshot_required",
        "permission_scope_summary_required",
        "agent_task_payload",
        "task_payload",
        "external_connector_arguments",
        "connector_arguments",
        "external_plugin_path",
        "plugin_path",
        "source_signal",
        "authorization_status",
        "risk_reason",
        "q9_node_id",
        "q9_posture_source",
        "operator_approval_required",
        "evidence_ref",
        "proactive_action_kind",
        "preventive_recovery",
        "worker_dispatch_enabled",
        "selection_rationale",
        "candidate_comparison",
        "non_selected_candidates",
        "capability_action_mapping",
        "capability_health_recovery",
        "action_intent",
        "functional_plugin_ref",
        "execution_parameters",
        "security_routing",
        "expected_receipt_type",
        "initial_state",
        "internal_cognitive_task",
        "intent_name",
        "intent_description",
        "intent_objective",
        "creation_rationale",
        "task_precautions",
        "task_prohibitions",
        "task_name",
        "task_description",
        "task_goal",
        "task_creation_reason_and_basis",
        "required_capability",
        "target_engine_or_organ",
        "security_attributes",
        "resource_matching_deferred_to",
        "task_splitting_deferred_to",
        "parameter_binding_deferred_to",
    )
    preserved: dict[str, Any] = {}
    for key in allowed_keys:
        if key in metadata:
            preserved[key] = metadata[key]
        elif key in item:
            preserved[key] = item[key]
    return preserved


def _q8_generation_basis(
    *,
    snapshot_map: dict[str, dict[str, Any]],
    context_updates: dict[str, Any],
    objective_profile: dict[str, Any],
    task_queue: dict[str, Any],
    scope: TaskScope,
    item: dict[str, Any],
) -> dict[str, Any]:
    q8_snapshot = snapshot_map.get("q8") if isinstance(snapshot_map.get("q8"), dict) else {}
    question_snapshot = (
        context_updates.get("q8_q1_q7_snapshot")
        or context_updates.get("q1_q7_snapshot")
        or context_updates.get("q8_objective_and_queue", {}).get("q1_q7_snapshot")
        or {}
    )
    question_snapshot = question_snapshot if isinstance(question_snapshot, dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}
    functional_objectives = context_updates.get("q8_functional_objectives")
    functional_objectives = functional_objectives if isinstance(functional_objectives, list) else []
    data_sources = [
        key
        for key in ("q1", "q2", "q3", "q4", "q5", "q6", "q7")
        if key in question_snapshot
    ]
    data_sources += [
        "q8_objective_profile" if objective_profile else "",
        "q8_task_queue" if task_queue else "",
        "q8_persistent_task_state" if isinstance(context_updates.get("q8_persistent_task_state"), dict) else "",
        "q8_priority_baseline" if isinstance(context_updates.get("q8_priority_baseline"), dict) else "",
    ]
    generation_functions = [
        "build_q8_separated_task_plan",
        "build_internal_task_plan" if scope == TaskScope.INTERNAL else "build_external_task_plan",
        "sync_q8_tasks_to_task_service",
    ]
    plugin_refs = []
    for row in functional_objectives:
        if isinstance(row, dict):
            plugin = str(row.get("plugin_id") or row.get("id") or row.get("feature_code") or "").strip()
            if plugin:
                plugin_refs.append(plugin)
    if scope == TaskScope.INTERNAL:
        plugin_refs.append(_q8_internal_executor_plugin_id(item))
        plugin_refs += _string_list(q3.get("available_cognitive_tools"))
    else:
        executor = _q8_external_executor_metadata(item)
        plugin_refs += [
            str(executor.get("target_id") or "").strip(),
            str(executor.get("cli_tool_name") or "").strip(),
            str(executor.get("mcp_server_id") or "").strip(),
            str(executor.get("external_connector_id") or "").strip(),
            str(executor.get("agent_id") or "").strip(),
        ]
        plugin_refs += _string_list(q3.get("available_execution_tools"))
    return {
        "data_sources": [value for value in dict.fromkeys(data_sources) if value],
        "generation_functions": [value for value in dict.fromkeys(generation_functions) if value],
        "plugin_references": [value for value in dict.fromkeys(plugin_refs) if value],
        "source_trace_id": str(q8_snapshot.get("trace_id") or ""),
        "source_task_id": str(item.get("task_id") or item.get("id") or "").strip(),
    }


def _task_scope(task: dict[str, Any]) -> TaskScope:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    explicit_scope = str(task.get("task_scope") or metadata.get("task_scope") or "").strip().lower()
    if explicit_scope == TaskScope.EXTERNAL.value:
        return TaskScope.EXTERNAL
    executor_type = _task_executor_type(task)
    target_id = str(task.get("target_id") or metadata.get("target_id") or "").strip().lower()
    if executor_type in {"agent", "cli", "mcp", "external_connector", "connector"}:
        return TaskScope.EXTERNAL
    if target_id.startswith(("agent:", "cli:", "mcp:", "external_connector:", "connector:")):
        return TaskScope.EXTERNAL
    return TaskScope.INTERNAL


def _queue_with_rows(task_queue: dict[str, Any], replacements: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "next_self_tasks": replacements.get("next_self_tasks", []),
        "blocked_self_tasks": replacements.get("blocked_self_tasks", []),
        "proactive_actions": replacements.get("proactive_actions", []),
        **{
            key: value
            for key, value in task_queue.items()
            if key not in {"next_self_tasks", "blocked_self_tasks", "proactive_actions"}
        },
    }


def _q8_proactivity_evidence(task_queue: dict[str, Any], *, queue_name: str) -> dict[str, Any]:
    proactive_rows = normalize_q8_task_rows(task_queue.get("proactive_actions"))
    return {
        "status": "present" if proactive_rows else "missing",
        "source": "q8_task_queue.proactive_actions",
        "queue_name": queue_name,
        "is_proactive_task": queue_name == "proactive_actions",
        "proactive_action_count": len(proactive_rows),
        "proactive_action_ids": [str(item.get("task_id") or item.get("id") or "") for item in proactive_rows],
        "proactive_action_titles": [str(item.get("title") or "") for item in proactive_rows],
    }


def _q8_objective_fission(objective_profile: dict[str, Any], task_queue: dict[str, Any]) -> dict[str, Any]:
    proactive_rows = normalize_q8_task_rows(task_queue.get("proactive_actions"))
    return {
        "current_mission": str(
            objective_profile.get("current_mission")
            or objective_profile.get("current_primary_objective")
            or ""
        ),
        "completion_condition_count": len(_string_list(objective_profile.get("completion_conditions"))),
        "pause_condition_count": len(_string_list(objective_profile.get("pause_conditions"))),
        "escalation_condition_count": len(_string_list(objective_profile.get("escalation_conditions"))),
        "proactive_subgoal_count": len(proactive_rows),
        "proactive_subgoals": [str(item.get("title") or "") for item in proactive_rows],
    }


def build_q8_separated_task_plan(
    *,
    snapshot_map: dict[str, dict[str, Any]],
    objective_profile: dict[str, Any],
    task_queue: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]] | None = None,
    priority_baseline: dict[str, Any] | None = None,
    functional_objectives: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    q8_snapshot = snapshot_map.get("q8") if isinstance(snapshot_map.get("q8"), dict) else {}
    context_updates = q8_snapshot.get("context_updates") if isinstance(q8_snapshot.get("context_updates"), dict) else {}
    question_snapshot = (
        context_updates.get("q8_q1_q7_snapshot")
        or context_updates.get("q1_q7_snapshot")
        or context_updates.get("q8_objective_and_queue", {}).get("q1_q7_snapshot")
        or {}
    )
    question_snapshot = question_snapshot if isinstance(question_snapshot, dict) else {}
    priority = priority_baseline if isinstance(priority_baseline, dict) else {}
    functional = functional_objectives if isinstance(functional_objectives, list) else []
    task_state = normalized_task_state if isinstance(normalized_task_state, dict) else {}

    internal_queue_rows: dict[str, list[dict[str, Any]]] = {}
    external_queue_rows: dict[str, list[dict[str, Any]]] = {}
    for queue_name in ("next_self_tasks", "blocked_self_tasks", "proactive_actions"):
        internal_queue_rows[queue_name] = []
        external_queue_rows[queue_name] = []
        for item in normalize_q8_task_rows(task_queue.get(queue_name)):
            item = dict(item)
            item.setdefault("metadata", {})
            if _task_scope(item) == TaskScope.EXTERNAL:
                external_executor = _q8_external_executor_metadata(item)
                item["task_scope"] = TaskScope.EXTERNAL.value
                item["executor_type"] = external_executor["executor_type"]
                item["target_id"] = external_executor["target_id"]
                item["metadata"] = {
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "task_scope": TaskScope.EXTERNAL.value,
                    **external_executor,
                    "source_chain": "external_q8",
                }
                external_queue_rows[queue_name].append(item)
            else:
                item["task_scope"] = TaskScope.INTERNAL.value
                item["executor_type"] = "internal"
                item["target_id"] = _q8_internal_target_id(item)
                executor_plugin_id = _q8_internal_executor_plugin_id(item)
                item["metadata"] = {
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "task_scope": TaskScope.INTERNAL.value,
                    "executor_type": "internal",
                    "executor_id": executor_plugin_id,
                    "internal_executor_plugin_id": executor_plugin_id,
                    "target_id": item["target_id"],
                    "worker_dispatch_enabled": True,
                    "required_capabilities": _q8_internal_required_capabilities(item),
                    "source_chain": "internal_q8",
                }
                internal_queue_rows[queue_name].append(item)

    internal_queue = _queue_with_rows(task_queue, internal_queue_rows)
    external_queue = _queue_with_rows(task_queue, external_queue_rows)
    internal_plan = build_internal_task_plan(
        question_snapshot=question_snapshot,
        normalized_task_state=task_state,
        priority_baseline=priority,
        functional_objectives=functional,
        raw_task_queue=internal_queue,
    )
    external_plan = build_external_task_plan(
        question_snapshot=question_snapshot,
        raw_task_queue=external_queue,
    )
    return {
        "objective_profile": objective_profile,
        "internal": internal_plan,
        "external": external_plan,
        "internal_queue": internal_queue,
        "external_queue": external_queue,
        "combined_queue": _queue_with_rows(
            task_queue,
            {
                key: internal_queue_rows[key] + external_queue_rows[key]
                for key in ("next_self_tasks", "blocked_self_tasks", "proactive_actions")
            },
        ),
    }


def build_q8_task_contract(
    task: dict[str, Any],
    objective_profile: dict[str, Any],
) -> TaskContract:
    title = str(task.get("title") or "").strip()
    completion_conditions = _string_list(objective_profile.get("completion_conditions"))
    pause_conditions = list(
        dict.fromkeys(
            _string_list(task.get("pause_conditions"))
            + _string_list(objective_profile.get("pause_conditions"))
        )
    )
    escalation_conditions = list(
        dict.fromkeys(
            _string_list(task.get("escalation_conditions"))
            + _string_list(objective_profile.get("escalation_conditions"))
        )
    )
    success_criteria = _string_list(task.get("success_criteria"))
    fallback_generated = False
    if not success_criteria:
        success_criteria = completion_conditions or ([f"完成任务: {title}"] if title else [])
        fallback_generated = True

    acceptance_conditions = _string_list(task.get("acceptance_conditions")) or success_criteria
    expected_outcome = _dict_value(task.get("expected_outcome")) or {
        "summary": title,
        "source": "q8_task_contract_fallback",
    }

    risk_assessment = _dict_value(task.get("risk_assessment"))
    if fallback_generated:
        risk_assessment = {
            **risk_assessment,
            "acceptance_fallback_generated": True,
        }

    contract = TaskContract(
        expected_outcome=expected_outcome,
        success_criteria=success_criteria,
        acceptance_conditions=acceptance_conditions,
        verification_method=str(task.get("verification_method") or "rule_based_outcome_contract"),
        risk_assessment=risk_assessment,
        pause_conditions=pause_conditions,
        escalation_conditions=escalation_conditions,
        verification={
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "q8_required_outcome_evidence",
                    "verifier_type": VerificationType.RULE_BASED.value,
                    "retry_on_failure": False,
                    "max_retries": 0,
                    "config": {
                        "rules": [
                            {"type": "required_field", "field": "actual_outcome"},
                            {"type": "required_field", "field": "evidence"},
                        ]
                    },
                }
            ],
        },
    )
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    explicit_contract = task.get("contract") if isinstance(task.get("contract"), dict) else None
    explicit_verification = task.get("verification_contract")
    if not isinstance(explicit_verification, dict):
        explicit_verification = metadata.get("verification_contract")
    if not isinstance(explicit_verification, dict):
        explicit_verification = None
    if explicit_contract or explicit_verification:
        payload = contract.model_dump(mode="json")
        if explicit_contract:
            payload.update(explicit_contract)
        if explicit_verification:
            payload["verification"] = explicit_verification.get("verification", explicit_verification)
        return TaskContract(**payload)
    return contract


def sync_task_record_fields(
    task_service: Any,
    task: ZentexTask,
    *,
    title: str,
    remarks: str,
    priority: TaskPriority,
    tags: list[str],
    metadata: dict[str, Any],
    contract: TaskContract | None = None,
) -> None:
    task.title = title
    task.remarks = remarks
    task.priority = priority
    task.tags = list(tags)
    task.metadata = dict(metadata)
    if contract is not None:
        task.contract = contract
    task.last_updated_at = datetime.now(timezone.utc)
    if hasattr(task_service, "_shared_tasks"):
        task_service._shared_tasks.set(task.task_id, task)
    sync_fn = getattr(task_service, "_sync_task_to_database", None)
    if callable(sync_fn):
        sync_fn(task)


def sync_task_relationship_fields(
    task_service: Any,
    task: ZentexTask,
    *,
    parent_task_id: str | None,
    depends_on: list[str],
) -> None:
    changed = False
    if task.parent_task_id != parent_task_id:
        task.parent_task_id = parent_task_id
        changed = True
    if list(task.depends_on or []) != list(depends_on):
        task.depends_on = list(depends_on)
        changed = True
    if not changed:
        return

    task.last_updated_at = datetime.now(timezone.utc)
    if hasattr(task_service, "_shared_tasks"):
        task_service._shared_tasks.set(task.task_id, task)
    if hasattr(task_service, "_tasks"):
        task_service._tasks[task.task_id] = task
    sync_fn = getattr(task_service, "_sync_task_to_database", None)
    if callable(sync_fn):
        sync_fn(task)


def _find_existing_task_by_idempotency_key(task_service: Any, idempotency_key: str) -> ZentexTask | None:
    idempotency_dao = getattr(task_service, "_idempotency_dao", None)
    if idempotency_dao is not None:
        check_idempotency = getattr(idempotency_dao, "check_idempotency", None)
        if callable(check_idempotency):
            task_id = check_idempotency(idempotency_key)
            if task_id:
                task = task_service.get_task(task_id) if callable(getattr(task_service, "get_task", None)) else None
                if task is not None:
                    return task
    shared_idempotency = getattr(task_service, "_shared_idempotency", None)
    if shared_idempotency is not None:
        task_id = shared_idempotency.get(idempotency_key)
        if task_id:
            task = task_service.get_task(task_id) if callable(getattr(task_service, "get_task", None)) else None
            if task is not None:
                return task
    return None


async def sync_q8_tasks_to_task_service(
    *,
    task_service: Any,
    session_id: str,
    snapshot_map: dict[str, dict[str, Any]],
    logger: Optional[Any] = None,
    allow_q9_posture_overlay: bool = True,
) -> None:
    if logger is not None:
        logger.info(
            "Q8 task synchronization is disabled; Q8 emits abstract intent only and downstream orchestration owns task persistence.",
            extra={"session_id": session_id},
        )
    return

    if task_service is None:
        return

    q8_snapshot = snapshot_map.get("q8")
    if not isinstance(q8_snapshot, dict):
        return

    context_updates = q8_snapshot.get("context_updates")
    context_updates = context_updates if isinstance(context_updates, dict) else {}
    result_payload = q8_snapshot.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}

    objective_profile = (
        context_updates.get("q8_objective_profile")
        or result_payload.get("objective_profile")
        or {}
    )
    objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
    task_queue = (
        context_updates.get("q8_task_queue")
        or result_payload.get("task_queue")
        or {}
    )
    task_queue = task_queue if isinstance(task_queue, dict) else {}
    separated_plan = build_q8_separated_task_plan(
        snapshot_map=snapshot_map,
        objective_profile=objective_profile,
        task_queue=task_queue,
        normalized_task_state=context_updates.get("q8_persistent_task_state")
        if isinstance(context_updates.get("q8_persistent_task_state"), dict)
        else None,
        priority_baseline=context_updates.get("q8_priority_baseline")
        if isinstance(context_updates.get("q8_priority_baseline"), dict)
        else None,
        functional_objectives=context_updates.get("q8_functional_objectives")
        if isinstance(context_updates.get("q8_functional_objectives"), list)
        else None,
    )
    task_queue = separated_plan["combined_queue"]

    current_mission = str(
        objective_profile.get("current_mission")
        or objective_profile.get("current_primary_objective")
        or q8_snapshot.get("summary")
        or "Q8 generated task"
    ).strip()

    queue_specs = [
        ("next_self_tasks", TaskStatus.TODO, TaskPriority.HIGH),
        ("blocked_self_tasks", TaskStatus.BLOCKED, TaskPriority.MEDIUM),
        ("proactive_actions", TaskStatus.TODO, TaskPriority.MEDIUM),
    ]
    evaluation_plan = (
        derive_q8_evaluation_plan(snapshot_map)
        if allow_q9_posture_overlay
        else None
    )
    phase_b_realtime_gate_config = resolve_phase_b_realtime_gate_config(
        _dict_value(
            context_updates.get("phase_b_realtime_gate")
            or result_payload.get("phase_b_realtime_gate")
        )
    )

    existing_tasks = []
    list_tasks_fn = getattr(task_service, "list_tasks", None)
    if callable(list_tasks_fn):
        existing_tasks = list(
            list_tasks_fn(
                source_module="nine_questions.q8",
                metadata_filters={"session_id": session_id},
                limit=1000,
                offset=0,
            )
            or []
        )
    existing_by_key: dict[str, ZentexTask] = {}
    existing_by_id: dict[str, ZentexTask] = {}
    for task in existing_tasks:
        existing_by_id[str(task.task_id)] = task
        metadata = getattr(task, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata.get("source") == "nine_questions.q8" and metadata.get("session_id") == session_id:
            existing_by_key[str(task.idempotency_key)] = task

    desired_keys: set[str] = set()
    synced_tasks_by_logical_id: dict[str, ZentexTask] = {}
    relationship_rows: list[tuple[ZentexTask, dict[str, Any]]] = []

    for queue_name, target_status, default_priority in queue_specs:
        for index, item in enumerate(normalize_q8_task_rows(task_queue.get(queue_name))):
            suffix = stable_task_suffix(item, index)
            idempotency_key = f"nineq:{session_id}:q8:{queue_name}:{suffix}"
            desired_keys.add(idempotency_key)

            title = _q8_task_title(item, queue_name=queue_name)
            reason = str(item.get("reason") or "").strip()
            item_success_criteria = _string_list(item.get("success_criteria"))
            item_verification_method = str(item.get("verification_method") or "").strip()
            remarks_parts = [f"目标: {current_mission}", f"执行队列: {queue_name}"]
            if reason:
                remarks_parts.append(f"原因: {reason}")
            if item_success_criteria:
                remarks_parts.append("成功条件: " + "；".join(item_success_criteria[:3]))
            if item_verification_method:
                remarks_parts.append(f"验证方式: {item_verification_method}")
            base_priority = coerce_task_priority(item.get("priority"), default_priority)
            if evaluation_plan is not None:
                priority_decision = apply_evaluation_profile_to_task_priority(
                    task=item,
                    base_priority=base_priority,
                    evaluation_plan=evaluation_plan,
                )
            else:
                priority_decision = apply_evaluation_profile_to_task_priority(
                    task=item,
                    base_priority=base_priority,
                    evaluation_plan=derive_q8_evaluation_plan({}),
                )
                priority_decision.metadata.update(
                    {
                        "boundary_policy": "q8_core_does_not_consume_q9_posture",
                        "missing_sources": (
                            ["q9_posture_overlay_disabled_for_q8_core"]
                            if isinstance(snapshot_map.get("q9"), dict)
                            else ["q9.snapshot"]
                        ),
                        "applied_rules": ["base_q8_priority"],
                    }
                )
            item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            scope = _task_scope(item)
            executor_type = _task_executor_type(item)
            if scope == TaskScope.INTERNAL:
                executor_type = "internal"
            elif not executor_type:
                executor_type = _q8_external_executor_type(item)
            target_id = str(item.get("target_id") or item_metadata.get("target_id") or "").strip()
            if scope == TaskScope.INTERNAL:
                target_id = target_id or "internal:task_constraint_checker"
            else:
                target_id = target_id or _q8_external_target_id(item)
            internal_executor_plugin_id = _q8_internal_executor_plugin_id(item) if scope == TaskScope.INTERNAL else ""
            external_executor = _q8_external_executor_metadata(item) if scope == TaskScope.EXTERNAL else {}
            executor_id = internal_executor_plugin_id if scope == TaskScope.INTERNAL else target_id
            worker_dispatch_enabled = bool(scope == TaskScope.EXTERNAL and target_id)
            if scope == TaskScope.INTERNAL:
                worker_dispatch_enabled = True
            required_capabilities = (
                _q8_internal_required_capabilities(item)
                if scope == TaskScope.INTERNAL
                else list(external_executor.get("required_capabilities") or [])
            )
            generation_basis = _q8_generation_basis(
                snapshot_map=snapshot_map,
                context_updates=context_updates,
                objective_profile=objective_profile,
                task_queue=task_queue,
                scope=scope,
                item=item,
            )
            if not worker_dispatch_enabled:
                remarks_parts.append(
                    "执行方: internal:task_constraint_checker"
                    if scope == TaskScope.INTERNAL
                    else "执行方: 待指定外部执行端"
                )
            else:
                remarks_parts.append(f"执行方: {target_id}")
            if required_capabilities:
                capability_label = "内部功能/插件能力" if scope == TaskScope.INTERNAL else "外部功能/插件能力"
                remarks_parts.append(f"{capability_label}: " + "；".join(required_capabilities[:6]))
            if generation_basis["data_sources"]:
                remarks_parts.append("生成依据数据: " + "；".join(generation_basis["data_sources"][:8]))
            if generation_basis["generation_functions"]:
                remarks_parts.append("生成依据功能: " + "；".join(generation_basis["generation_functions"][:6]))
            if generation_basis["plugin_references"]:
                remarks_parts.append("生成依据插件/执行端: " + "；".join(generation_basis["plugin_references"][:8]))
            remarks = "\n".join(remarks_parts)
            execution_metadata = {
                "internal_executor_plugin_id": internal_executor_plugin_id,
            } if scope == TaskScope.INTERNAL else dict(external_executor)
            metadata = {
                "source": "nine_questions.q8",
                "source_module": "nine_questions.q8",
                "session_id": session_id,
                "question_id": "q8",
                "queue_name": queue_name,
                "q8_generated_task_id": str(item.get("task_id") or item.get("id") or "").strip(),
                "q8_generated_task_uid": idempotency_key,
                "task_scope": scope.value,
                "executor_type": executor_type,
                "executor_id": executor_id,
                "required_capabilities": required_capabilities,
                "worker_dispatch_enabled": worker_dispatch_enabled,
                "source_chain": "external_q8" if scope == TaskScope.EXTERNAL else "internal_q8",
                "target_id": target_id,
                "generation_basis": generation_basis,
                **execution_metadata,
                **_q8_runtime_instruction_metadata(item),
                "objective": current_mission,
                "raw_payload": item,
                "objective_profile": objective_profile,
                "q8_separated_task_plan": {
                    "internal_generated": separated_plan["internal"]["generated"],
                    "external_generated": separated_plan["external"]["generated"],
                },
                "evaluation_profile": evaluation_plan.evaluation_profile if evaluation_plan is not None else {},
                "phase_a_evaluation": priority_decision.metadata,
                "completion_conditions": _string_list(objective_profile.get("completion_conditions")),
                "pause_conditions": _string_list(objective_profile.get("pause_conditions")),
                "escalation_conditions": _string_list(objective_profile.get("escalation_conditions")),
                "expected_outcome": _dict_value(item.get("expected_outcome")),
                "success_criteria": _string_list(item.get("success_criteria")),
                "acceptance_conditions": _string_list(item.get("acceptance_conditions")),
                "verification_method": str(item.get("verification_method") or "").strip(),
                "risk_assessment": _dict_value(item.get("risk_assessment")),
                "trace_id": str(q8_snapshot.get("trace_id") or ""),
            }
            tags = ["nine-questions", "q8", queue_name]
            priority = priority_decision.priority
            effective_status = target_status
            initial_state = str(
                item.get("initial_state")
                or item_metadata.get("initial_state")
                or item.get("status")
                or ""
            ).strip().lower()
            if initial_state == TaskStatus.WAITING_CONFIRMATION.value:
                effective_status = TaskStatus.WAITING_CONFIRMATION
            elif initial_state == TaskStatus.BLOCKED.value:
                effective_status = TaskStatus.BLOCKED
            proactivity_evidence = _q8_proactivity_evidence(task_queue, queue_name=queue_name)
            objective_fission = _q8_objective_fission(objective_profile, task_queue)
            risk_posture_basis = {
                "phase_a_evaluation": priority_decision.metadata,
                "evaluation_profile": evaluation_plan.evaluation_profile if evaluation_plan is not None else {},
                "phase_b_realtime_gate_enabled": bool(phase_b_realtime_gate_config["enabled"]),
                "target_status": getattr(target_status, "value", target_status),
                "final_status": getattr(effective_status, "value", effective_status),
                "base_priority": getattr(base_priority, "value", base_priority),
                "final_priority": getattr(priority, "value", priority),
            }
            if phase_b_realtime_gate_config["enabled"]:
                phase_b_decision = evaluate_q8_phase_b_realtime_task_gate(
                    task=item,
                    target_status=target_status,
                    base_priority=priority,
                    accept_threshold=phase_b_realtime_gate_config["accept_threshold"],
                    reject_threshold=phase_b_realtime_gate_config["reject_threshold"],
                )
                priority = phase_b_decision.final_priority
                effective_status = phase_b_decision.final_status
                metadata["phase_b_realtime_gate"] = phase_b_decision.to_metadata()
                risk_posture_basis["phase_b_realtime_gate"] = phase_b_decision.to_metadata()
                risk_posture_basis["final_status"] = getattr(effective_status, "value", effective_status)
                risk_posture_basis["final_priority"] = getattr(priority, "value", priority)
            if initial_state == TaskStatus.WAITING_CONFIRMATION.value:
                effective_status = TaskStatus.WAITING_CONFIRMATION
            elif initial_state == TaskStatus.BLOCKED.value:
                effective_status = TaskStatus.BLOCKED
            risk_posture_basis["final_status"] = getattr(effective_status, "value", effective_status)
            metadata.update(
                {
                    "proactivity_status": proactivity_evidence["status"],
                    "proactivity_evidence": proactivity_evidence,
                    "proactive_actions": proactivity_evidence["proactive_action_titles"],
                    "objective_fission": objective_fission,
                    "risk_posture_basis": risk_posture_basis,
                }
            )
            contract = build_q8_task_contract(item, objective_profile)
            existing = existing_by_key.get(idempotency_key) or _find_existing_task_by_idempotency_key(
                task_service,
                idempotency_key,
            )
            if existing is not None:
                if existing.status != effective_status:
                    try:
                        await task_service.update_task_status(existing.task_id, effective_status, remarks)
                    except Exception:
                        if logger is not None:
                            logger.warning(
                                "Failed to update synced Q8 task status",
                                extra={"task_id": existing.task_id, "queue_name": queue_name},
                            )
                sync_task_record_fields(
                    task_service,
                    existing,
                    title=title,
                    remarks=remarks,
                    priority=priority,
                    tags=tags,
                    metadata=metadata,
                    contract=contract,
                )
                logical_id = str(item.get("task_id") or item.get("id") or "").strip()
                if logical_id:
                    synced_tasks_by_logical_id[logical_id] = existing
                relationship_rows.append((existing, item))
                continue

            create_task_fn = getattr(task_service, "create_task", None)
            if callable(create_task_fn):
                created = await create_task_fn(
                    {
                        "idempotency_key": idempotency_key,
                        "title": title,
                        "task_type": TaskType.COGNITIVE_STEP,
                        "task_scope": scope,
                        "status": effective_status,
                        "priority": priority,
                        "originator_id": session_id,
                        "target_id": target_id or None,
                        "remarks": remarks,
                        "tags": tags,
                        "metadata": metadata,
                        "contract": contract,
                    }
                )
                logical_id = str(item.get("task_id") or item.get("id") or "").strip()
                if logical_id:
                    synced_tasks_by_logical_id[logical_id] = created
                relationship_rows.append((created, item))

    synced_tasks_by_physical_id = {task.task_id: task for task in synced_tasks_by_logical_id.values()}
    synced_tasks_by_physical_id.update(existing_by_id)

    def resolve_task_ref(value: object) -> str:
        ref = str(value or "").strip()
        if not ref:
            return ""
        if ref in synced_tasks_by_logical_id:
            return synced_tasks_by_logical_id[ref].task_id
        if ref in synced_tasks_by_physical_id:
            return ref
        return ""

    for task, item in relationship_rows:
        item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        parent_ref = item.get("parent_task_id") or item_metadata.get("parent_task_id")
        parent_task_id = resolve_task_ref(parent_ref)
        dependency_refs = _string_list(item.get("depends_on")) or _string_list(item_metadata.get("depends_on"))
        depends_on = [resolved for ref in dependency_refs if (resolved := resolve_task_ref(ref))]
        sync_task_relationship_fields(
            task_service,
            task,
            parent_task_id=parent_task_id or None,
            depends_on=list(dict.fromkeys(depends_on)),
        )

    for idempotency_key, task in existing_by_key.items():
        if idempotency_key in desired_keys:
            continue
        if task.status in {TaskStatus.TODO, TaskStatus.BLOCKED, TaskStatus.SUSPENDED, TaskStatus.DONE}:
            try:
                await task_service.update_task_status(
                    task.task_id,
                    TaskStatus.ARCHIVED,
                    remarks="Archived because Q8 regenerated a new task set.",
                )
            except Exception:
                if logger is not None:
                    logger.warning("Failed to archive stale Q8 synced task", extra={"task_id": task.task_id})
        elif task.status in {TaskStatus.IN_PROGRESS, TaskStatus.WAITING_CONFIRMATION}:
            update_metadata_fn = getattr(task_service, "update_task_metadata", None)
            if callable(update_metadata_fn):
                try:
                    await update_metadata_fn(
                        task.task_id,
                        {
                            "q8_archive_blocked": {
                                "reason": "stale_q8_task_is_active",
                                "idempotency_key": idempotency_key,
                                "active_status": getattr(task.status, "value", task.status),
                                "desired_idempotency_keys": sorted(desired_keys),
                                "recommended_action": "wait_for_terminal_state_before_archive_or_reconcile_manually",
                            }
                        },
                        remarks="Archive deferred because Q8 regenerated the queue while this stale task is still active.",
                    )
                except Exception:
                    if logger is not None:
                        logger.warning("Failed to record stale active Q8 archive block", extra={"task_id": task.task_id})
