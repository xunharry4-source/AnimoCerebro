from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)

_TASK_STATE_ALLOWED_KEYS = {
    "task_id",
    "id",
    "title",
    "description",
    "status",
    "priority",
    "remarks",
    "reason",
    "queue_name",
}

_REQUIRED_Q8_UPSTREAMS = {"q4", "q5", "q6"}
_FORBIDDEN_RAW_KEYS = {
    "raw_output",
    "reasoning_trace",
    "chain_of_thought",
    "internal_reasoning",
    "debug",
    "debug_trace",
    "token_count",
    "latency",
    "latency_ms",
    "prompt",
    "completion",
}

_Q8_FIELD_INTENT_MAP: dict[str, Any] = {
    "q1": {
        "status": ("text", 80),
        "environment_summary": ("text", 300),
        "primary_domain": ("text", 160),
        "secondary_domains": ("list", 4, 120),
        "suggested_first_step": ("text", 220),
    },
    "q2": {
        "status": ("text", 80),
        "role_profile": {
            "identity_role": ("text", 160),
            "active_role": ("text", 160),
            "task_role": ("text", 160),
        },
        "mission": {
            "current_mission": ("text", 320),
            "priority_duties": ("list", 5, 160),
            "continuity_boundaries": ("list", 5, 180),
        },
        "non_bypassable_constraints": ("list", 4, 180),
        "audit_rules": ("list", 4, 160),
    },
    "q3": {
        "status": ("text", 80),
        "resource_status": ("text", 180),
        "bottleneck_node": ("text", 180),
        "missing_critical_assets": ("list", 6, 180),
        "available_cognitive_tools": ("list", 6, 140),
        "available_execution_tools": ("list", 6, 140),
        "functional_plugins": ("list", 12, 180),
        "cognitive_plugins": ("list", 12, 180),
        "accessible_workspace_zones": ("list", 6, 140),
    },
    "q4": {
        "status": ("text", 80),
        "actionable_space": ("list", 8, 180),
        "executable_strategies": ("list", 8, 180),
        "capability_upper_limits": ("list", 8, 180),
        "permission_profile": {
            "mode": ("text", 80),
            "is_read_only": ("bool",),
            "tenant_permissions": ("list", 6, 140),
            "execution_tokens": ("list", 6, 140),
            "accessible_workspace_zones": ("list", 6, 140),
        },
    },
    "q5": {
        "status": ("text", 80),
        "current_authorization_scope": ("text", 180),
        "contact_policies": ("list", 6, 180),
        "organizational_boundaries": ("text", 180),
        "allowed_action_space": ("list", 8, 180),
        "forbidden_action_space": ("list", 8, 180),
        "requires_escalation_actions": ("list", 6, 180),
        "authorized_actions": ("list", 8, 160),
        "unauthorized_actions": ("list", 8, 180),
        "conditional_actions": ("list", 8, 180),
        "objective_scope": ("text", 80),
        "collaboration_available": ("bool",),
        "authorization_limited": ("bool",),
    },
    "q6": {
        "status": ("text", 80),
        "absolute_red_lines": ("list", 10, 200),
        "performance_tradeoff_bans": ("list", 8, 180),
        "prohibited_strategies": ("list", 8, 180),
        "contamination_risks": ("list", 8, 180),
        "audit_rules": ("list", 4, 160),
    },
    "q7": {
        "status": ("text", 80),
        "current_red_line_hits": ("list", 8, 220),
        "rejected_operation_records": ("list", 8, 220),
        "ban_source_explanations": ("list", 8, 220),
        "non_bypassable_constraints": ("list", 12, 220),
        "question_driver_refs": ("list", 8, 180),
    },
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _text(value: Any, *, path: str, report: dict[str, Any]) -> str:
    return str(value or "").strip()


def _list(value: Any, *, path: str, report: dict[str, Any]) -> list[str]:
    if not isinstance(value, list):
        if value not in (None, "", {}, []):
            report["type_mismatches"].append({"path": path, "expected": "list", "actual": type(value).__name__})
        return []
    normalized: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, path=f"{path}[{index}]", report=report)
        if text:
            normalized.append(text)
    return normalized


def _compact_by_spec(value: Any, spec: Any, *, path: str, report: dict[str, Any]) -> Any:
    if isinstance(spec, tuple):
        kind = spec[0]
        if kind == "text":
            return _text(value, path=path, report=report)
        if kind == "list":
            return _list(value, path=path, report=report)
        if kind == "bool":
            return bool(value)
        raise ValueError(f"Unsupported q8 prompt field spec kind: {kind}")

    if not isinstance(value, dict):
        if value not in (None, "", [], {}):
            report["type_mismatches"].append({"path": path, "expected": "dict", "actual": type(value).__name__})
        return {}

    compact: dict[str, Any] = {}
    allowed_keys = set(spec.keys())
    for raw_key in value:
        key = str(raw_key)
        if key in _FORBIDDEN_RAW_KEYS:
            report["dropped_raw_fields"].append(f"{path}.{key}")
        elif key not in allowed_keys:
            report["dropped_unmapped_fields"].append(f"{path}.{key}")

    for key, child_spec in spec.items():
        child = _compact_by_spec(value.get(key), child_spec, path=f"{path}.{key}", report=report)
        if child not in ("", [], {}, None):
            compact[key] = child
    return compact


