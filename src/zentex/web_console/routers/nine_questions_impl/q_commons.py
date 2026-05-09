from __future__ import annotations
"""Common Nine-Questions Service Layer

Provides shared utilities for:
- Session management (get/create)
- State management (get/update)
- Question report building
- Common error handling
"""


import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from zentex.web_console.contracts.nine_questions import NineQuestionReportItem
from zentex.nine_questions.question_driver_framework import (
    ensure_mounted_plugins,
)
from .q_state import (
    _get_nine_question_service,
    get_or_create_session,
    get_question_snapshot_map,
)
from .route_handlers_shared import QUESTION_TITLES
from .evidence_q1 import _extract_q1_llm_upgrade
from .q_handlers import QUESTION_HANDLERS

logger = logging.getLogger(__name__)

EXPECTED_QUESTION_IDS = tuple(f"q{i}" for i in range(1, 10))
_REPORT_PAYLOAD_DROP_KEYS = {
    "execution_context",
    "execution_result",
    "execution_diagnosis",
    "history",
    "histories",
    "llm_trace_payload",
    "module_runs",
    "plugin_runs",
    "recovery_plan",
    "upstream_dependencies",
    "versions",
    "previous_versions",
    "historical_versions",
    "version_history",
    "snapshot_history",
    "snapshot_versions",
    "question_history",
    "question_versions",
    "question_snapshot_history",
    "question_snapshots_history",
}
_UPSTREAM_SNAPSHOT_REF_KEYS = {
    "q1_q7_snapshot",
    "q1_q8_snapshot",
    "q8_q1_q7_snapshot",
    "q9_q1_q8_snapshot",
}


def _compact_report_payload(value: Any) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in _REPORT_PAYLOAD_DROP_KEYS:
                continue
            if key_text in _UPSTREAM_SNAPSHOT_REF_KEYS:
                compacted[key_text] = _compact_question_snapshot_refs(item)
                continue
            compacted[key_text] = _compact_report_payload(item)
        return compacted
    if isinstance(value, list):
        return [_compact_report_payload(item) for item in value]
    return value


def _compact_question_snapshot_refs(value: Any) -> Any:
    if not isinstance(value, dict):
        return _compact_report_payload(value)
    compacted: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text.lower() not in EXPECTED_QUESTION_IDS:
            compacted[key_text] = _compact_report_payload(item)
            continue
        if isinstance(item, dict):
            compacted[key_text] = {
                "question_id": key_text,
                "summary": str(item.get("summary") or ""),
                "trace_id": str(item.get("trace_id") or ""),
                "tool_id": str(item.get("tool_id") or ""),
            }
        else:
            compacted[key_text] = {"question_id": key_text, "summary": str(item or "")}
    return compacted


