from __future__ import annotations

"""
Q8 (我现在应该做什么) evidence building and extraction.

Contains functions for building and extracting EVIDENCE_Q8 evidence.
"""

from typing import Any, Dict, List, Optional, Union

from zentex.web_console.contracts.nine_questions import (
    Q8PreprocessedEvidence,
    Q8WhatShouldIDoNowInferenceView,
    Q8AggregatedContextEvidence,
    Q8RuntimeStateEvidence,
    Q8PersistentTaskItem,
    Q8AgendaItem,
    Q8ObjectiveProfileView,
    Q8AutonomousTaskQueueView,
)

from .helpers import _coerce_string_list


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_q8_snapshot_dict(context_payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = (
        context_payload.get("q8_q1_q7_snapshot")
        or context_payload.get("q1_q7_snapshot")
        or context_payload.get("nine_questions")
        or {}
    )
    if isinstance(snapshot, dict):
        return {str(k): v for k, v in snapshot.items() if str(k).strip()}
    return {}


def _count_q8_redlines(snapshot: dict[str, Any]) -> int:
    q6 = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    q5 = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q7 = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    q6_profile = q6.get("forbidden_zone_profile") if isinstance(q6.get("forbidden_zone_profile"), dict) else {}
    q5_profile = q5.get("authorization_boundary_profile") if isinstance(q5.get("authorization_boundary_profile"), dict) else {}
    q7_profile = q7.get("red_line_assessment") if isinstance(q7.get("red_line_assessment"), dict) else {}
    return len(
        _coerce_string_list(q6.get("absolute_red_lines") or q6_profile.get("absolute_red_lines"))
        + _coerce_string_list(q6.get("non_bypassable_constraints") or q6_profile.get("non_bypassable_constraints"))
        + _coerce_string_list(q5.get("explicitly_forbidden_actions") or q5_profile.get("explicitly_forbidden_actions"))
        + _coerce_string_list(q7.get("non_bypassable_constraints") or q7_profile.get("non_bypassable_constraints"))
        + _coerce_string_list(q7.get("current_red_line_hits") or q7_profile.get("current_red_line_hits"))
    )


def _count_q8_capability_ceilings(snapshot: dict[str, Any]) -> int:
    q4 = snapshot.get("q4") if isinstance(snapshot.get("q4"), dict) else {}
    q7 = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    q4_profile = q4.get("capability_boundary_profile") if isinstance(q4.get("capability_boundary_profile"), dict) else {}
    q7_profile = q7.get("alternative_strategy_profile") if isinstance(q7.get("alternative_strategy_profile"), dict) else {}
    return len(
        _coerce_string_list(q4.get("capability_upper_limits") or q4_profile.get("capability_upper_limits"))
        + _coerce_string_list(q4.get("actionable_space") or q4_profile.get("actionable_space"))
        + _coerce_string_list(q7.get("capability_limits") or q7_profile.get("capability_limits"))
    )


def _coerce_q8_persistent_items(raw: object) -> list[Q8PersistentTaskItem]:
    if not isinstance(raw, dict):
        return []

    items: list[Q8PersistentTaskItem] = []
    for status_key, value in raw.items():
        if isinstance(value, list):
            for index, entry in enumerate(value):
                if isinstance(entry, dict):
                    title = str(entry.get("title") or entry.get("task") or entry.get("id") or f"{status_key}-{index}")
                    items.append(
                        Q8PersistentTaskItem(
                            item_id=str(entry.get("id") or f"{status_key}-{index}"),
                            title=title,
                            status=str(entry.get("status") or status_key),
                            priority=entry.get("priority") if isinstance(entry.get("priority"), int) else None,
                            blocker_reason=str(entry.get("blocker_reason") or entry.get("reason") or "")
                            or None,
                        )
                    )
                else:
                    items.append(
                        Q8PersistentTaskItem(
                            item_id=f"{status_key}-{index}",
                            title=str(entry),
                            status=str(status_key),
                        )
                    )
    return items


def _coerce_q8_agenda_items(raw: object) -> list[Q8AgendaItem]:
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []

    agenda_items: list[Q8AgendaItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        agenda_items.append(
            Q8AgendaItem(
                item_id=str(item.get("item_id") or item.get("id") or f"agenda-{index}"),
                title=str(item.get("title") or item.get("item_id") or item.get("id") or f"agenda-{index}"),
                status=str(item.get("status") or "open"),
                priority=item.get("priority") if isinstance(item.get("priority"), int) else None,
                next_review_condition=str(item.get("next_review_condition") or "") or None,
                delay_risk_score=float(item.get("delay_risk_score"))
                if isinstance(item.get("delay_risk_score"), (int, float))
                else None,
            )
        )
    return agenda_items


def _build_q8_preprocessed_evidence(context_payload: dict[str, Any]) -> Optional[Q8PreprocessedEvidence]:
    snapshot = _extract_q8_snapshot_dict(context_payload)
    task_state = _coerce_q8_persistent_items(
        context_payload.get("q8_persistent_task_state")
        or context_payload.get("persistent_task_state")
        or (context_payload.get("q8_objective_and_queue") or {}).get("persistent_task_state")
    )
    agenda_items = _coerce_q8_agenda_items(
        context_payload.get("cognitive_agenda")
        or context_payload.get("q8_cognitive_agenda")
        or (context_payload.get("q8_objective_and_queue") or {}).get("cognitive_agenda")
    )
    if not snapshot and not task_state and not agenda_items:
        return None

    return Q8PreprocessedEvidence(
        aggregated_context=Q8AggregatedContextEvidence(
            q1_to_q7_snapshot=snapshot,
            absolute_red_line_count=_count_q8_redlines(snapshot),
            capability_ceiling_count=_count_q8_capability_ceilings(snapshot),
        ),
        runtime_state=Q8RuntimeStateEvidence(
            persistent_task_state=task_state,
            cognitive_agenda=agenda_items,
        ),
    )


def _extract_q8_preprocessed_evidence(context_payload: object) -> Optional[Q8PreprocessedEvidence]:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("q8_q1_q7_snapshot", "q1_q7_snapshot", "nine_questions", "q8_persistent_task_state", "persistent_task_state", "cognitive_agenda")
    ):
        return None
    return _build_q8_preprocessed_evidence(context_payload)


def _extract_q8_inference_result(result_payload: object) -> Optional[Q8WhatShouldIDoNowInferenceView]:
    if not isinstance(result_payload, dict):
        return None

    aggregate_raw = result_payload.get("q8_objective_and_queue") or {}
    objective_raw = (
        result_payload.get("objective_profile")
        or result_payload.get("objective")
        or result_payload.get("q8_objective_profile")
        or (aggregate_raw.get("q8_objective_profile") if isinstance(aggregate_raw, dict) else None)
        or (aggregate_raw.get("objective") if isinstance(aggregate_raw, dict) else None)
    )
    queue_raw = (
        result_payload.get("task_queue")
        or result_payload.get("q8_task_queue")
        or (aggregate_raw.get("q8_task_queue") if isinstance(aggregate_raw, dict) else None)
        or (aggregate_raw.get("task_queue") if isinstance(aggregate_raw, dict) else None)
    )
    internal_tasks_raw = (
        result_payload.get("q8_internal_cognitive_tasks")
        or result_payload.get("internal_cognitive_tasks")
        or (_dict_or_empty(result_payload.get("q8_internal_llm_output")).get("internal_cognitive_tasks"))
        or (aggregate_raw.get("q8_internal_cognitive_tasks") if isinstance(aggregate_raw, dict) else None)
        or (aggregate_raw.get("internal_cognitive_tasks") if isinstance(aggregate_raw, dict) else None)
        or (_dict_or_empty(aggregate_raw.get("q8_internal_llm_output")).get("internal_cognitive_tasks") if isinstance(aggregate_raw, dict) else None)
        or []
    )
    external_tasks_raw = (
        result_payload.get("q8_external_execution_tasks")
        or result_payload.get("external_execution_tasks")
        or (_dict_or_empty(result_payload.get("q8_external_llm_output")).get("external_execution_tasks"))
        or (aggregate_raw.get("q8_external_execution_tasks") if isinstance(aggregate_raw, dict) else None)
        or (aggregate_raw.get("external_execution_tasks") if isinstance(aggregate_raw, dict) else None)
        or (_dict_or_empty(aggregate_raw.get("q8_external_llm_output")).get("external_execution_tasks") if isinstance(aggregate_raw, dict) else None)
        or []
    )
    if not isinstance(objective_raw, dict):
        objective_raw = {}
    if not isinstance(queue_raw, dict):
        queue_raw = {}
    if not objective_raw and not queue_raw and not internal_tasks_raw and not external_tasks_raw:
        return None

    def _normalize_queue_rows(value: object, *, status: str) -> list[dict[str, Any]]:
        if isinstance(value, str):
            text = value.strip()
            return [{"task_id": f"{status}-0", "title": text, "status": status}] if text else []

        if not isinstance(value, list):
            return []

        rows: list[dict[str, Any]] = []
        char_titles: list[str] = []
        for index, item in enumerate(value):
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("task") or "").strip()
                task_id = str(item.get("task_id") or item.get("id") or f"{status}-{index}").strip()
                row_status = str(item.get("status") or status).strip() or status
                if title and len(title) == 1 and task_id.startswith(f"{status}-"):
                    char_titles.append(title)
                    continue
                if title:
                    rows.append(
                        {
                            **item,
                            "task_id": task_id,
                            "title": title,
                            "status": row_status,
                        }
                    )
                continue

            text = str(item or "").strip()
            if text:
                rows.append({"task_id": f"{status}-{index}", "title": text, "status": status})

        if char_titles and not rows:
            rows.append({"task_id": f"{status}-0", "title": "".join(char_titles), "status": status})
        return rows

    return Q8WhatShouldIDoNowInferenceView(
        objective_profile=Q8ObjectiveProfileView(
            current_primary_objective=str(objective_raw.get("current_mission") or objective_raw.get("current_primary_objective") or ""),
            primary_objectives=_coerce_string_list(objective_raw.get("primary_objectives")),
            secondary_objectives=_coerce_string_list(objective_raw.get("secondary_objectives")),
            completion_conditions=_coerce_string_list(objective_raw.get("completion_conditions")),
            pause_conditions=_coerce_string_list(objective_raw.get("pause_conditions")),
            escalation_conditions=_coerce_string_list(objective_raw.get("escalation_conditions")),
            current_phase_tasks=_coerce_string_list(objective_raw.get("current_phase_tasks")),
            priority_order=_coerce_string_list(objective_raw.get("priority_order")),
        ),
        task_queue=Q8AutonomousTaskQueueView(
            next_self_tasks=_normalize_queue_rows(queue_raw.get("next_self_tasks"), status="next"),
            blocked_self_tasks=_normalize_queue_rows(queue_raw.get("blocked_self_tasks"), status="blocked"),
            proactive_actions=_normalize_queue_rows(queue_raw.get("proactive_actions"), status="proactive"),
        ),
        q8_internal_cognitive_tasks=[
            item for item in internal_tasks_raw if isinstance(item, dict)
        ] if isinstance(internal_tasks_raw, list) else [],
        q8_external_execution_tasks=[
            item for item in external_tasks_raw if isinstance(item, dict)
        ] if isinstance(external_tasks_raw, list) else [],
    )