def _enforce_total_snapshot_budget(snapshot: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return dict(snapshot)


def build_q8_prompt_snapshot(q1_q7_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the compact Q8 prompt snapshot using an explicit field-intent map."""
    report: dict[str, Any] = {
        "no_truncation_policy": "Q8 prompt preprocessing does not truncate or drop fields for token budgets.",
        "missing_required_questions": [],
        "dropped_raw_fields": [],
        "dropped_unmapped_fields": [],
        "type_mismatches": [],
    }
    raw = q1_q7_snapshot if isinstance(q1_q7_snapshot, dict) else {}
    compact: dict[str, Any] = {}
    for question_id, spec in _Q8_FIELD_INTENT_MAP.items():
        question_payload = raw.get(question_id)
        if question_id in _REQUIRED_Q8_UPSTREAMS and not isinstance(question_payload, dict):
            report["missing_required_questions"].append(question_id)
        normalized = _compact_by_spec(question_payload, spec, path=question_id, report=report)
        if normalized:
            compact[question_id] = normalized
    compact = _enforce_total_snapshot_budget(compact, report)
    report["context_chars"] = len(_json(compact))
    report["used_field_intent_map"] = True
    return compact, report


def _compact_task_state(persistent_task_state: Any, report: dict[str, Any]) -> Any:
    def _compact_task_item(item: Any, path: str) -> Any:
        if isinstance(item, dict):
            compact_item: dict[str, Any] = {}
            for key, value in item.items():
                key_text = str(key)
                if key_text in _FORBIDDEN_RAW_KEYS:
                    report["dropped_raw_fields"].append(f"{path}.{key_text}")
                    continue
                if key_text not in _TASK_STATE_ALLOWED_KEYS:
                    report["dropped_unmapped_fields"].append(f"{path}.{key_text}")
                    continue
                compact_item[key_text] = _text(
                    value,
                    path=f"{path}.{key_text}",
                    report=report,
                )
            return compact_item
        return _text(item, path=path, report=report)

    if isinstance(persistent_task_state, dict):
        compact: dict[str, Any] = {}
        for key, value in persistent_task_state.items():
            if isinstance(value, list):
                compact[str(key)] = [
                    _compact_task_item(item, f"task_state.{key}[{index}]")
                    for index, item in enumerate(value)
                ]
            else:
                compact[str(key)] = _compact_task_item(value, f"task_state.{key}")
        return compact
    if isinstance(persistent_task_state, list):
        return [
            _compact_task_item(item, f"task_state[{index}]")
            for index, item in enumerate(persistent_task_state)
        ]
    return []


def _compact_functional_objectives(functional_objectives: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for index, item in enumerate(functional_objectives):
        if not isinstance(item, dict):
            report["type_mismatches"].append(
                {"path": f"functional_objectives[{index}]", "expected": "dict", "actual": type(item).__name__}
            )
            continue
        cleaned: dict[str, Any] = {}
        for key in ("plugin_id", "objective", "priority", "result", "summary"):
            if key in item:
                cleaned[key] = _text(
                    item.get(key),
                    path=f"functional_objectives[{index}].{key}",
                    report=report,
                )
        if cleaned:
            compact.append(cleaned)
    return compact


def build_q8_llm_request(
    *,
    system_prompt: str,
    nine_questions_summary: str,
    task_state_summary: str,
    objective_catalog: str,
    priority_baseline: dict[str, Any],
    q1_q7_snapshot: dict[str, Any],
    nine_questions: dict[str, Any],
    persistent_task_state: Any,
    active_objectives: list[str],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    compact_snapshot, preprocessing_report = build_q8_prompt_snapshot(q1_q7_snapshot)
    compact_task_state = _compact_task_state(persistent_task_state, preprocessing_report)
    compact_functional_objectives = _compact_functional_objectives(functional_objectives, preprocessing_report)
    compact_active_objectives = [
        _text(item, path=f"active_objectives[{index}]", report=preprocessing_report)
        for index, item in enumerate(active_objectives)
    ]
    compact_objective_catalog = _text(
        objective_catalog,
        path="objective_catalog",
        report=preprocessing_report,
    )
    compact_priority_baseline = json.loads(_json(priority_baseline if isinstance(priority_baseline, dict) else {}))

    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the decision-synthesis task for Q8.",
            purpose="Focus the model on current objective selection and task queue generation.",
            content=system_prompt,
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="snapshot_q1_q7",
            title="Cognitive Snapshot Q1-Q7",
            intent="Provide the audited field-intent subset of upstream Q1-Q7 state.",
            purpose="Ground Q8 without leaking raw outputs, traces, or unrelated metadata.",
            content=_json(compact_snapshot),
        ),
        build_prompt_section(
            key="task_state",
            title="Task State Machine",
            intent="Provide current task lifecycle state.",
            purpose="Align prioritization with ongoing, blocked, and waiting work.",
            content=_json(compact_task_state),
        ),
        build_prompt_section(
            key="objective_catalog",
            title="Objective Strategy Plugins",
            intent="Provide plugin-sourced objective hints.",
            purpose="Leverage specialized objective proposals before synthesis.",
            content=compact_objective_catalog,
        ),
        build_prompt_section(
            key="priority_baseline",
            title="Q8 Priority Baseline",
            intent="Provide baseline prioritization signals.",
            purpose="Constrain decisions to the validated Q8 prioritization frame.",
            content=_json(compact_priority_baseline),
        ),
        build_prompt_section(
            key="q5_dynamic_convergence_guard",
            title="Q5 Dynamic Authorization Convergence Guard",
            intent="Force Q8 objectives to shrink when Q5 collaboration or authorization is limited.",
            purpose="Prevent high-permission or cross-brain objectives when Q5 forbids them.",
            content=(
                "如果 q1_q7_snapshot.q5.objective_scope 为 `single_brain_only`，"
                "或 q1_q7_snapshot.q5.collaboration_available 为 false，"
                "或 q1_q7_snapshot.q5.authorization_limited 为 true，"
                "则 Q8 的 objective_profile 与 task_queue 必须收缩为单脑可完成目标，"
                "不得生成跨脑委托、外部 Agent 求助或高权限执行任务。"
            ),
        ),
        build_prompt_section(
            key="preprocessing_report",
            title="Q8 Prompt Preprocessing Report",
            intent="Expose missing required upstreams and dropped raw/debug/unmapped fields.",
            purpose="Prevent hidden prompt-input loss while preserving all allowed LLM input without truncation.",
            content=_json(preprocessing_report),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required final response shape.",
            purpose="Prevent summary-only output and enforce objective/task JSON.",
            content=(
                "综合判断，输出严格 JSON。\n"
                "顶层只能包含：\n"
                "- `objective_profile`\n"
                "- `task_queue`\n\n"
                "`objective_profile` 必须包含以下字段：\n"
                "- `current_mission`\n"
                "- `primary_objectives`\n"
                "- `secondary_objectives`\n"
                "- `completion_conditions`\n"
                "- `pause_conditions`\n"
                "- `escalation_conditions`\n"
                "- `current_phase_tasks`\n"
                "- `priority_order`\n\n"
                "`task_queue` 必须是对象，且只能包含：\n"
                "- `next_self_tasks`\n"
                "- `blocked_self_tasks`\n"
                "- `proactive_actions`\n\n"
                "禁止返回旧字段或旧结构：\n"
                "- 不要使用 `main_objective`\n"
                "- 不要使用 `rationale`\n"
                "- 不要使用 `constraints_adherence`\n"
                "- 不要使用 `derived_capabilities`\n"
                "- 不要把 `task_queue` 输出成数组\n"
                "- 不要输出 Q9 的 `evaluation_profile`\n"
                "- 不要输出 Q9 的 `evolution_profile`\n"
                "- 不要输出 Q9 的 `escalation_profile`\n"
                "- 不要输出任何解释文字、markdown、代码块"
            ),
        ),
    ]
    user_prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "q1_q7_snapshot": compact_snapshot,
        "nine_questions": compact_snapshot,
        "persistent_task_state": compact_task_state,
        "q8_priority_baseline": compact_priority_baseline,
        "active_objectives": compact_active_objectives,
        "functional_objectives": compact_functional_objectives,
        "q8_prompt_preprocessing_report": preprocessing_report,
    }
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": user_prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }


def build_q8_staged_llm_request(
    *,
    system_prompt: str,
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_llm_output: Any | None = None,
    q7_snapshot: Any,
    normalized_task_state: dict[str, list[dict[str, Any]]],
    request_timeout_seconds: float,
    request_scope: str = "internal",
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    q1_q7_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (request_scope or "").strip().lower() == "external":
        from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.llm_request import (
            build_q8_external_staged_llm_request,
        )

        return build_q8_external_staged_llm_request(
            system_prompt=system_prompt,
            priority_baseline=priority_baseline,
            allowed_tasks=allowed_tasks,
            blocked_tasks=blocked_tasks,
            q1_llm_output=q1_llm_output,
            q7_snapshot=q7_snapshot,
            normalized_task_state=normalized_task_state,
            request_timeout_seconds=request_timeout_seconds,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q4_external_capabilities=q4_external_capabilities,
            q7_redlines=q7_redlines,
            q1_q7_snapshot=q1_q7_snapshot,
        )

    from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks.llm_request import (
        build_q8_internal_staged_llm_request,
    )

    return build_q8_internal_staged_llm_request(
        system_prompt=system_prompt,
        priority_baseline=priority_baseline,
        allowed_tasks=allowed_tasks,
        blocked_tasks=blocked_tasks,
        q1_llm_output=q1_llm_output,
        q7_snapshot=q7_snapshot,
        normalized_task_state=normalized_task_state,
        request_timeout_seconds=request_timeout_seconds,
        q2_cognitive_plugins=q2_cognitive_plugins,
        q2_functional_plugins=q2_functional_plugins,
        q7_redlines=q7_redlines,
        q1_q7_snapshot=q1_q7_snapshot,
    )
