from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths
from zentex.common.nine_questions_shared import json_safe_payload

NQ_BASELINE_SESSION_ID = "nq-baseline"
_Q8_SCOPE_MODULES = {
    "internal": (
        "q8_internal_task_generation",
        "q8_internal_llm_input",
        "q8_internal_llm_output",
    ),
    "external": (
        "q8_external_task_generation",
        "q8_external_llm_input",
        "q8_external_llm_output",
    ),
}


Q8_SNAPSHOT_TABLE = "nine_question_q8_snapshots"
Q8_OBJECTIVE_LLM_IO_TABLE = "nine_question_q8_objective_llm_io"


def _resolve_q8_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    raise RuntimeError("q8_combined_llm_output_forbidden")


def _load_scoped_llm_io_from_module_table(
    *,
    scope: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q8_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q8_module_output_table_missing: {resolved_db_path}")
    module_id, input_key, output_key = _Q8_SCOPE_MODULES[scope]
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT output_json
                FROM nine_question_module_outputs
                WHERE session_id = ? AND question_id = 'q8' AND module_id = ?
                """,
                (session_id, module_id),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q8_module_output_table_missing") from exc
    if row is None:
        raise RuntimeError(f"q8_{scope}_module_output_row_missing")
    try:
        module_output = json.loads(str(row["output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"q8_{scope}_module_output_json_invalid") from exc
    if not isinstance(module_output, dict):
        raise RuntimeError(f"q8_{scope}_module_output_json_not_object")
    data = module_output.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"q8_{scope}_module_output_data_missing")
    llm_input = data.get(input_key)
    llm_output = data.get(output_key)
    if not isinstance(llm_input, dict) or not llm_input:
        raise RuntimeError(f"{input_key}_missing")
    if not isinstance(llm_output, dict) or not llm_output:
        raise RuntimeError(f"{output_key}_missing")
    return deepcopy(
        {
            input_key: llm_input,
            output_key: llm_output,
        }
    )


def load_internal_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    objective_rows = load_q8_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane="internal")
    if objective_rows:
        return _load_objective_aggregate_llm_io(lane="internal", rows=objective_rows)
    return _load_scoped_llm_io_from_module_table(scope="internal", db_path=db_path, session_id=session_id)


def load_external_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    objective_rows = load_q8_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane="external")
    if objective_rows:
        return _load_objective_aggregate_llm_io(lane="external", rows=objective_rows)
    return _load_scoped_llm_io_from_module_table(scope="external", db_path=db_path, session_id=session_id)


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    objective_rows = load_q8_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane="internal")
    if not objective_rows:
        raise RuntimeError("q8_internal_public_output_missing")
    task_result = _aggregate_objective_task_result(lane="internal", rows=objective_rows)
    q7_public_output = _load_q7_public_output(lane="internal", db_path=db_path, session_id=session_id)
    return _build_q8_branch_public_output(
        scope="internal",
        task_result=task_result,
        upstream_q7_public_output=q7_public_output,
    )


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    objective_rows = load_q8_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane="external")
    if not objective_rows:
        raise RuntimeError("q8_external_public_output_missing")
    task_result = _aggregate_objective_task_result(lane="external", rows=objective_rows)
    q7_public_output = _load_q7_public_output(lane="external", db_path=db_path, session_id=session_id)
    return _build_q8_branch_public_output(
        scope="external",
        task_result=task_result,
        upstream_q7_public_output=q7_public_output,
    )


def save_q8_objective_llm_io_to_table(
    *,
    db_path: str | Path | None = None,
    session_id: str,
    lane: str,
    objective_number: str,
    llm_input: dict[str, Any],
    output_payload: dict[str, Any],
    task_profile: dict[str, Any],
) -> None:
    normalized_lane = str(lane or "").strip().lower()
    normalized_objective_number = str(objective_number or "").strip()
    if normalized_lane not in {"internal", "external"}:
        raise RuntimeError(f"q8_objective_llm_io_invalid_lane:{lane}")
    if not normalized_objective_number:
        raise RuntimeError("q8_objective_llm_io_objective_number_missing")
    now = datetime.now(timezone.utc).isoformat()
    resolved_db_path = _resolve_q8_state_db_path(db_path)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_q8_objective_llm_io_table(conn)
        row = conn.execute(
            f"""
            SELECT created_at
            FROM {Q8_OBJECTIVE_LLM_IO_TABLE}
            WHERE session_id = ? AND lane = ? AND objective_number = ?
            """,
            (session_id, normalized_lane, normalized_objective_number),
        ).fetchone()
        created_at = str(row["created_at"]) if row is not None else now
        conn.execute(
            f"""
            INSERT INTO {Q8_OBJECTIVE_LLM_IO_TABLE}
                (session_id, lane, objective_number,
                 llm_input_json, llm_output_json, task_profile_json,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, lane, objective_number) DO UPDATE SET
                llm_input_json = excluded.llm_input_json,
                llm_output_json = excluded.llm_output_json,
                task_profile_json = excluded.task_profile_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                normalized_lane,
                normalized_objective_number,
                json.dumps(json_safe_payload(llm_input), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(output_payload), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(task_profile), ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )


def load_q8_objective_llm_io_rows_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    lane: str | None = None,
) -> list[dict[str, Any]]:
    resolved_db_path = _resolve_q8_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q8_objective_llm_io_table_missing: {resolved_db_path}")
    normalized_lane = str(lane or "").strip().lower()
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            _ensure_q8_objective_llm_io_table(conn)
            if normalized_lane:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           task_profile_json, updated_at
                    FROM {Q8_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ? AND lane = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id, normalized_lane),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           task_profile_json, updated_at
                    FROM {Q8_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("q8_objective_llm_io_table_missing") from exc
    return [_decode_q8_objective_llm_io_row(row) for row in rows]


def _ensure_q8_objective_llm_io_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {Q8_OBJECTIVE_LLM_IO_TABLE} (
            session_id TEXT NOT NULL,
            lane TEXT NOT NULL,
            objective_number TEXT NOT NULL,
            llm_input_json TEXT NOT NULL DEFAULT '{{}}',
            llm_output_json TEXT NOT NULL DEFAULT '{{}}',
            task_profile_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, lane, objective_number)
        )
        """
    )


def _decode_q8_objective_llm_io_row(row: sqlite3.Row) -> dict[str, Any]:
    def _loads(field: str) -> dict[str, Any]:
        try:
            value = json.loads(str(row[field] or "{}"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"q8_objective_llm_io_json_invalid:{field}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"q8_objective_llm_io_json_not_object:{field}")
        return value

    return {
        "lane": str(row["lane"] or ""),
        "objective_number": str(row["objective_number"] or ""),
        "llm_input": _loads("llm_input_json"),
        "llm_output": _loads("llm_output_json"),
        "task_profile": _loads("task_profile_json"),
        "updated_at": str(row["updated_at"] or ""),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _merge_string_lists(*values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for items in values:
        for item in items:
            text = _text(item)
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def _merge_inference_payloads(rows: list[dict[str, Any]]) -> dict[str, Any]:
    objective: dict[str, Any] = {
        "current_mission": "",
        "mission_rationale": "",
        "primary_objectives": [],
        "secondary_objectives": [],
        "completion_conditions": [],
        "pause_conditions": [],
        "escalation_conditions": [],
        "current_phase_tasks": [],
        "priority_order": [],
    }
    queue: dict[str, list[Any]] = {
        "next_self_tasks": [],
        "blocked_self_tasks": [],
        "proactive_actions": [],
    }
    for row in rows:
        profile = _dict(row.get("task_profile"))
        payload = _dict(profile.get("inference_payload"))
        if not payload:
            payload = _dict(row.get("llm_output"))
        item_objective = _dict(payload.get("objective_profile"))
        for key in (
            "primary_objectives",
            "secondary_objectives",
            "completion_conditions",
            "pause_conditions",
            "escalation_conditions",
            "current_phase_tasks",
            "priority_order",
        ):
            objective[key] = _merge_string_lists(
                list(objective.get(key) or []),
                _string_list(item_objective.get(key)),
            )
        if not objective.get("current_mission"):
            objective["current_mission"] = _text(item_objective.get("current_mission"))
        if not objective.get("mission_rationale"):
            objective["mission_rationale"] = _text(item_objective.get("mission_rationale"))
        item_queue = _dict(payload.get("task_queue"))
        for key in queue:
            queue[key].extend(_list(item_queue.get(key)))
    return {"objective_profile": objective, "task_queue": queue}


def _row_tasks(row: dict[str, Any]) -> list[dict[str, Any]]:
    profile = _dict(row.get("task_profile"))
    tasks = _list(profile.get("tasks"))
    if not tasks:
        tasks = _list(_dict(profile.get("task_plan")).get("generated"))
    objective_number = _text(row.get("objective_number"))
    normalized: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        task = deepcopy(item)
        if objective_number and not _text(task.get("objective_number") or task.get("target_id")):
            task["objective_number"] = objective_number
        normalized.append(task)
    return normalized


def _aggregate_objective_task_result(*, lane: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise RuntimeError(f"q8_{lane}_objective_llm_io_rows_missing")
    tasks: list[dict[str, Any]] = []
    objective_requests: list[dict[str, Any]] = []
    objective_results: list[dict[str, Any]] = []
    for row in rows:
        objective_number = _text(row.get("objective_number"))
        if not objective_number:
            raise RuntimeError(f"q8_{lane}_objective_number_missing")
        tasks.extend(_row_tasks(row))
        objective_requests.append(
            {
                "objective_number": objective_number,
                "llm_input": deepcopy(_dict(row.get("llm_input"))),
            }
        )
        objective_results.append(
            {
                "objective_number": objective_number,
                "llm_output": deepcopy(_dict(row.get("llm_output"))),
            }
        )
    title = "InternalObjectiveProfileBatch" if lane == "internal" else "ExternalObjectiveProfileBatch"
    planner = "q8_internal_task_generation" if lane == "internal" else "q8_external_task_generation"
    return {
        "scope": lane,
        "tasks": tasks,
        "inference_payload": _merge_inference_payloads(rows),
        "llm_input": {
            "type": f"Q8{title.replace('ProfileBatch', 'RequestBatch')}",
            "scope": lane,
            "objective_requests": objective_requests,
        },
        "llm_output": {
            "type": f"Q8{title}",
            "objective_results": objective_results,
        },
        "task_plan": {
            "generated": tasks,
            "planner": planner,
        },
    }


def _load_objective_aggregate_llm_io(*, lane: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    task_result = _aggregate_objective_task_result(lane=lane, rows=rows)
    input_key = "q8_internal_llm_input" if lane == "internal" else "q8_external_llm_input"
    output_key = "q8_internal_llm_output" if lane == "internal" else "q8_external_llm_output"
    return {
        input_key: deepcopy(task_result["llm_input"]),
        output_key: deepcopy(task_result["llm_output"]),
    }


def _public_task_rows(value: Any) -> list[dict[str, Any]]:
    allowed_keys = {
        "task_id",
        "title",
        "status",
        "scope",
        "source_question",
        "source_objective",
        "objective_number",
        "executor_type",
        "target_id",
        "required_capability",
        "creation_rationale",
        "task_goal",
        "completion_condition",
        "metadata",
    }
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else []):
        if not isinstance(item, dict):
            title = _text(item)
            if title:
                rows.append({"task_id": f"q8-task-{index}", "title": title})
            continue
        title = _text(item.get("title") or item.get("task") or item.get("intent_name") or item.get("objective"))
        if not title:
            continue
        row = {
            str(key): json_safe_payload(val)
            for key, val in item.items()
            if key in allowed_keys and val not in (None, "", [], {})
        }
        row["title"] = title
        row.setdefault("task_id", _text(item.get("task_id") or item.get("id") or f"q8-task-{index}"))
        rows.append(row)
    return rows


def _public_task_queue(value: Any) -> dict[str, list[dict[str, Any]]]:
    queue = _dict(value)
    return {
        "next_self_tasks": _public_task_rows(queue.get("next_self_tasks")),
        "blocked_self_tasks": _public_task_rows(queue.get("blocked_self_tasks")),
        "proactive_actions": _public_task_rows(queue.get("proactive_actions")),
    }


def _public_objective_profile(value: Any) -> dict[str, Any]:
    objective = _dict(value)
    return {
        "current_mission": _text(objective.get("current_mission") or objective.get("current_primary_objective")),
        "mission_rationale": _text(objective.get("mission_rationale")),
        "primary_objectives": _string_list(objective.get("primary_objectives")),
        "secondary_objectives": _string_list(objective.get("secondary_objectives")),
        "completion_conditions": _string_list(objective.get("completion_conditions")),
        "pause_conditions": _string_list(objective.get("pause_conditions")),
        "escalation_conditions": _string_list(objective.get("escalation_conditions")),
        "current_phase_tasks": _string_list(objective.get("current_phase_tasks")),
        "priority_order": _string_list(objective.get("priority_order")),
    }


def _merge_rows_with_upstream(rows: list[dict[str, Any]], upstream_public_output: dict[str, Any]) -> list[dict[str, Any]]:
    upstream_items = _list(upstream_public_output.get("creative_possibilities"))
    upstream_map = {
        _text(item.get("objective_number")): item
        for item in upstream_items
        if isinstance(item, dict) and _text(item.get("objective_number"))
    }
    merged: list[dict[str, Any]] = []
    for row in rows:
        objective_number = _text(row.get("objective_number") or row.get("target_id"))
        if objective_number and objective_number in upstream_map:
            merged.append({**deepcopy(upstream_map[objective_number]), **row})
        else:
            merged.append(row)
    return merged


def _build_q8_branch_public_output(
    *,
    scope: str,
    task_result: dict[str, Any],
    upstream_q7_public_output: dict[str, Any],
) -> dict[str, Any]:
    inference_payload = _dict(task_result.get("inference_payload"))
    objective_profile = _public_objective_profile(inference_payload.get("objective_profile"))
    task_queue = _public_task_queue(inference_payload.get("task_queue"))
    task_plan = _dict(task_result.get("task_plan"))
    generated = _public_task_rows(task_plan.get("generated") or task_result.get("tasks"))
    upstream_public = _dict(upstream_q7_public_output)
    if not upstream_public:
        raise RuntimeError(f"q8_{scope}_upstream_q7_public_output_missing")
    generated = _merge_rows_with_upstream(generated, upstream_public)
    public_output = {
        "scope": scope,
        "objective_profile": objective_profile,
        "task_queue": task_queue,
        "task_plan": {
            "planner": _text(task_plan.get("planner")) or f"q8_{scope}_task_generation",
            "generated": generated,
        },
        "upstream_q7_public_output": deepcopy(upstream_public),
    }
    meaningful = (
        objective_profile.get("current_mission")
        or objective_profile.get("primary_objectives")
        or objective_profile.get("priority_order")
        or generated
        or any(task_queue.values())
    )
    if not meaningful:
        raise RuntimeError(f"q8_{scope}_public_output_empty")
    return public_output


def _load_q7_public_output(
    *,
    lane: str,
    db_path: str | Path | None,
    session_id: str,
) -> dict[str, Any]:
    if lane == "internal":
        from plugins.nine_questions.q7_what_else_can_i_do.service import (
            load_internal_public_output as load_q7_public_output,
        )
    elif lane == "external":
        from plugins.nine_questions.q7_what_else_can_i_do.service import (
            load_external_public_output as load_q7_public_output,
        )
    else:
        raise RuntimeError(f"q8_objective_llm_io_invalid_lane:{lane}")
    return load_q7_public_output(db_path=db_path, session_id=session_id)
