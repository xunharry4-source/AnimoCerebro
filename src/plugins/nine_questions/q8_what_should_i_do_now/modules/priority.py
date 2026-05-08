from __future__ import annotations

from typing import Any


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def normalize_snapshot_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).strip()}


def normalize_task_state(raw: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, list[dict[str, Any]]] = {}
    for status_key, value in raw.items():
        entries: list[dict[str, Any]] = []
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    entries.append(
                        {
                            "id": str(item.get("id") or f"{status_key}-{index}"),
                            "title": normalize_text(
                                item.get("title") or item.get("task") or item.get("id") or f"{status_key}-{index}"
                            ),
                            "status": normalize_text(item.get("status") or status_key),
                            "priority": item.get("priority") if isinstance(item.get("priority"), int) else None,
                            "reason": normalize_text(item.get("reason") or item.get("blocker_reason")),
                        }
                    )
                else:
                    text = normalize_text(item)
                    if text:
                        entries.append(
                            {
                                "id": f"{status_key}-{index}",
                                "title": text,
                                "status": normalize_text(status_key),
                                "priority": None,
                                "reason": "",
                            }
                        )
        if entries:
            normalized[str(status_key)] = entries
    return normalized


def normalize_functional_objectives(raw_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        plugin_id = normalize_text(item.get("plugin_id"))
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        normalized.append(
            {
                "plugin_id": plugin_id,
                "current_mission": normalize_text(result.get("current_mission")),
                "primary_objectives": coerce_string_list(result.get("primary_objectives")),
                "secondary_objectives": coerce_string_list(result.get("secondary_objectives")),
                "current_phase_tasks": coerce_string_list(result.get("current_phase_tasks")),
                "priority_order": coerce_string_list(result.get("priority_order")),
                "completion_conditions": coerce_string_list(result.get("completion_conditions")),
                "pause_conditions": coerce_string_list(result.get("pause_conditions")),
                "escalation_conditions": coerce_string_list(result.get("escalation_conditions")),
                "next_self_tasks": result.get("next_self_tasks") if isinstance(result.get("next_self_tasks"), list) else [],
                "blocked_self_tasks": result.get("blocked_self_tasks") if isinstance(result.get("blocked_self_tasks"), list) else [],
                "proactive_actions": result.get("proactive_actions") if isinstance(result.get("proactive_actions"), list) else [],
            }
        )
    return normalized


def derive_priority_baseline(
    snapshot: dict[str, Any],
    question_snapshot: dict[str, Any],
    task_state: dict[str, list[dict[str, Any]]],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    q4 = question_snapshot.get("q4") if isinstance(question_snapshot.get("q4"), dict) else {}
    q5 = question_snapshot.get("q5") if isinstance(question_snapshot.get("q5"), dict) else {}
    q6 = question_snapshot.get("q6") if isinstance(question_snapshot.get("q6"), dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}

    immediate_tasks: list[str] = []
    blocked_tasks: list[str] = []
    proactive_actions: list[str] = []
    escalation_conditions: list[str] = []

    actionable_space = coerce_string_list(q4.get("actionable_space"))
    resource_gaps = coerce_string_list(q3.get("missing_critical_assets"))
    absolute_red_lines = coerce_string_list(q6.get("absolute_red_lines"))
    forbidden_actions = coerce_string_list(q5.get("explicitly_forbidden_actions"))

    if actionable_space:
        immediate_tasks.extend([f"execute within validated action space: {item}" for item in actionable_space])
    else:
        immediate_tasks.append("rebuild actionable space evidence before execution")

    if resource_gaps:
        blocked_tasks.extend([f"resolve resource gap: {item}" for item in resource_gaps])
    escalation_conditions.extend([f"red-line conflict detected: {item}" for item in absolute_red_lines])
    escalation_conditions.extend([f"forbidden action requested: {item}" for item in forbidden_actions])

    for status_key, entries in task_state.items():
        for entry in entries:
            title = normalize_text(entry.get("title"))
            reason = normalize_text(entry.get("reason"))
            if status_key in {"blocked", "waiting", "paused"}:
                blocked_tasks.append(f"{title}: {reason}" if reason else title)
            else:
                immediate_tasks.append(title)

    for item in functional_objectives:
        immediate_tasks.extend(coerce_string_list(item.get("current_phase_tasks")))
        proactive_actions.extend(coerce_string_list(item.get("priority_order")))
        escalation_conditions.extend(coerce_string_list(item.get("escalation_conditions")))

    return {
        "immediate_tasks": list(dict.fromkeys(item for item in immediate_tasks if normalize_text(item))),
        "blocked_tasks": list(dict.fromkeys(item for item in blocked_tasks if normalize_text(item))),
        "proactive_actions": list(dict.fromkeys(item for item in proactive_actions if normalize_text(item))),
        "escalation_conditions": list(
            dict.fromkeys(item for item in escalation_conditions if normalize_text(item))
        ),
    }


def merge_string_lists(primary: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(coerce_string_list(primary) + coerce_string_list(baseline)))


def merge_task_rows(primary: list[dict[str, Any]], baseline_titles: list[str], status: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in primary:
        if not isinstance(item, dict):
            continue
        title = normalize_text(item.get("title") or item.get("task") or item.get("task_id") or item.get("id"))
        if not title or title in seen:
            continue
        seen.add(title)
        merged.append(dict(item))
    for index, title in enumerate(coerce_string_list(baseline_titles)):
        if title in seen:
            continue
        seen.add(title)
        merged.append({"task_id": f"{status}-{index}", "title": title, "status": status})
    return merged


def _normalize_queue_entry(item: object, *, index: int, status: str) -> dict[str, Any] | None:
    if isinstance(item, dict):
        task_id = normalize_text(item.get("task_id") or item.get("id") or f"{status}-{index}")
        title = normalize_text(item.get("title") or item.get("task") or task_id)
        if not title:
            return None
        normalized = dict(item)
        normalized["task_id"] = task_id
        normalized["title"] = title
        normalized["status"] = normalize_text(item.get("status") or status) or status
        return normalized

    title = normalize_text(item)
    if not title:
        return None
    return {"task_id": f"{status}-{index}", "title": title, "status": status}


def _queue_entries(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    text = normalize_text(value)
    return [text] if text else []


def _stable_fragment(value: object, fallback: str) -> str:
    text = normalize_text(value).lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or fallback


_INTERNAL_COGNITIVE_TASK_KEYS = {
    "intent_name",
    "intent_description",
    "intent_objective",
    "creation_rationale",
    "task_precautions",
    "task_prohibitions",
    "required_capability",
    "risk_level",
    "target_engine_or_organ",
    "security_attributes",
    "initial_state",
}
_INTERNAL_ENGINE_ORGANS = {
    "MemoryEngine",
    "ReflectionEngine",
    "LearningEngine",
    "EvolutionEngine",
    "B1_WorkingMemory",
    "B4_ThoughtSandbox",
    "B5_ConflictEngine",
}
_OBJECTIVE_PROFILE_KEYS = {
    "current_mission",
    "basis_and_traceability",
    "primary_objectives",
    "secondary_objectives",
    "completion_conditions",
    "pause_conditions",
    "escalation_conditions",
}
_LEGACY_OBJECTIVE_PROFILE_KEYS = {
    "current_mission",
    "mission_rationale",
    "primary_objectives",
    "secondary_objectives",
    "completion_conditions",
    "pause_conditions",
    "escalation_conditions",
    "question_driver_refs",
}
_BASIS_AND_TRACEABILITY_KEYS = {
    "q1_environment_bases": ("environment_signal_name", "trigger_reason"),
    "q2_asset_support_bases": ("asset_function_name", "support_logic"),
    "q3_role_alignment": ("capability_name", "posture_adjustment"),
    "q7_boundary_checks": ("checked_risk_point", "compliance_reason"),
}
_EXTERNAL_BASIS_AND_TRACEABILITY_KEYS = {
    "q1_environment_bases": ("environment_signal_name", "trigger_reason"),
    "q2_asset_support_bases": ("asset_function_name", "support_logic"),
    "q3_role_alignment": ("capability_name", "posture_adjustment"),
    "q7_boundary_checks": ("checked_risk_point", "compliance_reason"),
}
_BASIS_AND_TRACEABILITY_SCHEMAS = (
    _BASIS_AND_TRACEABILITY_KEYS,
    _EXTERNAL_BASIS_AND_TRACEABILITY_KEYS,
)
_FORBIDDEN_INTERNAL_SIDE_EFFECT_MARKERS = (
    "git_push",
    "file_writer",
    "http_request",
    "write_file",
    "delete_file",
    "shell",
    "cli:",
    "mcp:",
    "agent:",
    "external_connector:",
    "network",
    "http",
    "post",
    "put",
    "patch",
    "delete",
    "remove",
    "push",
    "写入文件",
    "删除文件",
    "网络请求",
    "提交",
    "推送",
)
_OBJECTIVE_PROFILE_SIDE_EFFECT_MARKERS = (
    "write_file",
    "delete_file",
    "git_push",
    "systemctl",
    "shell",
    "cli:",
    "mcp:",
    "agent:",
    "external_connector:",
    "执行脚本",
    "执行命令",
    "修改文件",
    "删除文件",
    "写入文件",
    "发起网络请求",
    "调用外部工具",
    "下发命令",
)
_CONCRETE_PLUGIN_MARKERS = (
    "plugin",
    "_v",
    "connector",
    "adapter",
    "tool:",
    "cli:",
    "mcp:",
    "agent:",
)


def normalize_q8_internal_cognitive_tasks(
    raw: object,
    *,
    q2_cognitive_plugins: list[str] | None = None,
    q2_functional_plugins: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    objective_tasks = _objective_profile_to_internal_tasks(raw)
    if objective_tasks is not None:
        return objective_tasks
    tasks = raw.get("internal_cognitive_tasks")
    if not isinstance(tasks, list):
        return []

    cognitive_capabilities = [
        normalize_text(item)
        for item in (q2_cognitive_plugins or [])
        if normalize_text(item)
    ]
    functional_refs = {normalize_text(item) for item in (q2_functional_plugins or []) if normalize_text(item)}

    normalized_tasks: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        if set(item.keys()) != _INTERNAL_COGNITIVE_TASK_KEYS:
            continue

        intent_name = normalize_text(item.get("intent_name"))
        intent_description = normalize_text(item.get("intent_description"))
        intent_objective = normalize_text(item.get("intent_objective"))
        creation_rationale = normalize_text(item.get("creation_rationale"))
        task_precautions = coerce_string_list(item.get("task_precautions"))
        task_prohibitions = coerce_string_list(item.get("task_prohibitions"))
        required_capability = normalize_text(item.get("required_capability"))
        required_capability_lower = required_capability.lower()
        if not intent_name or not intent_description or not intent_objective or not creation_rationale or not required_capability:
            continue
        if not isinstance(item.get("task_precautions"), list) or not isinstance(item.get("task_prohibitions"), list):
            continue
        if required_capability in functional_refs:
            continue
        if any(marker in required_capability_lower for marker in _CONCRETE_PLUGIN_MARKERS):
            continue

        risk_level = normalize_text(item.get("risk_level")).lower()
        if risk_level not in _RISK_LEVELS:
            continue
        if risk_level in {"high", "critical"}:
            continue

        task_text = (
            f"{intent_name} {intent_description} {intent_objective} {creation_rationale} "
            f"{' '.join(task_precautions)} {required_capability}"
        ).lower()
        if any(marker in task_text for marker in _FORBIDDEN_INTERNAL_SIDE_EFFECT_MARKERS):
            continue

        target_engine_or_organ = normalize_text(item.get("target_engine_or_organ"))
        if target_engine_or_organ not in _INTERNAL_ENGINE_ORGANS:
            continue

        security_attributes = item.get("security_attributes")
        if not isinstance(security_attributes, dict):
            continue
        if security_attributes.get("read_only") is not True or security_attributes.get("side_effect_free") is not True:
            continue

        if normalize_text(item.get("initial_state")).lower() != "queued":
            continue

        normalized_tasks.append(
            {
                "intent_name": intent_name,
                "intent_description": intent_description,
                "intent_objective": intent_objective,
                "creation_rationale": creation_rationale,
                "task_precautions": task_precautions,
                "task_prohibitions": task_prohibitions,
                "required_capability": required_capability,
                "risk_level": risk_level,
                "target_engine_or_organ": target_engine_or_organ,
                "security_attributes": {
                    "read_only": True,
                    "side_effect_free": True,
                },
                "initial_state": "queued",
            }
        )
    return normalized_tasks


def _normalize_basis_and_traceability(value: object) -> dict[str, list[dict[str, str]]] | None:
    if not isinstance(value, dict):
        return None
    for schema in _BASIS_AND_TRACEABILITY_SCHEMAS:
        normalized: dict[str, list[dict[str, str]]] = {}
        schema_matches = True
        for key, required_fields in schema.items():
            raw_items = value.get(key)
            if not isinstance(raw_items, list):
                schema_matches = False
                break
            rows: list[dict[str, str]] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    schema_matches = False
                    break
                row: dict[str, str] = {}
                for field in required_fields:
                    text = normalize_text(item.get(field))
                    if not text:
                        schema_matches = False
                        break
                    row[field] = text
                if not schema_matches:
                    break
                rows.append(row)
            if not schema_matches:
                break
            normalized[key] = rows
        if schema_matches:
            return normalized
    return None


def _basis_traceability_summary(basis: dict[str, list[dict[str, str]]] | None) -> str:
    if not isinstance(basis, dict):
        return ""
    fragments: list[str] = []
    for key in basis:
        for item in basis.get(key) or []:
            fragments.extend(normalize_text(value) for value in item.values() if normalize_text(value))
    return "；".join(dict.fromkeys(fragments))


def _basis_question_driver_refs(basis: dict[str, list[dict[str, str]]] | None) -> list[str]:
    if not isinstance(basis, dict):
        return []
    refs: list[str] = []
    for key, rows in basis.items():
        if rows:
            refs.append(key)
    return refs


def _objective_profile_from_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    objective = raw.get("ObjectiveProfile")
    if not isinstance(objective, dict):
        return None
    objective_keys = set(objective.keys())

    current_mission = normalize_text(objective.get("current_mission"))
    if not current_mission:
        return None
    basis_and_traceability: dict[str, list[dict[str, str]]] | None = None
    if objective_keys == _OBJECTIVE_PROFILE_KEYS:
        basis_and_traceability = _normalize_basis_and_traceability(objective.get("basis_and_traceability"))
        if basis_and_traceability is None:
            return None
        mission_rationale = _basis_traceability_summary(basis_and_traceability)
        question_driver_refs = _basis_question_driver_refs(basis_and_traceability)
    elif objective_keys == _LEGACY_OBJECTIVE_PROFILE_KEYS:
        mission_rationale = normalize_text(objective.get("mission_rationale"))
        question_driver_refs = coerce_string_list(objective.get("question_driver_refs"))
        if not mission_rationale:
            return None
    else:
        return None
    for key in (
        "primary_objectives",
        "secondary_objectives",
        "completion_conditions",
        "pause_conditions",
        "escalation_conditions",
    ):
        if not isinstance(objective.get(key), list):
            return None

    primary_objectives = coerce_string_list(objective.get("primary_objectives"))
    secondary_objectives = coerce_string_list(objective.get("secondary_objectives"))
    completion_conditions = coerce_string_list(objective.get("completion_conditions"))
    pause_conditions = coerce_string_list(objective.get("pause_conditions"))
    escalation_conditions = coerce_string_list(objective.get("escalation_conditions"))
    if not primary_objectives:
        primary_objectives = [current_mission]

    return {
        "current_mission": current_mission,
        "mission_rationale": mission_rationale,
        "basis_and_traceability": basis_and_traceability or {},
        "primary_objectives": primary_objectives,
        "secondary_objectives": secondary_objectives,
        "completion_conditions": completion_conditions,
        "pause_conditions": pause_conditions,
        "escalation_conditions": escalation_conditions,
        "question_driver_refs": question_driver_refs,
    }


def _objective_profile_to_internal_tasks(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
    objective = _objective_profile_from_raw(raw)
    if objective is None:
        return None

    task_text = " ".join(
        [
            objective["current_mission"],
            objective["mission_rationale"],
            " ".join(objective["primary_objectives"]),
            " ".join(objective["secondary_objectives"]),
            " ".join(objective["question_driver_refs"]),
        ]
    ).lower()
    if any(marker in task_text for marker in _OBJECTIVE_PROFILE_SIDE_EFFECT_MARKERS):
        return []

    task_prohibitions = [
        "禁止执行任何外部物理副作用操作",
        "禁止修改文件、执行脚本、发起网络请求或调用外部工具",
        "必须保持 read_only=True 且 side_effect_free=True",
    ]
    normalized_tasks: list[dict[str, Any]] = []
    for index, objective_text in enumerate(objective["primary_objectives"]):
        intent_name = objective["current_mission"] if index == 0 else objective_text
        normalized_tasks.append(
            {
                "intent_name": intent_name,
                "intent_description": objective_text,
                "intent_objective": objective_text,
                "creation_rationale": objective["mission_rationale"],
                "mission_rationale": objective["mission_rationale"],
                "task_precautions": objective["pause_conditions"],
                "task_prohibitions": task_prohibitions,
                "required_capability": "strategic_alignment_reasoning",
                "risk_level": "low",
                "target_engine_or_organ": "ReflectionEngine",
                "security_attributes": {
                    "read_only": True,
                    "side_effect_free": True,
                },
                "initial_state": "queued",
                "question_driver_refs": objective["question_driver_refs"],
                "completion_conditions": objective["completion_conditions"],
                "escalation_conditions": objective["escalation_conditions"],
                "secondary_objectives": objective["secondary_objectives"],
            }
        )
    return normalized_tasks


def _internal_cognitive_tasks_payload(
    raw: dict[str, Any],
    *,
    q2_cognitive_plugins: list[str] | None = None,
    q2_functional_plugins: list[str] | None = None,
) -> dict[str, Any] | None:
    objective = _objective_profile_from_raw(raw)
    if objective is not None:
        internal_tasks = _objective_profile_to_internal_tasks(raw) or []
        task_rows: list[dict[str, Any]] = []
        for index, item in enumerate(internal_tasks):
            name = item["intent_name"]
            required_capability = item["required_capability"]
            task_rows.append(
                {
                    "task_id": f"q8-internal-objective-{_stable_fragment(name, str(index))}",
                    "title": name,
                    "reason": item["creation_rationale"],
                    "description": item["intent_description"],
                    "goal": item["intent_objective"],
                    "status": "next",
                    "task_scope": "internal",
                    "executor_type": "internal",
                    "target_id": "q8:internal_objective_profile",
                    "required_capabilities": [required_capability],
                    "metadata": {
                        "source_chain": "internal_q8",
                        "q8_dual_prompt_schema": "Q8_Internal.ObjectiveProfile",
                        "internal_cognitive_task": item,
                        "intent_name": name,
                        "intent_description": item["intent_description"],
                        "intent_objective": item["intent_objective"],
                        "creation_rationale": item["creation_rationale"],
                        "mission_rationale": item["mission_rationale"],
                        "basis_and_traceability": objective["basis_and_traceability"],
                        "task_precautions": item["task_precautions"],
                        "task_prohibitions": item["task_prohibitions"],
                        "question_driver_refs": item["question_driver_refs"],
                        "completion_conditions": item["completion_conditions"],
                        "escalation_conditions": item["escalation_conditions"],
                        "secondary_objectives": item["secondary_objectives"],
                        "task_name": name,
                        "task_description": item["intent_description"],
                        "task_goal": item["intent_objective"],
                        "task_creation_reason_and_basis": item["creation_rationale"],
                        "required_capability": required_capability,
                        "risk_level": item["risk_level"],
                        "target_engine_or_organ": item["target_engine_or_organ"],
                        "security_attributes": item["security_attributes"],
                        "initial_state": item["initial_state"],
                        "q8_output_policy": "objective_profile_to_internal_task_projection",
                        "target_id": "q8:internal_objective_profile",
                        "required_capabilities": [required_capability],
                    },
                }
            )

        return {
            "objective_profile": {
                "current_mission": objective["current_mission"],
                "mission_rationale": objective["mission_rationale"],
                "basis_and_traceability": objective["basis_and_traceability"],
                "primary_objectives": objective["primary_objectives"],
                "secondary_objectives": objective["secondary_objectives"],
                "completion_conditions": objective["completion_conditions"],
                "pause_conditions": objective["pause_conditions"],
                "escalation_conditions": objective["escalation_conditions"],
                "question_driver_refs": objective["question_driver_refs"],
                "current_phase_tasks": objective["primary_objectives"],
                "priority_order": objective["primary_objectives"] or [objective["current_mission"]],
            },
            "task_queue": {
                "next_self_tasks": task_rows,
                "blocked_self_tasks": [],
                "proactive_actions": [],
            },
        }

    if "internal_cognitive_tasks" not in raw:
        return None
    internal_tasks = normalize_q8_internal_cognitive_tasks(
        raw,
        q2_cognitive_plugins=q2_cognitive_plugins,
        q2_functional_plugins=q2_functional_plugins,
    )
    task_rows: list[dict[str, Any]] = []
    objective_names: list[str] = []
    for index, item in enumerate(internal_tasks):
        name = item["intent_name"]
        objective_names.append(name)
        required_capability = item["required_capability"]
        task_rows.append(
            {
                "task_id": f"q8-internal-cognitive-{_stable_fragment(name, str(index))}",
                "title": name,
                "reason": item["creation_rationale"],
                "description": item["intent_description"],
                "goal": item["intent_objective"],
                "status": "next",
                "task_scope": "internal",
                "executor_type": "internal",
                "target_id": "q8:internal_abstract_intent",
                "required_capabilities": [required_capability],
                "metadata": {
                    "source_chain": "internal_q8",
                    "q8_dual_prompt_schema": "Q8_Internal.PureCognitiveActionIntent",
                    "internal_cognitive_task": item,
                    "intent_name": name,
                    "intent_description": item["intent_description"],
                    "intent_objective": item["intent_objective"],
                    "creation_rationale": item["creation_rationale"],
                    "task_precautions": item["task_precautions"],
                    "task_prohibitions": item["task_prohibitions"],
                    "task_name": name,
                    "task_description": item["intent_description"],
                    "task_goal": item["intent_objective"],
                    "task_creation_reason_and_basis": item["creation_rationale"],
                    "required_capability": required_capability,
                    "risk_level": item["risk_level"],
                    "target_engine_or_organ": item["target_engine_or_organ"],
                    "security_attributes": item["security_attributes"],
                    "initial_state": item["initial_state"],
                    "q8_output_policy": "abstract_intent_only_no_task_center_sync",
                    "target_id": "q8:internal_abstract_intent",
                    "required_capabilities": [required_capability],
                },
            }
        )

    current_mission = objective_names[0] if objective_names else "Q8 internal cognitive agenda"
    return {
        "objective_profile": {
            "current_mission": current_mission,
            "primary_objectives": objective_names,
            "secondary_objectives": [],
            "completion_conditions": [
                "Every internal cognitive intent stays read_only=True and side_effect_free=True; Q8 only stores abstract intent."
            ],
            "pause_conditions": ["No valid Q2 cognitive capability was available for internal task generation"] if "internal_cognitive_tasks" in raw and not internal_tasks else [],
            "escalation_conditions": [],
            "current_phase_tasks": objective_names,
            "priority_order": objective_names or [current_mission],
        },
        "task_queue": {
            "next_self_tasks": task_rows,
            "blocked_self_tasks": [],
            "proactive_actions": [],
        },
    }


def _internal_objectives_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    objectives = raw.get("internal_objectives")
    if not isinstance(objectives, list):
        return None

    task_rows: list[dict[str, Any]] = []
    objective_names: list[str] = []
    pause_conditions = coerce_string_list(raw.get("pause_conditions"))
    priority_sorting = normalize_text(raw.get("priority_sorting"))
    refs = coerce_string_list(raw.get("question_driver_refs"))
    for index, item in enumerate(objectives):
        if not isinstance(item, dict):
            continue
        name = normalize_text(item.get("objective_name"))
        if not name:
            continue
        tools = coerce_string_list(item.get("cognitive_tools_required"))
        justification = normalize_text(item.get("justification"))
        objective_names.append(name)
        first_tool = normalize_text(tools[0] if tools else "task_constraint_checker")
        plugin_id = first_tool.removeprefix("internal:").removeprefix("cognitive.")
        task_rows.append(
            {
                "task_id": f"q8-internal-{_stable_fragment(name, str(index))}",
                "title": name,
                "reason": justification,
                "status": "next",
                "task_scope": "internal",
                "executor_type": "internal",
                "target_id": f"internal:{plugin_id or 'task_constraint_checker'}",
                "required_capabilities": tools or ["task.constraint_checking"],
                "metadata": {
                    "source_chain": "internal_q8",
                    "q8_dual_prompt_schema": "Q8_Internal",
                    "cognitive_tools_required": tools,
                    "question_driver_refs": refs,
                },
            }
        )

    current_mission = objective_names[0] if objective_names else "Q8 internal cognitive agenda"
    priority_order = coerce_string_list(priority_sorting) or objective_names
    return {
        "objective_profile": {
            "current_mission": current_mission,
            "primary_objectives": objective_names,
            "secondary_objectives": [],
            "completion_conditions": [
                "Internal cognitive agenda items remain read_only=True and side_effect_free=True."
            ],
            "pause_conditions": pause_conditions,
            "escalation_conditions": [],
            "current_phase_tasks": objective_names,
            "priority_order": priority_order or [current_mission],
        },
        "task_queue": {
            "next_self_tasks": task_rows,
            "blocked_self_tasks": [],
            "proactive_actions": [],
        },
    }


def _external_executor_from_tools(tools: list[str]) -> tuple[str, str, dict[str, Any], list[str]]:
    for tool in tools:
        normalized = normalize_text(tool)
        lowered = normalized.lower()
        if lowered.startswith("cli:"):
            tool_name = normalized.split(":", 1)[1].strip()
            if not tool_name:
                continue
            return "cli", f"cli:{tool_name}", {"cli_tool_name": tool_name}, ["external.cli", f"cli.{tool_name}"]
        if lowered.startswith("mcp:"):
            parts = normalized.split(":", 2)
            server_id = parts[1].strip() if len(parts) >= 2 else ""
            tool_name = parts[2].strip() if len(parts) == 3 else ""
            if not server_id or not tool_name:
                continue
            return (
                "mcp",
                normalized,
                {"mcp_server_id": server_id, "mcp_tool_name": tool_name},
                ["external.mcp", f"mcp.{server_id}.{tool_name}"],
            )
        if lowered.startswith("external_connector:"):
            connector_id = normalized.split(":", 1)[1].strip()
            if not connector_id:
                continue
            return (
                "external_connector",
                f"external_connector:{connector_id}",
                {"external_connector_id": connector_id},
                ["external.external_connector", f"external_connector.{connector_id}"],
            )
        if lowered.startswith("agent:"):
            agent_id = normalized.split(":", 1)[1].strip()
            if not agent_id:
                continue
            return "agent", f"agent:{agent_id}", {"agent_id": agent_id}, ["external.agent", f"agent.{agent_id}"]
    return "", "", {}, []


_ACTION_INTENT_KEYS = {
    "intent_name",
    "intent_description",
    "intent_objective",
    "creation_rationale",
    "task_precautions",
    "task_prohibitions",
    "required_capability",
    "target_execution_domain",
    "risk_level",
    "security_routing",
    "initial_state",
}
_RISK_LEVELS = {"low", "medium", "high", "critical"}
_EXTERNAL_EXECUTION_DOMAINS = {"Workspace", "HostSystem", "ExternalNetwork", "ExternalAgent"}
_SIDE_EFFECT_MARKERS = (
    "write",
    "delete",
    "remove",
    "reset",
    "push",
    "post",
    "put",
    "patch",
    "http",
    "request",
    "network",
    "修改",
    "写入",
    "删除",
    "重置",
    "提交",
    "推送",
    "外发",
    "网络请求",
)


def _json_text(value: object) -> str:
    try:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _redline_texts(q7_redlines: dict[str, Any] | None) -> list[str]:
    payload = q7_redlines if isinstance(q7_redlines, dict) else {}
    texts: list[str] = []
    for key in (
        "absolute_red_lines",
        "prohibited_strategies",
        "current_red_line_hits",
        "rejected_operation_records",
        "non_bypassable_constraints",
    ):
        texts.extend(coerce_string_list(payload.get(key)))
    return [item.lower() for item in texts if item.strip()]


def normalize_q8_external_execution_tasks(
    raw: object,
    *,
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    tasks = raw.get("external_execution_tasks")
    if not isinstance(tasks, list):
        return []

    functional_capabilities = [
        normalize_text(item)
        for item in (q2_functional_plugins or [])
        if normalize_text(item)
    ]
    cognitive_refs = {normalize_text(item) for item in (q2_cognitive_plugins or []) if normalize_text(item)}
    capability_payload = q4_external_capabilities if isinstance(q4_external_capabilities, dict) else {}

    redlines = _redline_texts(q7_redlines)
    normalized_tasks: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        if set(item.keys()) != _ACTION_INTENT_KEYS:
            continue

        intent_name = normalize_text(item.get("intent_name"))
        intent_description = normalize_text(item.get("intent_description"))
        intent_objective = normalize_text(item.get("intent_objective"))
        creation_rationale = normalize_text(item.get("creation_rationale"))
        task_precautions = coerce_string_list(item.get("task_precautions"))
        task_prohibitions = coerce_string_list(item.get("task_prohibitions"))
        required_capability = normalize_text(item.get("required_capability"))
        required_capability_lower = required_capability.lower()
        if not intent_name or not intent_description or not intent_objective or not creation_rationale or not required_capability:
            continue
        if not isinstance(item.get("task_precautions"), list) or not isinstance(item.get("task_prohibitions"), list):
            continue
        if required_capability in cognitive_refs:
            continue
        if any(marker in required_capability_lower for marker in _CONCRETE_PLUGIN_MARKERS):
            continue

        target_execution_domain = normalize_text(item.get("target_execution_domain"))
        if target_execution_domain not in _EXTERNAL_EXECUTION_DOMAINS:
            continue

        intent_text = (
            f"{intent_name} {intent_description} {intent_objective} "
            f"{creation_rationale} {' '.join(task_precautions)} {required_capability} {target_execution_domain}"
        ).lower()
        if any(redline and redline in intent_text for redline in redlines):
            continue

        risk_level = normalize_text(item.get("risk_level")).lower()
        if risk_level not in _RISK_LEVELS:
            continue
        if risk_level in {"low", "medium"} and any(marker in intent_text for marker in _SIDE_EFFECT_MARKERS):
            risk_level = "high"

        security_routing = item.get("security_routing")
        if not isinstance(security_routing, dict):
            continue
        safety_gate_required = bool(security_routing.get("safety_gate_required"))
        if not safety_gate_required:
            continue
        audit_required = bool(security_routing.get("audit_required"))
        if risk_level in {"high", "critical"}:
            audit_required = True

        initial_state = normalize_text(item.get("initial_state")).lower()
        if initial_state != "queued_for_orchestration":
            continue

        normalized_tasks.append(
            {
                "intent_name": intent_name,
                "intent_description": intent_description,
                "intent_objective": intent_objective,
                "creation_rationale": creation_rationale,
                "task_precautions": task_precautions,
                "task_prohibitions": task_prohibitions,
                "required_capability": required_capability,
                "target_execution_domain": target_execution_domain,
                "risk_level": risk_level,
                "security_routing": {
                    "safety_gate_required": True,
                    "audit_required": audit_required,
                },
                "initial_state": initial_state,
            }
        )
    return normalized_tasks


def _external_execution_tasks_payload(
    raw: dict[str, Any],
    *,
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if "external_execution_tasks" not in raw:
        return None
    action_intents = normalize_q8_external_execution_tasks(
        raw,
        q2_functional_plugins=q2_functional_plugins,
        q2_cognitive_plugins=q2_cognitive_plugins,
        q4_external_capabilities=q4_external_capabilities,
        q7_redlines=q7_redlines,
    )
    next_tasks: list[dict[str, Any]] = []
    blocked_tasks: list[dict[str, Any]] = []
    objective_names: list[str] = []
    for index, item in enumerate(action_intents):
        name = item["intent_name"]
        objective_names.append(name)
        required_capability = item["required_capability"]
        target_execution_domain = item["target_execution_domain"]
        task_row = {
            "task_id": f"q8-actionintent-{_stable_fragment(name, str(index))}",
            "title": name,
            "reason": item["creation_rationale"],
            "description": item["intent_description"],
            "goal": item["intent_objective"],
            "status": "next",
            "task_scope": "external",
            "executor_type": "external_connector",
            "target_id": "q8:external_abstract_intent",
            "required_capabilities": [required_capability],
            "risk_assessment": {
                "risk_level": item["risk_level"],
                "security_routing": item["security_routing"],
                "target_execution_domain": target_execution_domain,
            },
            "metadata": {
                "source_chain": "external_q8",
                "q8_dual_prompt_schema": "Q8_External.PureActionIntent",
                "action_intent": {
                    "action_type": name,
                    "intent_description": item["intent_description"],
                    "intent_objective": item["intent_objective"],
                    "creation_rationale": item["creation_rationale"],
                    "task_precautions": item["task_precautions"],
                    "task_prohibitions": item["task_prohibitions"],
                    "required_capability": required_capability,
                    "target_execution_domain": target_execution_domain,
                    "requester_id": "q8",
                },
                "intent_name": name,
                "intent_description": item["intent_description"],
                "intent_objective": item["intent_objective"],
                "creation_rationale": item["creation_rationale"],
                "task_precautions": item["task_precautions"],
                "task_prohibitions": item["task_prohibitions"],
                "task_name": name,
                "task_description": item["intent_description"],
                "task_goal": item["intent_objective"],
                "task_creation_reason_and_basis": item["creation_rationale"],
                "required_capability": required_capability,
                "target_execution_domain": target_execution_domain,
                "risk_level": item["risk_level"],
                "security_routing": item["security_routing"],
                "initial_state": item["initial_state"],
                "q8_output_policy": "abstract_intent_only_no_task_center_sync",
                "target_id": "q8:external_abstract_intent",
                "required_capabilities": [required_capability],
            },
        }
        next_tasks.append(task_row)

    current_mission = objective_names[0] if objective_names else "Q8 external ActionIntent queue"
    return {
        "objective_profile": {
            "current_mission": current_mission,
            "primary_objectives": objective_names,
            "secondary_objectives": [],
            "completion_conditions": [
                "Every external ActionIntent remains abstract in Q8; Q8 only stores abstract intent."
            ],
            "pause_conditions": ["External execution permission or redline gate blocks ActionIntent generation"] if not action_intents else [],
            "escalation_conditions": [
                "Any ActionIntent without safety gate approval must remain blocked.",
                "Any high or critical ActionIntent without audit approval must remain blocked.",
            ],
            "current_phase_tasks": objective_names,
            "priority_order": objective_names or [current_mission],
        },
        "task_queue": {
            "next_self_tasks": next_tasks,
            "blocked_self_tasks": blocked_tasks,
            "proactive_actions": [],
        },
    }


def _objective_profile_to_external_tasks(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
    objective = _objective_profile_from_raw(raw)
    if objective is None:
        return None

    basis = objective.get("basis_and_traceability") if isinstance(objective.get("basis_and_traceability"), dict) else {}
    q2_support = basis.get("q2_asset_support_bases") if isinstance(basis, dict) else []
    if not q2_support:
        return []

    normalized_tasks: list[dict[str, Any]] = []
    for objective_text in objective["primary_objectives"]:
        objective_lower = objective_text.lower()
        if any(marker in objective_lower for marker in _CONCRETE_PLUGIN_MARKERS):
            continue
        normalized_tasks.append(
            {
                "intent_name": objective_text,
                "intent_description": objective_text,
                "intent_objective": objective_text,
                "creation_rationale": objective["mission_rationale"],
                "task_precautions": objective["pause_conditions"],
                "task_prohibitions": objective["escalation_conditions"],
                "required_capability": "abstract_external_orchestration",
                "target_execution_domain": "Workspace",
                "risk_level": "medium",
                "security_routing": {
                    "safety_gate_required": True,
                    "audit_required": False,
                },
                "initial_state": "queued_for_orchestration",
                "basis_and_traceability": basis,
                "completion_conditions": objective["completion_conditions"],
                "secondary_objectives": objective["secondary_objectives"],
            }
        )
    return normalized_tasks


def _external_objective_profile_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    objective = _objective_profile_from_raw(raw)
    if objective is None:
        return None
    action_intents = _objective_profile_to_external_tasks(raw) or []
    basis = objective.get("basis_and_traceability") if isinstance(objective.get("basis_and_traceability"), dict) else {}
    has_q2_support = bool(basis.get("q2_asset_support_bases") if isinstance(basis, dict) else [])

    next_tasks: list[dict[str, Any]] = []
    proactive_actions: list[dict[str, Any]] = []
    for index, item in enumerate(action_intents):
        name = item["intent_name"]
        task_row = {
            "task_id": f"q8-external-objective-{_stable_fragment(name, str(index))}",
            "title": name,
            "reason": item["creation_rationale"],
            "description": item["intent_description"],
            "goal": item["intent_objective"],
            "status": "next",
            "task_scope": "external",
            "executor_type": "external_connector",
            "target_id": "q8:external_objective_profile",
            "required_capabilities": [item["required_capability"]],
            "risk_assessment": {
                "risk_level": item["risk_level"],
                "security_routing": item["security_routing"],
                "target_execution_domain": item["target_execution_domain"],
            },
            "metadata": {
                "source_chain": "external_q8",
                "q8_dual_prompt_schema": "Q8_External.ObjectiveProfile",
                "basis_and_traceability": item["basis_and_traceability"],
                "intent_name": name,
                "intent_description": item["intent_description"],
                "intent_objective": item["intent_objective"],
                "creation_rationale": item["creation_rationale"],
                "task_precautions": item["task_precautions"],
                "task_prohibitions": item["task_prohibitions"],
                "completion_conditions": item["completion_conditions"],
                "secondary_objectives": item["secondary_objectives"],
                "required_capability": item["required_capability"],
                "target_execution_domain": item["target_execution_domain"],
                "risk_level": item["risk_level"],
                "security_routing": item["security_routing"],
                "initial_state": item["initial_state"],
                "q8_output_policy": "objective_profile_abstract_intent_only_no_tool_binding",
                "target_id": "q8:external_objective_profile",
                "required_capabilities": [item["required_capability"]],
            },
        }
        next_tasks.append(task_row)

    if not has_q2_support:
        for index, objective_text in enumerate(objective["primary_objectives"]):
            proactive_actions.append(
                {
                    "task_id": f"q8-external-downgraded-internal-{_stable_fragment(objective_text, str(index))}",
                    "title": objective_text,
                    "reason": "Q2 asset support bases are empty; external objective downgraded to internal cognitive probe.",
                    "status": "proactive",
                    "task_scope": "internal",
                    "executor_type": "internal",
                    "target_id": "q8:external_objective_profile_downgrade",
                    "required_capabilities": ["strategic_alignment_reasoning"],
                    "metadata": {
                        "source_chain": "external_q8",
                        "q8_dual_prompt_schema": "Q8_External.ObjectiveProfile.downgraded_to_internal",
                        "basis_and_traceability": basis,
                        "q8_output_policy": "q2_missing_asset_support_forces_internal_downgrade",
                    },
                }
            )

    return {
        "objective_profile": {
            "current_mission": objective["current_mission"],
            "mission_rationale": objective["mission_rationale"],
            "basis_and_traceability": basis,
            "primary_objectives": objective["primary_objectives"],
            "secondary_objectives": objective["secondary_objectives"],
            "completion_conditions": objective["completion_conditions"],
            "pause_conditions": objective["pause_conditions"],
            "escalation_conditions": objective["escalation_conditions"],
            "current_phase_tasks": objective["primary_objectives"],
            "priority_order": objective["primary_objectives"] or [objective["current_mission"]],
        },
        "task_queue": {
            "next_self_tasks": next_tasks,
            "blocked_self_tasks": [],
            "proactive_actions": proactive_actions,
        },
    }


def _external_objectives_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    objectives = raw.get("external_objectives")
    degraded = raw.get("degraded_to_internal_tasks")
    if not isinstance(objectives, list) and not isinstance(degraded, list):
        return None

    refs = coerce_string_list(raw.get("question_driver_refs"))
    escalation_conditions = coerce_string_list(raw.get("escalation_conditions"))
    next_tasks: list[dict[str, Any]] = []
    blocked_tasks: list[dict[str, Any]] = []
    objective_names: list[str] = []
    for index, item in enumerate(objectives if isinstance(objectives, list) else []):
        if not isinstance(item, dict):
            continue
        name = normalize_text(item.get("objective_name"))
        if not name:
            continue
        tools = coerce_string_list(item.get("functional_tools_required"))
        risk_level = normalize_text(item.get("risk_level")).lower() or "medium"
        objective_names.append(name)
        executor_type, target_id, executor_metadata, capabilities = _external_executor_from_tools(tools)
        if not executor_type or not target_id:
            blocked_tasks.append(
                {
                    "task_id": f"q8-external-blocked-{_stable_fragment(name, str(index))}",
                    "title": name,
                    "reason": "missing_concrete_external_executor",
                    "status": "blocked",
                    "metadata": {
                        "source_chain": "external_q8",
                        "q8_dual_prompt_schema": "Q8_External",
                        "functional_tools_required": tools,
                        "blocked_by": "missing_concrete_external_executor",
                        "question_driver_refs": refs,
                    },
                }
            )
            continue
        next_tasks.append(
            {
                "task_id": f"q8-external-{_stable_fragment(name, str(index))}",
                "title": name,
                "reason": f"Q8 external objective risk_level={risk_level}",
                "status": "next",
                "task_scope": "external",
                "executor_type": executor_type,
                "target_id": target_id,
                "required_capabilities": list(dict.fromkeys(capabilities + tools)),
                "risk_assessment": {"risk_level": risk_level},
                "metadata": {
                    "source_chain": "external_q8",
                    "q8_dual_prompt_schema": "Q8_External",
                    "functional_tools_required": tools,
                    "risk_level": risk_level,
                    "target_id": target_id,
                    "required_capabilities": list(dict.fromkeys(capabilities + tools)),
                    "question_driver_refs": refs,
                    **executor_metadata,
                },
            }
        )

    proactive_actions: list[dict[str, Any]] = []
    for index, item in enumerate(degraded if isinstance(degraded, list) else []):
        if not isinstance(item, dict):
            continue
        original_intent = normalize_text(item.get("original_intent"))
        degraded_action = normalize_text(item.get("degraded_action"))
        if not degraded_action and not original_intent:
            continue
        title = degraded_action or f"Prepare internal downgrade for: {original_intent}"
        proactive_actions.append(
            {
                "task_id": f"q8-degraded-internal-{_stable_fragment(title, str(index))}",
                "title": title,
                "reason": normalize_text(item.get("blocked_by")),
                "status": "proactive",
                "task_scope": "internal",
                "executor_type": "internal",
                "metadata": {
                    "source_chain": "internal_q8",
                    "q8_dual_prompt_schema": "Q8_External.degraded_to_internal_tasks",
                    "original_intent": original_intent,
                    "blocked_by": normalize_text(item.get("blocked_by")),
                    "question_driver_refs": refs,
                },
            }
        )

    current_mission = objective_names[0] if objective_names else "Q8 external action intent"
    return {
        "objective_profile": {
            "current_mission": current_mission,
            "primary_objectives": objective_names,
            "secondary_objectives": [item["title"] for item in proactive_actions],
            "completion_conditions": [
                "External action intents pass SafetyGate and cloud audit before side effects."
            ],
            "pause_conditions": [item.get("reason", "") for item in blocked_tasks if item.get("reason")],
            "escalation_conditions": escalation_conditions,
            "current_phase_tasks": objective_names + [item["title"] for item in proactive_actions],
            "priority_order": objective_names + [item["title"] for item in proactive_actions] or [current_mission],
        },
        "task_queue": {
            "next_self_tasks": next_tasks,
            "blocked_self_tasks": blocked_tasks,
            "proactive_actions": proactive_actions,
        },
    }


def normalize_q8_inference_payload(
    raw: object,
    *,
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    request_scope: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    if request_scope == "external":
        external_objective_payload = _external_objective_profile_payload(raw)
        if external_objective_payload is not None:
            return external_objective_payload

    if request_scope == "internal":
        internal_objective_payload = _internal_cognitive_tasks_payload(
            raw,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q2_functional_plugins=q2_functional_plugins,
        )
        if internal_objective_payload is not None:
            return internal_objective_payload

    if "internal_cognitive_tasks" in raw and "external_execution_tasks" in raw:
        internal_cognitive_payload = _internal_cognitive_tasks_payload(
            raw,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q2_functional_plugins=q2_functional_plugins,
        )
        action_intent_payload = _external_execution_tasks_payload(
            raw,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q4_external_capabilities=q4_external_capabilities,
            q7_redlines=q7_redlines,
        )
        internal_cognitive_payload = internal_cognitive_payload or {
            "objective_profile": {
                "current_mission": "Q8 internal cognitive agenda",
                "primary_objectives": [],
                "secondary_objectives": [],
                "completion_conditions": [],
                "pause_conditions": [],
                "escalation_conditions": [],
                "current_phase_tasks": [],
                "priority_order": ["Q8 internal cognitive agenda"],
            },
            "task_queue": {"next_self_tasks": [], "blocked_self_tasks": [], "proactive_actions": []},
        }
        action_intent_payload = action_intent_payload or {
            "objective_profile": {
                "current_mission": "Q8 external ActionIntent queue",
                "primary_objectives": [],
                "secondary_objectives": [],
                "completion_conditions": [],
                "pause_conditions": [],
                "escalation_conditions": [],
                "current_phase_tasks": [],
                "priority_order": ["Q8 external ActionIntent queue"],
            },
            "task_queue": {"next_self_tasks": [], "blocked_self_tasks": [], "proactive_actions": []},
        }
        internal_objective = internal_cognitive_payload["objective_profile"]
        external_objective = action_intent_payload["objective_profile"]
        internal_queue = internal_cognitive_payload["task_queue"]
        external_queue = action_intent_payload["task_queue"]
        current_mission = normalize_text(internal_objective.get("current_mission")) or normalize_text(external_objective.get("current_mission"))
        external_mission = normalize_text(external_objective.get("current_mission"))
        if external_mission and external_mission != current_mission:
            current_mission = f"{current_mission}；{external_mission}" if current_mission else external_mission
        return {
            "objective_profile": {
                "current_mission": current_mission or "Q8 abstract internal and external intent generation",
                "mission_rationale": normalize_text(internal_objective.get("mission_rationale"))
                or normalize_text(external_objective.get("mission_rationale")),
                "primary_objectives": merge_string_lists(
                    coerce_string_list(internal_objective.get("primary_objectives")),
                    coerce_string_list(external_objective.get("primary_objectives")),
                ),
                "secondary_objectives": merge_string_lists(
                    coerce_string_list(internal_objective.get("secondary_objectives")),
                    coerce_string_list(external_objective.get("secondary_objectives")),
                ),
                "completion_conditions": merge_string_lists(
                    coerce_string_list(internal_objective.get("completion_conditions")),
                    coerce_string_list(external_objective.get("completion_conditions")),
                ),
                "pause_conditions": merge_string_lists(
                    coerce_string_list(internal_objective.get("pause_conditions")),
                    coerce_string_list(external_objective.get("pause_conditions")),
                ),
                "escalation_conditions": merge_string_lists(
                    coerce_string_list(internal_objective.get("escalation_conditions")),
                    coerce_string_list(external_objective.get("escalation_conditions")),
                ),
                "current_phase_tasks": merge_string_lists(
                    coerce_string_list(internal_objective.get("current_phase_tasks")),
                    coerce_string_list(external_objective.get("current_phase_tasks")),
                ),
                "priority_order": merge_string_lists(
                    coerce_string_list(internal_objective.get("priority_order")),
                    coerce_string_list(external_objective.get("priority_order")),
                ) or [current_mission or "Q8 abstract internal and external intent generation"],
            },
            "task_queue": {
                "next_self_tasks": list(internal_queue.get("next_self_tasks") or []) + list(external_queue.get("next_self_tasks") or []),
                "blocked_self_tasks": list(internal_queue.get("blocked_self_tasks") or []) + list(external_queue.get("blocked_self_tasks") or []),
                "proactive_actions": list(internal_queue.get("proactive_actions") or []) + list(external_queue.get("proactive_actions") or []),
            },
        }

    internal_cognitive_payload = _internal_cognitive_tasks_payload(
        raw,
        q2_cognitive_plugins=q2_cognitive_plugins,
        q2_functional_plugins=q2_functional_plugins,
    )
    if internal_cognitive_payload is not None:
        return internal_cognitive_payload

    external_objective_payload = _external_objective_profile_payload(raw)
    if external_objective_payload is not None:
        return external_objective_payload

    action_intent_payload = _external_execution_tasks_payload(
        raw,
        q2_functional_plugins=q2_functional_plugins,
        q2_cognitive_plugins=q2_cognitive_plugins,
        q4_external_capabilities=q4_external_capabilities,
        q7_redlines=q7_redlines,
    )
    if action_intent_payload is not None:
        return action_intent_payload

    internal_payload = _internal_objectives_payload(raw)
    if internal_payload is not None:
        return internal_payload
    external_payload = _external_objectives_payload(raw)
    if external_payload is not None:
        return external_payload

    objective_raw = raw.get("objective_profile")
    objective_input = objective_raw if isinstance(objective_raw, dict) else {}
    current_mission = normalize_text(
        objective_input.get("current_mission") or objective_input.get("main_objective")
    )
    derived_capabilities = coerce_string_list(objective_input.get("derived_capabilities"))
    rationale = normalize_text(objective_input.get("rationale"))
    mission_rationale = normalize_text(objective_input.get("mission_rationale"))

    current_phase_tasks = coerce_string_list(objective_input.get("current_phase_tasks"))
    if not current_phase_tasks:
        current_phase_tasks = derived_capabilities

    priority_order = coerce_string_list(objective_input.get("priority_order"))
    if not priority_order:
        priority_order = current_phase_tasks or ([current_mission] if current_mission else [])

    primary_objectives = coerce_string_list(objective_input.get("primary_objectives"))
    if not primary_objectives and current_mission:
        primary_objectives = [current_mission]

    secondary_objectives = coerce_string_list(objective_input.get("secondary_objectives"))
    completion_conditions = coerce_string_list(objective_input.get("completion_conditions"))
    if not completion_conditions and rationale:
        completion_conditions = [rationale]

    objective_profile = {
        "current_mission": current_mission,
        "mission_rationale": mission_rationale,
        "primary_objectives": primary_objectives,
        "secondary_objectives": secondary_objectives,
        "completion_conditions": completion_conditions,
        "pause_conditions": coerce_string_list(objective_input.get("pause_conditions")),
        "escalation_conditions": coerce_string_list(objective_input.get("escalation_conditions")),
        "current_phase_tasks": current_phase_tasks,
        "priority_order": priority_order,
    }

    queue_raw = raw.get("task_queue")
    queue_input = queue_raw if isinstance(queue_raw, dict) else {}
    next_self_tasks: list[dict[str, Any]] = []
    blocked_self_tasks: list[dict[str, Any]] = []
    proactive_actions: list[dict[str, Any]] = []

    if isinstance(queue_raw, list):
        for index, item in enumerate(queue_raw):
            item_status = "proactive"
            if isinstance(item, dict):
                status_text = normalize_text(item.get("status")).lower()
                if status_text in {"next", "next_self_tasks", "todo", "ready"}:
                    item_status = "next"
                elif status_text in {"blocked", "blocked_self_tasks", "waiting", "paused"}:
                    item_status = "blocked"
            normalized = _normalize_queue_entry(item, index=index, status=item_status)
            if normalized is None:
                continue
            if item_status == "next":
                next_self_tasks.append(normalized)
            elif item_status == "blocked":
                blocked_self_tasks.append(normalized)
            else:
                proactive_actions.append(normalized)
    else:
        for index, item in enumerate(_queue_entries(queue_input.get("next_self_tasks"))):
            normalized = _normalize_queue_entry(item, index=index, status="next")
            if normalized is not None:
                next_self_tasks.append(normalized)
        for index, item in enumerate(_queue_entries(queue_input.get("blocked_self_tasks"))):
            normalized = _normalize_queue_entry(item, index=index, status="blocked")
            if normalized is not None:
                blocked_self_tasks.append(normalized)
        for index, item in enumerate(_queue_entries(queue_input.get("proactive_actions"))):
            normalized = _normalize_queue_entry(item, index=index, status="proactive")
            if normalized is not None:
                proactive_actions.append(normalized)

    return {
        "objective_profile": objective_profile,
        "task_queue": {
            "next_self_tasks": next_self_tasks,
            "blocked_self_tasks": blocked_self_tasks,
            "proactive_actions": proactive_actions,
        },
    }