def _build_question_ref_map(
    refs: dict[str, dict[str, Any]],
    question_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    return {
        question_id: dict(
            refs.get(question_id)
            or {
                "question_id": question_id,
                "summary": QUESTION_TITLES.get(question_id, question_id),
                "trace_id": "",
                "tool_id": f"nine_questions.{question_id}",
            }
        )
        for question_id in question_ids
    }


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_or_strings(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return _coerce_string_list(value)


def _slim_q8_task_row(row: Any, *, index: int, proactive: bool = False) -> dict[str, Any]:
    item = dict(row) if isinstance(row, dict) else {"title": str(row or "")}
    title = str(item.get("title") or item.get("action") or item.get("task_id") or f"task-{index}").strip()
    slim = {
        "task_id": str(item.get("task_id") or item.get("physical_task_id") or f"task-{index}"),
        "title": title,
        "status": str(item.get("status") or item.get("task_status") or ""),
        "reason": str(item.get("reason") or item.get("details") or item.get("description") or title),
    }
    if proactive:
        normalized = _normalize_q8_proactive_actions([item])[0]
        slim.update(
            {
                "source_signal": normalized["source_signal"],
                "authorization_status": normalized["authorization_status"],
                "evidence_ref": normalized["evidence_ref"],
            }
        )
    return slim


def _slim_q8_task_queue(task_queue: Any) -> dict[str, Any]:
    queue = _dict_or_empty(task_queue)
    next_rows = _list_or_strings(queue.get("next_self_tasks"))
    blocked_rows = _list_or_strings(queue.get("blocked_self_tasks"))
    proactive_rows = _normalize_q8_proactive_actions(queue.get("proactive_actions") or [])
    return {
        "next_self_tasks": [
            _slim_q8_task_row(row, index=index)
            for index, row in enumerate(next_rows[:10])
        ],
        "blocked_self_tasks": [
            _slim_q8_task_row(row, index=index)
            for index, row in enumerate(blocked_rows[:10])
        ],
        "proactive_actions": [
            _slim_q8_task_row(row, index=index, proactive=True)
            for index, row in enumerate(proactive_rows[:10])
        ],
    }


def _slim_q8_objective_profile(objective_profile: Any, task_queue: Any) -> dict[str, Any]:
    objective = _dict_or_empty(objective_profile)
    queue = _slim_q8_task_queue(task_queue)
    slim = {
        "objective_profile": str(objective.get("objective_profile") or objective.get("profile_id") or "q8_current_objective"),
        "current_mission": str(objective.get("current_mission") or objective.get("current_primary_objective") or ""),
        "current_primary_objective": str(objective.get("current_primary_objective") or objective.get("current_mission") or ""),
        "primary_objectives": _list_or_strings(objective.get("primary_objectives"))[:10],
        "secondary_objectives": _list_or_strings(objective.get("secondary_objectives"))[:10],
        "completion_conditions": _list_or_strings(objective.get("completion_conditions"))[:10],
        "pause_conditions": _list_or_strings(objective.get("pause_conditions"))[:10],
        "escalation_conditions": _list_or_strings(objective.get("escalation_conditions"))[:10],
        "proactive_actions": queue["proactive_actions"],
    }
    return {key: value for key, value in slim.items() if value not in (None, "", [], {})}


def _project_list_report_payload(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], Any, Any]:
    """Return the bounded read model for report/list endpoints."""
    if question_id == "q1":
        result = {
            "workspace_path": _first_present(result_payload.get("workspace_path"), context_updates.get("workspace_path"), result_payload.get("workspace")),
            "session_id": _first_present(result_payload.get("session_id"), context_updates.get("session_id")),
            "runtime": _first_present(result_payload.get("runtime"), context_updates.get("runtime"), context_updates.get("environment_event")),
        }
        return result, {"nine_questions": context_updates.get("nine_questions", {})}, None, None

    if question_id == "q2":
        inventory = _dict_or_empty(_first_present(result_payload.get("asset_inventory"), context_updates.get("q2_asset_inventory")))
        resource = _dict_or_empty(_first_present(result_payload.get("resource_evaluation"), context_updates.get("q2_resource_evaluation")))
        result = {
            "asset_inventory": inventory,
            "resource_status": _first_present(resource.get("resource_status"), result_payload.get("resource_status")),
            "missing_critical_assets": _list_or_strings(resource.get("missing_critical_assets"))[:10],
            "bottleneck_node": resource.get("bottleneck_node"),
        }
        return result, {}, None, None

    if question_id == "q3":
        q3_result = result_payload.get("Q3InferenceResult") if isinstance(result_payload.get("Q3InferenceResult"), dict) else {}
        role = _dict_or_empty(_first_present(q3_result.get("RoleProfile"), context_updates.get("q3_role_profile")))
        boundary = _dict_or_empty(_first_present(q3_result.get("MissionContinuityBoundary"), context_updates.get("q3_mission_boundary")))
        result = {
            "identity": _first_present(result_payload.get("identity"), role.get("identity_role"), role.get("active_role"), "zentex_agent"),
            "role": _first_present(result_payload.get("role"), role.get("active_role"), role),
            "inferred_reference_role": role.get("inferred_reference_role"),
            "role_alignment_gap": role.get("role_alignment_gap"),
            "mission_boundary": boundary,
        }
        return result, {}, None, None

    if question_id == "q4":
        result = {
            "action_candidates": _list_or_strings(_first_present(result_payload.get("action_candidates"), context_updates.get("action_candidates"), []))[:20],
            "required_inputs": _list_or_strings(_first_present(result_payload.get("required_inputs"), context_updates.get("required_inputs"), []))[:20],
            "verification": _list_or_strings(_first_present(result_payload.get("verification"), context_updates.get("verification"), []))[:20],
        }
        context = {"capability_action_mapping": context_updates.get("capability_action_mapping") or {"action_candidates": result["action_candidates"]}}
        return result, context, None, None

    if question_id == "q5":
        result = {
            "allowed": _list_or_strings(_first_present(result_payload.get("allowed"), context_updates.get("allowed"), []))[:20],
            "confirmation": _list_or_strings(_first_present(result_payload.get("confirmation"), context_updates.get("confirmation"), []))[:20],
            "denied": _list_or_strings(_first_present(result_payload.get("denied"), context_updates.get("blocked"), []))[:20],
        }
        return result, {"blocked": result["denied"]}, None, None

    if question_id == "q6":
        prohibited = _list_or_strings(_first_present(result_payload.get("prohibited"), result_payload.get("forbidden"), context_updates.get("blocked_patterns"), []))[:30]
        result = {
            "risk_flags": _list_or_strings(_first_present(result_payload.get("risk_flags"), context_updates.get("risk_flags"), ["risk_unverified_action"]))[:20],
            "prohibited": prohibited,
            "forbidden": prohibited,
        }
        context = {"blocked_patterns": prohibited, "pause": _first_present(context_updates.get("pause"), context_updates.get("escalation"), ["risk review required"])}
        return result, context, None, None

    if question_id == "q7":
        result = {
            "current_red_line_hits": _list_or_strings(
                _first_present(result_payload.get("current_red_line_hits"), context_updates.get("q7_current_red_line_hits"), [])
            )[:20],
            "rejected_operation_records": _list_or_strings(
                _first_present(result_payload.get("rejected_operation_records"), context_updates.get("q7_rejected_operation_records"), [])
            )[:20],
            "non_bypassable_constraints": _list_or_strings(
                _first_present(result_payload.get("non_bypassable_constraints"), context_updates.get("q7_non_bypassable_constraints"), [])
            )[:30],
        }
        return result, {"q7_red_line_assessment": result}, None, result

    if question_id == "q8":
        objective = _first_present(result_payload.get("objective_profile"), context_updates.get("q8_objective_profile"), {})
        queue = _first_present(result_payload.get("task_queue"), context_updates.get("q8_task_queue"), {})
        slim_queue = _slim_q8_task_queue(queue)
        slim_objective = _slim_q8_objective_profile(objective, queue)
        upstream = _compact_question_snapshot_refs(
            _first_present(context_updates.get("q8_q1_q7_snapshot"), context_updates.get("q1_q7_snapshot"), result_payload.get("q1_q7_snapshot"), {})
        )
        result = {"objective_profile": slim_objective, "task_queue": slim_queue, "q1_q7_snapshot": upstream}
        context = {"q8_objective_profile": slim_objective, "q8_task_queue": slim_queue, "q8_q1_q7_snapshot": upstream}
        inference = {"objective_profile": slim_objective, "task_queue": slim_queue}
        return result, context, None, inference

    if question_id == "q9":
        upstream = _compact_question_snapshot_refs(
            _first_present(context_updates.get("q9_q1_q8_snapshot"), context_updates.get("q1_q8_snapshot"), result_payload.get("q1_q8_snapshot"), {})
        )
        posture = _first_present(result_payload.get("posture"), result_payload.get("q9_evaluation_profile"), context_updates.get("q9_evaluation_profile"), {"posture": "steady_fail_closed"})
        result = {
            "posture": posture,
            "q9_evaluation_profile": posture,
            "action_rhythm_hint": _first_present(result_payload.get("action_rhythm_hint"), context_updates.get("action_rhythm_hint"), "conservative"),
            "dispatch_gate": _first_present(result_payload.get("dispatch_gate"), context_updates.get("dispatch_gate"), "confirm_before_commit"),
        }
        context = {"q9_q1_q8_snapshot": upstream, "q9_evaluation_profile": posture, "dispatch_gate": result["dispatch_gate"]}
        return result, context, None, None

    return result_payload, context_updates, None, None


def _ensure_q4_action_mapping_aliases(
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> None:
    candidates = result_payload.get("action_candidates")
    if not candidates:
        candidates = result_payload.get("ranked_options") or result_payload.get("proposals")
    if not candidates:
        candidates = context_updates.get("q4_functional_capabilities") or context_updates.get("q4_capability_baseline")
    if candidates and not result_payload.get("action_candidates"):
        result_payload["action_candidates"] = candidates
    if candidates and not context_updates.get("capability_action_mapping"):
        context_updates["capability_action_mapping"] = {
            "action_candidates": candidates,
            "source": "q4_existing_capability_projection",
        }


def _normalize_q8_proactive_actions(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        rows = _coerce_string_list(rows)
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row) if isinstance(row, dict) else {"title": str(row or "")}
        title = str(item.get("title") or item.get("action") or f"proactive-{index}").strip()
        detail = str(item.get("details") or item.get("description") or item.get("action") or title).strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        item["title"] = title or f"proactive-{index}"
        item["reason"] = str(item.get("reason") or detail or "q8 proactive action derived from current objective").strip()
        item["source_signal"] = str(
            item.get("source_signal")
            or metadata.get("source_signal")
            or metadata.get("source_chain")
            or "q8_task_queue.proactive_actions"
        ).strip()
        item["authorization_status"] = str(
            item.get("authorization_status")
            or metadata.get("authorization_status")
            or "authorized_by_q5_current_boundary"
        ).strip()
        item["evidence_ref"] = str(
            item.get("evidence_ref")
            or item.get("trace_id")
            or item.get("task_id")
            or f"q8:proactive:{index}"
        ).strip()
        normalized.append(item)
    return normalized


def _ensure_legacy_report_aliases(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> None:
    if question_id == "q4":
        _ensure_q4_action_mapping_aliases(result_payload, context_updates)
        return
    if question_id == "q5":
        denied = (
            result_payload.get("denied")
            or result_payload.get("denied_actions")
            or result_payload.get("blocked")
            or result_payload.get("blocked_actions")
            or result_payload.get("explicitly_forbidden_actions")
            or context_updates.get("denied")
            or context_updates.get("denied_actions")
            or context_updates.get("blocked")
            or context_updates.get("blocked_actions")
            or context_updates.get("explicitly_forbidden_actions")
            or []
        )
        result_payload.setdefault("denied", denied)
        context_updates.setdefault("blocked", denied)
        return
    if question_id == "q6":
        standard_redlines = [
            "fake_runtime_state",
            "mock_runtime_state",
            "silent_fallback_on_missing_dependency",
            "secret_disclosure",
            "risk_unverified_action",
        ]
        prohibited = (
            result_payload.get("prohibited")
            or result_payload.get("blocked_patterns")
            or result_payload.get("forbidden")
            or context_updates.get("prohibited")
            or context_updates.get("blocked_patterns")
            or context_updates.get("forbidden")
            or []
        )
        if not isinstance(prohibited, list):
            prohibited = [prohibited]
        prohibited = list(dict.fromkeys([*prohibited, *standard_redlines]))
        result_payload["prohibited"] = prohibited
        result_payload.setdefault("forbidden", prohibited)
        context_updates.setdefault("blocked_patterns", prohibited)
        context_updates.setdefault("pause", context_updates.get("escalation") or result_payload.get("escalation") or {})
        return
    if question_id == "q7":
        result_payload.setdefault("alternative", result_payload.get("alternatives") or context_updates.get("alternatives") or [])
        result_payload.setdefault("fallback", result_payload.get("fallback_policy") or context_updates.get("fallback_policy") or {})
        context_updates.setdefault("recovery", result_payload.get("recovery") or context_updates.get("recover") or {})
        return
    if question_id == "q8":
        objective_profile = (
            result_payload.get("objective_profile")
            or context_updates.get("q8_objective_profile")
            or {}
        )
        task_queue = (
            result_payload.get("task_queue")
            or context_updates.get("q8_task_queue")
            or {}
        )
        objective_profile = dict(objective_profile) if isinstance(objective_profile, dict) else {}
        task_queue = dict(task_queue) if isinstance(task_queue, dict) else {}
        proactive = _normalize_q8_proactive_actions(
            objective_profile.get("proactive_actions") or task_queue.get("proactive_actions") or []
        )
        if proactive:
            objective_profile["proactive_actions"] = proactive
            task_queue["proactive_actions"] = proactive
        result_payload["objective_profile"] = objective_profile
        result_payload["task_queue"] = task_queue
        context_updates["q8_objective_profile"] = objective_profile
        context_updates["q8_task_queue"] = task_queue


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        return value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}


def _q8_task_to_web_binding(task: Any, outcome: dict[str, Any] | None) -> dict[str, Any]:
    contract = getattr(task, "contract", None)
    contract_payload = _model_dump(contract)
    verification = contract_payload.get("verification") if isinstance(contract_payload.get("verification"), dict) else {}
    metadata = getattr(task, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    status = getattr(task, "status", "")
    priority = getattr(task, "priority", "")
    return {
        "task_binding_status": "bound",
        "physical_task_id": str(getattr(task, "task_id", "") or ""),
        "task_status": str(getattr(status, "value", status) or ""),
        "task_priority": str(getattr(priority, "value", priority) or ""),
        "trace_id": str(metadata.get("trace_id") or ""),
        "queue_name": str(metadata.get("queue_name") or ""),
        "expected_outcome": contract_payload.get("expected_outcome") or metadata.get("expected_outcome") or {},
        "success_criteria": contract_payload.get("success_criteria") or metadata.get("success_criteria") or [],
        "acceptance_conditions": contract_payload.get("acceptance_conditions") or metadata.get("acceptance_conditions") or [],
        "verification_method": contract_payload.get("verification_method") or metadata.get("verification_method") or "",
        "risk_assessment": contract_payload.get("risk_assessment") or metadata.get("risk_assessment") or {},
        "verification_enabled": bool(verification.get("enabled")),
        "verification_strategy": str(verification.get("strategy") or ""),
        "task_outcome": outcome or None,
    }


def _enrich_q8_queue_rows_with_task_bindings(
    request: Request,
    *,
    trace_id: str,
    inference_result: Any,
) -> Any:
    if not inference_result:
        return inference_result
    app_state = getattr(getattr(request, "app", None), "state", None)
    task_service = getattr(app_state, "task_service", None)
    if task_service is None:
        return inference_result

    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise RuntimeError("Task service does not expose list_tasks() for Q8 binding")

    q8_tasks = list(list_tasks(metadata_filters={"source": "nine_questions.q8"}) or [])
    if trace_id and not trace_id.endswith(":no-trace"):
        q8_tasks = [
            task
            for task in q8_tasks
            if isinstance(getattr(task, "metadata", None), dict)
            and str(task.metadata.get("trace_id") or "") == trace_id
        ]

    by_queue_title: dict[tuple[str, str], Any] = {}
    for task in q8_tasks:
        metadata = getattr(task, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        key = (str(metadata.get("queue_name") or ""), str(getattr(task, "title", "") or "").strip())
        if key[0] and key[1] and key not in by_queue_title:
            by_queue_title[key] = task

    payload = _model_dump(inference_result)
    queue = payload.get("task_queue") if isinstance(payload.get("task_queue"), dict) else {}

    def _enrich_rows(queue_key: str, status: str) -> list[dict[str, Any]]:
        rows = queue.get(queue_key)
        if not isinstance(rows, list):
            return []
        enriched: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row) if isinstance(row, dict) else {"title": str(row or ""), "status": status}
            title = str(item.get("title") or "").strip()
            task = by_queue_title.get((queue_key, title))
            if task is None:
                enriched.append({**item, "task_binding_status": "missing"})
                continue
            outcome = task_service.get_task_outcome(task.task_id) if callable(getattr(task_service, "get_task_outcome", None)) else None
            enriched.append({**item, **_q8_task_to_web_binding(task, outcome)})
        return enriched

    queue["next_self_tasks"] = _enrich_rows("next_self_tasks", "next")
    queue["blocked_self_tasks"] = _enrich_rows("blocked_self_tasks", "blocked")
    queue["proactive_actions"] = _enrich_rows("proactive_actions", "proactive")
    payload["task_queue"] = queue
    return payload


def _state_has_question_data(state: Any) -> bool:
    snapshot_map = get_question_snapshot_map(state)
    return bool(snapshot_map)


def _merge_trace_projection_payloads(
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
    trace_detail: dict[str, Optional[Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot_execution_context = snapshot.get("execution_context")
    snapshot_execution_context = snapshot_execution_context if isinstance(snapshot_execution_context, dict) else {}
    snapshot_execution_result = snapshot.get("execution_result")
    snapshot_execution_result = snapshot_execution_result if isinstance(snapshot_execution_result, dict) else {}

    trace_context = trace_detail.get("context") if isinstance(trace_detail, dict) else {}
    trace_context = trace_context if isinstance(trace_context, dict) else {}
    trace_result = trace_detail.get("result") if isinstance(trace_detail, dict) else {}
    trace_result = trace_result if isinstance(trace_result, dict) else {}

    nested_result_context_updates = result_payload.get("context_updates")
    nested_result_context_updates = (
        nested_result_context_updates if isinstance(nested_result_context_updates, dict) else {}
    )

    merged_result = dict(snapshot_execution_result)
    merged_result.update(trace_result)
    merged_result.update(result_payload)

    merged_context = dict(snapshot_execution_context)
    merged_context.update(trace_context)
    merged_context.update(nested_result_context_updates)
    merged_context.update(context_updates)

    return merged_result, merged_context


def _state_has_complete_question_data(state: Any) -> bool:
    from .q_state import _state_has_complete_question_data as _shared_state_complete
    return _shared_state_complete(state)


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _trace_payload_has_material(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    invocations = payload.get("invocations")
    if isinstance(invocations, list) and any(_trace_payload_has_material(item) for item in invocations):
        return True
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("provider_name", "model", "prompt", "system_prompt", "context_data", "raw_response", "error_type", "error_message")
    )


def _first_material_trace_payload(*payloads: Any) -> dict[str, Any] | None:
    for payload in payloads:
        if isinstance(payload, dict) and _trace_payload_has_material(payload):
            return payload
    return None


def _material_trace_payload(
    *,
    snapshot: dict[str, Any],
    record_trace_payload: dict[str, Any] | None = None,
    raw_llm_payload: dict[str, Any] | None = None,
    raw_context_llm_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    snapshot_payload = snapshot.get("llm_trace_payload")
    snapshot_payload = snapshot_payload if isinstance(snapshot_payload, dict) else {}

    return _first_material_trace_payload(
        record_trace_payload,
        raw_llm_payload,
        raw_context_llm_payload,
        snapshot_payload,
    )


def _humanize_question_summary(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    if question_id == "q1":
        workspace_domain = (
            result_payload.get("workspace_domain_inference")
            or context_updates.get("workspace_domain_inference")
            or {}
        )
        workspace_domain = workspace_domain if isinstance(workspace_domain, dict) else {}
        primary_domain = str(workspace_domain.get("primary_domain") or "").strip()
        confidence = workspace_domain.get("confidence")
        secondary_count = len(_coerce_string_list(workspace_domain.get("secondary_domains")))
        uncertainty_count = len(_coerce_string_list(workspace_domain.get("uncertainties")))
        parts = []
        if primary_domain:
            parts.append(f"当前工作区主领域判断为 {primary_domain}")
        if isinstance(confidence, (int, float)):
            parts.append(f"置信度 {float(confidence):.2f}")
        if secondary_count:
            parts.append(f"次领域 {secondary_count} 项")
        if uncertainty_count:
            parts.append(f"不确定因素 {uncertainty_count} 项")
        return "，".join(parts)

    if question_id == "q2":
        resource_eval = (
            result_payload.get("resource_evaluation")
            or result_payload.get("sufficiency_assessment")
            or context_updates.get("q2_resource_evaluation")
            or {}
        )
        resource_eval = resource_eval if isinstance(resource_eval, dict) else {}
        resource_status = str(resource_eval.get("resource_status") or "").strip()
        missing_assets = _coerce_string_list(resource_eval.get("missing_critical_assets"))
        bottleneck = str(resource_eval.get("bottleneck_node") or "").strip()
        parts = []
        if resource_status:
            parts.append(f"当前资源状态：{resource_status}")
        if bottleneck:
            parts.append(f"瓶颈节点：{bottleneck}")
        if missing_assets:
            parts.append(f"缺失关键资产 {len(missing_assets)} 项")
        return "，".join(parts)

    if question_id == "q3":
        q3_result = result_payload.get("Q3InferenceResult") if isinstance(result_payload.get("Q3InferenceResult"), dict) else {}
        role_profile = (
            q3_result.get("RoleProfile")
            or context_updates.get("q3_role_profile")
            or {}
        )
        role_profile = role_profile if isinstance(role_profile, dict) else {}
        mission_boundary = (
            q3_result.get("MissionContinuityBoundary")
            or context_updates.get("q3_mission_boundary")
            or {}
        )
        mission_boundary = mission_boundary if isinstance(mission_boundary, dict) else {}
        identity_role = str(role_profile.get("identity_role") or "").strip()
        active_role = str(role_profile.get("active_role") or "").strip()
        current_mission = str(mission_boundary.get("current_mission") or "").strip()
        parts = []
        if identity_role:
            parts.append(f"当前身份角色为 {identity_role}")
        if active_role:
            parts.append(f"活跃角色为 {active_role}")
        inferred_reference_role = str(role_profile.get("inferred_reference_role") or "").strip()
        if inferred_reference_role:
            parts.append(f"系统参考角色为 {inferred_reference_role}")
        if current_mission:
            parts.append(f"当前使命：{current_mission}")
        return "，".join(parts)

    if question_id == "q4":
        capability_profile = (
            result_payload.get("capability_boundary_profile")
            or context_updates.get("q4_capability_boundary_profile")
            or {}
        )
        capability_profile = capability_profile if isinstance(capability_profile, dict) else {}
        upper_limits = _coerce_string_list(capability_profile.get("capability_upper_limits"))
        actionable_space = _coerce_string_list(capability_profile.get("actionable_space"))
        executable_strategies = _coerce_string_list(capability_profile.get("executable_strategies"))
        parts = []
        if upper_limits:
            parts.append(f"能力上限 {len(upper_limits)} 项")
        if actionable_space:
            parts.append(f"可行动空间 {len(actionable_space)} 项")
        if executable_strategies:
            parts.append(f"可执行策略 {len(executable_strategies)} 项")
        return "，".join(parts)

    if question_id == "q5":
        auth_profile = (
            result_payload.get("authorization_boundary")
            or result_payload.get("authorization_boundary_profile")
            or context_updates.get("q5_authorization_boundary")
            or context_updates.get("q5_authorization_boundary_profile")
            or context_updates.get("q5_permission_boundary")
            or {}
        )
        auth_profile = auth_profile if isinstance(auth_profile, dict) else {}
        execution_tier = str(auth_profile.get("execution_tier") or "").strip()
        allowed_actions = _coerce_string_list(auth_profile.get("allowed_actions") or auth_profile.get("allowed_action_space"))
        forbidden_actions = _coerce_string_list(auth_profile.get("forbidden_actions") or auth_profile.get("forbidden_action_space"))
        escalation_actions = _coerce_string_list(auth_profile.get("requires_escalation_actions"))
        parts = []
        if execution_tier:
            parts.append(f"执行层级：{execution_tier}")
        if allowed_actions:
            parts.append(f"允许动作 {len(allowed_actions)} 项")
        if forbidden_actions:
            parts.append(f"禁止动作 {len(forbidden_actions)} 项")
        if escalation_actions:
            parts.append(f"需升级确认 {len(escalation_actions)} 项")
        if not parts and any(key in result_payload for key in ("allowed", "confirmation", "denied")):
            parts.append(f"允许动作 {len(_coerce_string_list(result_payload.get('allowed')))} 项")
            parts.append(f"需确认动作 {len(_coerce_string_list(result_payload.get('confirmation')))} 项")
            parts.append(f"拒绝动作 {len(_coerce_string_list(result_payload.get('denied')))} 项")
        return "，".join(parts)

    if question_id == "q6":
        forbidden_profile = (
            result_payload.get("forbidden_zone_profile")
            or context_updates.get("q6_forbidden_zone_profile")
            or {}
        )
        forbidden_profile = forbidden_profile if isinstance(forbidden_profile, dict) else {}
        red_lines = _coerce_string_list(forbidden_profile.get("absolute_red_lines"))
        bans = _coerce_string_list(forbidden_profile.get("performance_tradeoff_bans"))
        prohibited = _coerce_string_list(forbidden_profile.get("prohibited_strategies"))
        contamination = _coerce_string_list(forbidden_profile.get("contamination_risks"))
        parts = []
        if red_lines:
            parts.append(f"绝对红线 {len(red_lines)} 项")
        if bans:
            parts.append(f"性能权衡禁令 {len(bans)} 项")
        if prohibited:
            parts.append(f"禁止策略 {len(prohibited)} 项")
        if contamination:
            parts.append(f"污染风险 {len(contamination)} 项")
        return "，".join(parts)

    if question_id == "q7":
        red_line_assessment = (
            result_payload.get("red_line_assessment")
            or context_updates.get("q7_red_line_assessment")
            or context_updates.get("red_line_assessment")
            or {}
        )
        red_line_assessment = red_line_assessment if isinstance(red_line_assessment, dict) else {}
        hits = _coerce_string_list(red_line_assessment.get("current_red_line_hits"))
        rejections = _coerce_string_list(red_line_assessment.get("rejected_operation_records"))
        sources = _coerce_string_list(red_line_assessment.get("ban_source_explanations"))
        constraints = _coerce_string_list(red_line_assessment.get("non_bypassable_constraints"))
        parts = []
        if hits:
            parts.append(f"当前红线命中 {len(hits)} 项")
        if rejections:
            parts.append(f"拒绝记录 {len(rejections)} 项")
        if sources:
            parts.append(f"禁令来源 {len(sources)} 项")
        if constraints:
            parts.append(f"不可绕过约束 {len(constraints)} 项")
        return "，".join(parts)

    if question_id == "q8":
        objective_profile = (
            result_payload.get("objective_profile")
            or context_updates.get("q8_objective_profile")
            or {}
        )
        objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
        task_queue = (
            result_payload.get("task_queue")
            or context_updates.get("q8_task_queue")
            or {}
        )
        task_queue = task_queue if isinstance(task_queue, dict) else {}
        objective = str(
            objective_profile.get("current_mission")
            or objective_profile.get("current_primary_objective")
            or ""
        ).strip()
        next_count = len(task_queue.get("next_self_tasks") or []) if isinstance(task_queue.get("next_self_tasks"), list) else len(_coerce_string_list(task_queue.get("next_self_tasks")))
        blocked_count = len(task_queue.get("blocked_self_tasks") or []) if isinstance(task_queue.get("blocked_self_tasks"), list) else len(_coerce_string_list(task_queue.get("blocked_self_tasks")))
        proactive_count = len(task_queue.get("proactive_actions") or []) if isinstance(task_queue.get("proactive_actions"), list) else len(_coerce_string_list(task_queue.get("proactive_actions")))
        parts = []
        if objective:
            parts.append(f"当前主目标：{objective}")
        parts.append(f"下一步 {next_count} 项")
        parts.append(f"阻塞任务 {blocked_count} 项")
        parts.append(f"主动行动 {proactive_count} 项")
        return "，".join(parts)

    if question_id == "q9":
        evaluation_profile = (
            result_payload.get("evaluation_profile")
            or context_updates.get("q9_evaluation_profile")
            or {}
        )
        evaluation_profile = evaluation_profile if isinstance(evaluation_profile, dict) else {}
        evolution_profile = (
            result_payload.get("evolution_profile")
            or context_updates.get("q9_evolution_profile")
            or {}
        )
        evolution_profile = evolution_profile if isinstance(evolution_profile, dict) else {}
        escalation_profile = (
            result_payload.get("escalation_profile")
            or context_updates.get("q9_escalation_profile")
            or {}
        )
        escalation_profile = escalation_profile if isinstance(escalation_profile, dict) else {}
        style = str(evaluation_profile.get("evaluation_style") or "").strip()
        risk = str(
            evaluation_profile.get("risk_level")
            or evaluation_profile.get("risk_tolerance")
            or ""
        ).strip()
        conservative = evaluation_profile.get("conservative_mode_triggered")
        allowed_count = len(_coerce_string_list(evolution_profile.get("allowed_directions")))
        confirm_count = len(_coerce_string_list(escalation_profile.get("confirmation_required_conditions")))
        parts = []
        if style:
            parts.append(f"行动评估风格：{style}")
        if risk:
            parts.append(f"风险容忍度：{risk}")
        if conservative is True:
            parts.append("当前处于保守模式")
        parts.append(f"允许方向 {allowed_count} 项")
        parts.append(f"确认条件 {confirm_count} 项")
        return "，".join(parts)

    return ""


def _derive_provider_name(
    snapshot: dict[str, Any],
    trace_detail: dict[str, Optional[Any]],
    *trace_payloads: Any,
) -> Optional[str]:
    provider_name = str(snapshot.get("provider_name") or "").strip()
    if provider_name:
        return provider_name

    if isinstance(trace_detail, dict):
        trace_payload = trace_detail.get("llm_trace_payload")
        trace_payload = trace_payload if isinstance(trace_payload, dict) else {}
        provider_name = str(
            trace_payload.get("provider_name")
            or trace_detail.get("provider_name")
            or ""
        ).strip()
        if provider_name:
            return provider_name

    for payload in (*trace_payloads, snapshot.get("llm_trace_payload")):
        payload = payload if isinstance(payload, dict) else {}
        provider_name = str(payload.get("provider_name") or "").strip()
        if provider_name:
            return provider_name
        invocations = payload.get("invocations")
        if isinstance(invocations, list):
            for invocation in invocations:
                invocation = invocation if isinstance(invocation, dict) else {}
                provider_name = str(invocation.get("provider_name") or "").strip()
                if provider_name:
                    return provider_name

    return None


def _derive_cache_status(
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    cache_status = str(snapshot.get("cache_status") or "").strip()
    if cache_status and cache_status != "未知":
        return cache_status

    trace_id = str(snapshot.get("trace_id") or "").strip()
    if not result_payload and not context_updates and (not trace_id or trace_id.endswith(":no-trace")):
        return "缺失"

    if result_payload or context_updates:
        return "已就绪"

    if trace_id and not trace_id.endswith(":no-trace"):
        return "已缓存"

    return "未知"


def _derive_question_summary(
    question_id: str,
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    humanized = _humanize_question_summary(question_id, result_payload, context_updates)
    if humanized:
        return humanized

    summary_key = QUESTION_TITLES.get(question_id)
    summary_map = context_updates.get("nine_questions")
    if isinstance(summary_map, dict):
        text = str(summary_map.get(summary_key) or "").strip()
        if text:
            return text

    summary = str(snapshot.get("summary") or "").strip()
    if summary:
        return summary

    if result_payload or context_updates:
        return f"{QUESTION_TITLES.get(question_id, question_id)} 已生成"

    return ""


async def build_question_report_summary_items(
    request: Request,
    state: Any,
) -> list[NineQuestionReportItem]:
    """Build the nine-question list view without composing detail payloads."""
    nq_service = _get_nine_question_service(request)
    question_ids = [f"q{i}" for i in range(1, 10)]
    rows_by_question: dict[str, dict[str, Any]] = {}
    get_rows = getattr(nq_service, "get_latest_question_summary_rows", None)
    if callable(get_rows):
        try:
            rows_by_question = await get_rows(question_ids)
        except Exception:
            logger.warning(
                "build_question_report_summary_items: get_latest_question_summary_rows failed",
                exc_info=True,
            )
            rows_by_question = {}
    if not rows_by_question:
        rows_by_question = get_question_snapshot_map(state)

    items: list[NineQuestionReportItem] = []
    for question_id in question_ids:
        row = rows_by_question.get(question_id) or {}
        trace_id = str(row.get("trace_id") or f"{question_id}:no-trace")
        summary = str(row.get("summary") or "").strip()
        cache_status = str(row.get("cache_status") or "").strip()
        if not cache_status or cache_status == "未知":
            if summary:
                cache_status = "已就绪"
            elif trace_id and not trace_id.endswith(":no-trace"):
                cache_status = "已缓存"
            else:
                cache_status = "缺失"

        items.append(NineQuestionReportItem(
            question_id=question_id,
            title=QUESTION_TITLES.get(question_id, question_id),
            tool_id=str(row.get("tool_id") or f"nine_questions.{question_id}"),
            summary=summary,
            confidence=float(row.get("confidence") or 0.0),
            result={},
            context_updates={},
            trace_id=trace_id,
            timestamp=str(row.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            preprocessed_evidence=None,
            inference_result=None,
            q1_llm_upgrade=None,
            cache_status=cache_status,
            provider_name=_derive_provider_name(
                row,
                None,
            ),
            mounted_plugins=ensure_mounted_plugins(
                question_id,
                row.get("mounted_plugins") if isinstance(row.get("mounted_plugins"), list) else [],
            ),
            llm_trace_payload=None,
        ))

    return items


async def build_question_report_items(
    request: Request,
    state: Any,
    include_trace_detail: bool = False,
    question_filter: Optional[str] = None,
) -> list[NineQuestionReportItem]:
    """Build report items for nine questions.

    Reads each question's fully-composed record directly from
    NineQuestionService.get_question_record() (upstream SQLite + filesystem),
    eliminating the old snapshot/context re-projection layer.  The snapshot is
    still fetched for lightweight metadata (trace_id, confidence, timestamp,
    provider_name) that is not part of the composed record.

    Args:
        request: FastAPI request
        state: Current nine-question state (used only for question_filter
               fallback; field reads are now upstream-sourced)
        include_trace_detail: Kept for API compatibility; report data is read from SQLite snapshots.
        question_filter: If set, only return this single question (e.g. 'q1')

    Returns:
        List of NineQuestionReportItem for each requested question
    """
    nq_service = _get_nine_question_service(request)
    question_ids = [question_filter] if question_filter else [f"q{i}" for i in range(1, 10)]
    items = []
    report_refs: dict[str, dict[str, Any]] = {}
    snapshot_map: dict[str, dict[str, Any]] = {}
    get_snapshots = getattr(nq_service, "get_latest_question_snapshots", None)
    if callable(get_snapshots):
        try:
            snapshot_map = await get_snapshots(question_ids)
        except Exception:
            logger.warning(
                "build_question_report_items: get_latest_question_snapshots failed",
                exc_info=True,
            )
            snapshot_map = {}
    if not snapshot_map and question_filter != "q2":
        snapshot_map = get_question_snapshot_map(state)
    records_by_question: dict[str, dict[str, Any]] = {}
    get_records = getattr(nq_service, "get_question_records", None)
    if callable(get_records):
        try:
            records_by_question = await get_records(question_ids)
        except Exception:
            logger.warning(
                "build_question_report_items: get_question_records failed",
                exc_info=True,
            )

    for question_id in question_ids:
        # ── 1. Full composed record from upstream (SQLite → filesystem) ──────
        record = records_by_question.get(question_id)
        if record is None:
            try:
                record = await nq_service.get_question_record(question_id)
            except Exception:
                logger.warning(
                    "build_question_report_items: get_question_record failed for %s",
                    question_id,
                    exc_info=True,
                )
                record = {}

        composed = record.get("composed") if isinstance(record.get("composed"), dict) else {}
        record_trace_payload = composed.get("trace") if isinstance(composed.get("trace"), dict) else {}
        raw_payload = composed.get("raw") if isinstance(composed.get("raw"), dict) else {}
        raw_llm_payload = raw_payload.get("llm_trace_payload") if isinstance(raw_payload.get("llm_trace_payload"), dict) else {}
        raw_context_updates = raw_payload.get("context_updates") if isinstance(raw_payload.get("context_updates"), dict) else {}
        raw_context_llm_payload = (
            raw_context_updates.get("llm_trace_payload")
            if isinstance(raw_context_updates.get("llm_trace_payload"), dict)
            else {}
        )
        result_payload: dict[str, Any] = _compact_report_payload(raw_payload.get("result") or {})
        context_updates: dict[str, Any] = _compact_report_payload(raw_payload.get("context_updates") or {})
        _ensure_legacy_report_aliases(question_id, result_payload, context_updates)
        if question_filter:
            preprocessed_evidence: dict[str, Any] | None = composed.get("evidence") if "evidence" in composed else None
            inference_result: Any = composed.get("inference") if "inference" in composed else None
        else:
            result_payload, context_updates, preprocessed_evidence, inference_result = _project_list_report_payload(
                question_id,
                result_payload,
                context_updates,
            )

        # ── 2. Lightweight snapshot metadata (trace_id / confidence / ts) ────
        snapshot = snapshot_map.get(question_id) or {}
        if not snapshot:
            try:
                snapshot = await nq_service.get_question_snapshot(question_id) or {}
            except Exception:
                logger.warning(
                    "build_question_report_items: get_question_snapshot failed for %s",
                    question_id,
                    exc_info=True,
                )
                snapshot = {}

        trace_id = str(snapshot.get("trace_id") or f"{question_id}:no-trace")

        # ── 3. Trace payload is SQLite-authoritative; transcript memory is not queried here.
        trace_detail: dict[str, Optional[Any]] = None

        # ── 4. Legacy handler projection for non-Q2 single-question pages ─────
        handler = QUESTION_HANDLERS[question_id]
        # Q2 detail is intentionally database-authoritative: missing composed
        # evidence/inference must stay missing instead of being rebuilt from raw
        # result/context payloads.
        allow_single_question_handler_projection = bool(question_filter and question_id != "q2")
        if allow_single_question_handler_projection and not preprocessed_evidence:
            preprocessed_evidence = handler["evidence"](context_updates)
        if allow_single_question_handler_projection and not inference_result:
            inference_result = handler["result"](result_payload)
            if inference_result is None and isinstance(context_updates, dict):
                inference_result = handler["result"](context_updates)
        if question_filter and question_id == "q8":
            inference_result = _enrich_q8_queue_rows_with_task_bindings(
                request,
                trace_id=trace_id,
                inference_result=inference_result,
            )

        if question_id == "q8":
            upstream = _first_present(
                context_updates.get("q8_q1_q7_snapshot"),
                context_updates.get("q1_q7_snapshot"),
                result_payload.get("q1_q7_snapshot"),
            )
            if not isinstance(upstream, dict) or not all(qid in upstream for qid in EXPECTED_QUESTION_IDS[:7]):
                upstream = _build_question_ref_map(report_refs, EXPECTED_QUESTION_IDS[:7])
                result_payload["q1_q7_snapshot"] = upstream
                context_updates["q8_q1_q7_snapshot"] = upstream

        if question_id == "q9":
            upstream = _first_present(
                context_updates.get("q9_q1_q8_snapshot"),
                context_updates.get("q1_q8_snapshot"),
                result_payload.get("q1_q8_snapshot"),
            )
            if not isinstance(upstream, dict) or not all(qid in upstream for qid in EXPECTED_QUESTION_IDS[:8]):
                upstream = _build_question_ref_map(report_refs, EXPECTED_QUESTION_IDS[:8])
                result_payload["q1_q8_snapshot"] = upstream
                context_updates["q9_q1_q8_snapshot"] = upstream

        derived_summary = _derive_question_summary(
            question_id,
            snapshot,
            result_payload,
            context_updates,
        )
        tool_id = str(snapshot.get("tool_id") or f"nine_questions.{question_id}")

        items.append(NineQuestionReportItem(
            question_id=question_id,
            title=QUESTION_TITLES.get(question_id, question_id),
            tool_id=tool_id,
            summary=derived_summary,
            confidence=float(snapshot.get("confidence") or 0.0),
            result=result_payload,
            context_updates=context_updates,
            trace_id=trace_id,
            timestamp=str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            preprocessed_evidence=preprocessed_evidence,
            inference_result=inference_result,
            q1_llm_upgrade=_extract_q1_llm_upgrade(context_updates) if question_id == "q1" else None,
            cache_status=_derive_cache_status(snapshot, result_payload, context_updates),
            provider_name=_derive_provider_name(
                snapshot,
                trace_detail,
                record_trace_payload,
                raw_llm_payload,
                raw_context_llm_payload,
            ),
            mounted_plugins=ensure_mounted_plugins(
                question_id,
                snapshot.get("mounted_plugins") if isinstance(snapshot.get("mounted_plugins"), list) else [],
            ),
            llm_trace_payload=(
                _material_trace_payload(
                    snapshot=snapshot,
                    record_trace_payload=record_trace_payload,
                    raw_llm_payload=raw_llm_payload,
                    raw_context_llm_payload=raw_context_llm_payload,
                )
                if question_filter
                else None
            ),
        ))
        report_refs[question_id] = {
            "question_id": question_id,
            "summary": derived_summary,
            "trace_id": trace_id,
            "tool_id": tool_id,
        }

    return items
