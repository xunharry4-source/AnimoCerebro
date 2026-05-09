from __future__ import annotations

import json
from typing import Any


_OBJECTIVE_PROFILE_FIELDS = (
    "current_mission",
    "mission_rationale",
    "current_phase_tasks",
    "priority_order",
    "primary_objectives",
    "secondary_objectives",
    "completion_conditions",
    "pause_conditions",
    "escalation_conditions",
)

_TASK_ITEM_FIELDS = (
    "task_id",
    "title",
    "status",
    "executor_type",
    "target_id",
    "required_capabilities",
    "success_criteria",
    "acceptance_conditions",
)

_TASK_QUEUE_FIELDS = (
    "next_self_tasks",
    "proactive_actions",
    "blocked_self_tasks",
)


def build_q9_q8_public_action_context(q8_public_output: dict[str, Any], *, expected_scope: str) -> dict[str, Any]:
    """Project Q8 public output into the smaller action-design surface Q9 needs."""
    if not isinstance(q8_public_output, dict):
        raise RuntimeError("q9_q8_public_output_not_dict")
    scope = str(q8_public_output.get("scope") or "").strip()
    if scope != expected_scope:
        raise RuntimeError(f"q9_q8_public_scope_mismatch: expected={expected_scope!r} actual={scope!r}")

    action_context = {
        "scope": scope,
        "objective_profile": _compact_objective_profile(q8_public_output.get("objective_profile")),
        "task_queue": _compact_task_queue(q8_public_output.get("task_queue")),
        "source_contract": {
            "upstream": "q8_public_service",
            "excluded_public_sections": [
                "deep_task_plan_rules",
                "task_metadata_payloads",
                "raw_boundary_source_payloads",
            ],
            "q7_constraint_route": "Q7 boundaries are consumed only through Q8 public objective and task fields.",
        },
    }
    if not action_context["objective_profile"].get("current_mission"):
        raise RuntimeError("q9_q8_public_current_mission_missing")
    if not _has_any_task(action_context["task_queue"]):
        raise RuntimeError("q9_q8_public_task_queue_empty")
    return action_context


def q9_public_action_context_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _compact_objective_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("q9_q8_public_objective_profile_missing")
    compact: dict[str, Any] = {}
    for field in _OBJECTIVE_PROFILE_FIELDS:
        if field in value:
            compact[field] = value[field]
    return compact


def _compact_task_queue(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("q9_q8_public_task_queue_missing")
    compact: dict[str, Any] = {}
    for field in _TASK_QUEUE_FIELDS:
        items = value.get(field)
        if not isinstance(items, list):
            compact[field] = []
            continue
        compact[field] = [_compact_task_item(item) for item in items if isinstance(item, dict)]
    return compact


def _compact_task_item(item: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for field in _TASK_ITEM_FIELDS:
        if item.get(field) not in (None, "", [], {}):
            compact[field] = item[field]
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        metadata_compact = {
            key: metadata[key]
            for key in ("source_chain", "q8_dual_prompt_schema", "functional_plugin_required", "receipt_required")
            if metadata.get(key) not in (None, "", [], {})
        }
        if metadata_compact:
            compact["metadata"] = metadata_compact
    return compact


def _has_any_task(task_queue: dict[str, Any]) -> bool:
    return any(isinstance(task_queue.get(field), list) and task_queue[field] for field in _TASK_QUEUE_FIELDS)
