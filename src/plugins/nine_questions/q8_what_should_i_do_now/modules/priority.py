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
    q7 = question_snapshot.get("q7") if isinstance(question_snapshot.get("q7"), dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}

    immediate_tasks: list[str] = []
    blocked_tasks: list[str] = []
    proactive_actions: list[str] = []
    escalation_conditions: list[str] = []

    actionable_space = coerce_string_list(q4.get("actionable_space"))
    fallback_plans = coerce_string_list(q7.get("fallback_plans"))
    resource_gaps = coerce_string_list(q3.get("missing_critical_assets"))
    absolute_red_lines = coerce_string_list(q6.get("absolute_red_lines"))
    forbidden_actions = coerce_string_list(q5.get("explicitly_forbidden_actions"))

    if actionable_space:
        immediate_tasks.extend([f"execute within validated action space: {item}" for item in actionable_space[:3]])
    else:
        immediate_tasks.append("rebuild actionable space evidence before execution")

    if fallback_plans:
        proactive_actions.extend([f"prepare fallback branch: {item}" for item in fallback_plans[:3]])
    if resource_gaps:
        blocked_tasks.extend([f"resolve resource gap: {item}" for item in resource_gaps[:3]])
    escalation_conditions.extend([f"red-line conflict detected: {item}" for item in absolute_red_lines[:3]])
    escalation_conditions.extend([f"forbidden action requested: {item}" for item in forbidden_actions[:3]])

    for status_key, entries in task_state.items():
        for entry in entries[:5]:
            title = normalize_text(entry.get("title"))
            reason = normalize_text(entry.get("reason"))
            if status_key in {"blocked", "waiting", "paused"}:
                blocked_tasks.append(f"{title}: {reason}" if reason else title)
            else:
                immediate_tasks.append(title)

    for item in functional_objectives:
        immediate_tasks.extend(coerce_string_list(item.get("current_phase_tasks"))[:2])
        proactive_actions.extend(coerce_string_list(item.get("priority_order"))[:2])
        escalation_conditions.extend(coerce_string_list(item.get("escalation_conditions"))[:2])

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


def normalize_q8_inference_payload(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    objective_raw = raw.get("objective_profile")
    objective_input = objective_raw if isinstance(objective_raw, dict) else {}
    current_mission = normalize_text(
        objective_input.get("current_mission") or objective_input.get("main_objective")
    )
    derived_capabilities = coerce_string_list(objective_input.get("derived_capabilities"))
    rationale = normalize_text(objective_input.get("rationale"))

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
