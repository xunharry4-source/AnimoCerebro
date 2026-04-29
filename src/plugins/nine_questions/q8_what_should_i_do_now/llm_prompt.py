from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)

_MAX_Q8_CONTEXT_CHARS = 4000
_MAX_OBJECTIVE_CATALOG_CHARS = 2000
_MAX_TASK_STATE_ITEMS = 6
_MAX_TASK_STATE_ITEM_CHARS = 500
_MAX_FUNCTIONAL_OBJECTIVES = 12
_MAX_FUNCTIONAL_OBJECTIVE_CHARS = 800
_MAX_ACTIVE_OBJECTIVES = 12
_MAX_ACTIVE_OBJECTIVE_CHARS = 220
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
        "allowed_action_space": ("list", 8, 180),
        "forbidden_action_space": ("list", 8, 180),
        "requires_escalation_actions": ("list", 6, 180),
        "authorized_actions": ("list", 8, 160),
        "unauthorized_actions": ("list", 8, 180),
        "conditional_actions": ("list", 8, 180),
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
        "fallback_plans": ("list", 8, 180),
        "degradation_strategies": ("list", 8, 180),
        "collaboration_switches": ("list", 6, 180),
        "exploratory_actions": ("list", 6, 180),
        "capability_limits": ("list", 8, 180),
        "permission_boundaries": ("list", 8, 180),
        "resource_bottlenecks": ("list", 6, 180),
    },
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _text(value: Any, *, max_chars: int, path: str, report: dict[str, Any]) -> str:
    text = str(value or "").strip()
    if len(text) > max_chars:
        report["truncated_fields"].append({"path": path, "from": len(text), "to": max_chars})
        return text[:max_chars]
    return text


def _list(value: Any, *, max_count: int, max_chars: int, path: str, report: dict[str, Any]) -> list[str]:
    if not isinstance(value, list):
        if value not in (None, "", {}, []):
            report["type_mismatches"].append({"path": path, "expected": "list", "actual": type(value).__name__})
        return []
    normalized: list[str] = []
    for index, item in enumerate(value):
        if len(normalized) >= max_count:
            report["truncated_fields"].append({"path": path, "from": len(value), "to": max_count})
            break
        text = _text(item, max_chars=max_chars, path=f"{path}[{index}]", report=report)
        if text:
            normalized.append(text)
    return normalized


def _compact_by_spec(value: Any, spec: Any, *, path: str, report: dict[str, Any]) -> Any:
    if isinstance(spec, tuple):
        kind = spec[0]
        if kind == "text":
            return _text(value, max_chars=int(spec[1]), path=path, report=report)
        if kind == "list":
            return _list(value, max_count=int(spec[1]), max_chars=int(spec[2]), path=path, report=report)
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
    compact = dict(snapshot)
    while len(_json(compact)) > _MAX_Q8_CONTEXT_CHARS and compact:
        removed_key = next((key for key in ("q3", "q1", "q2", "q7") if key in compact), None)
        if removed_key is None:
            removed_key = next(iter(compact))
        compact.pop(removed_key, None)
        report["budget_dropped_questions"].append(removed_key)
    return compact


def build_q8_prompt_snapshot(q1_q7_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the compact Q8 prompt snapshot using an explicit field-intent map."""
    report: dict[str, Any] = {
        "max_context_chars": _MAX_Q8_CONTEXT_CHARS,
        "missing_required_questions": [],
        "dropped_raw_fields": [],
        "dropped_unmapped_fields": [],
        "truncated_fields": [],
        "type_mismatches": [],
        "budget_dropped_questions": [],
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
                    max_chars=_MAX_TASK_STATE_ITEM_CHARS,
                    path=f"{path}.{key_text}",
                    report=report,
                )
            return compact_item
        return _text(item, max_chars=_MAX_TASK_STATE_ITEM_CHARS, path=path, report=report)

    if isinstance(persistent_task_state, dict):
        compact: dict[str, Any] = {}
        for key, value in persistent_task_state.items():
            if isinstance(value, list):
                compact[str(key)] = [
                    _compact_task_item(item, f"task_state.{key}[{index}]")
                    for index, item in enumerate(value[:_MAX_TASK_STATE_ITEMS])
                ]
                if len(value) > _MAX_TASK_STATE_ITEMS:
                    report["truncated_fields"].append(
                        {"path": f"task_state.{key}", "from": len(value), "to": _MAX_TASK_STATE_ITEMS}
                    )
            else:
                compact[str(key)] = _compact_task_item(value, f"task_state.{key}")
        return compact
    if isinstance(persistent_task_state, list):
        if len(persistent_task_state) > 24:
            report["truncated_fields"].append({"path": "task_state", "from": len(persistent_task_state), "to": 24})
        return [
            _compact_task_item(item, f"task_state[{index}]")
            for index, item in enumerate(persistent_task_state[:24])
        ]
    return []


def _compact_functional_objectives(functional_objectives: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for index, item in enumerate(functional_objectives[:_MAX_FUNCTIONAL_OBJECTIVES]):
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
                    max_chars=_MAX_FUNCTIONAL_OBJECTIVE_CHARS,
                    path=f"functional_objectives[{index}].{key}",
                    report=report,
                )
        if cleaned:
            compact.append(cleaned)
    if len(functional_objectives) > _MAX_FUNCTIONAL_OBJECTIVES:
        report["truncated_fields"].append(
            {"path": "functional_objectives", "from": len(functional_objectives), "to": _MAX_FUNCTIONAL_OBJECTIVES}
        )
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
        _text(item, max_chars=_MAX_ACTIVE_OBJECTIVE_CHARS, path=f"active_objectives[{index}]", report=preprocessing_report)
        for index, item in enumerate(active_objectives[:_MAX_ACTIVE_OBJECTIVES])
    ]
    if len(active_objectives) > _MAX_ACTIVE_OBJECTIVES:
        preprocessing_report["truncated_fields"].append(
            {"path": "active_objectives", "from": len(active_objectives), "to": _MAX_ACTIVE_OBJECTIVES}
        )
    compact_objective_catalog = _text(
        objective_catalog,
        max_chars=_MAX_OBJECTIVE_CATALOG_CHARS,
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
            key="preprocessing_report",
            title="Q8 Prompt Preprocessing Report",
            intent="Expose truncation, missing required upstreams, and dropped raw fields.",
            purpose="Prevent silent degradation or hidden prompt-input loss.",
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
