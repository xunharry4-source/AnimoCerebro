from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q9_SNAPSHOT_TABLE = "nine_question_q9_snapshots"
Q9_REQUIRED_LLM_FIELDS = (
    "q9_internal_llm_input",
    "q9_internal_llm_output",
    "q9_external_llm_input",
    "q9_external_llm_output",
)


def _resolve_q9_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q9_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q9_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q9_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q9_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q9_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q9_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q9_llm_output_json_not_object")
    for field in Q9_REQUIRED_LLM_FIELDS:
        if not isinstance(llm_output.get(field), dict) or not llm_output.get(field):
            raise RuntimeError(f"{field}_missing")
    return deepcopy(llm_output)


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return deepcopy(load_llm_output_from_table(db_path=db_path, session_id=session_id)["q9_internal_llm_output"])


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return deepcopy(load_llm_output_from_table(db_path=db_path, session_id=session_id)["q9_external_llm_output"])


def build_llm_trace_payload_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = load_llm_output_from_table(db_path=db_path, session_id=session_id)
    invocations: list[dict[str, Any]] = []
    for phase, input_key, output_key in (
        ("internal", "q9_internal_llm_input", "q9_internal_llm_output"),
        ("external", "q9_external_llm_input", "q9_external_llm_output"),
    ):
        llm_input = deepcopy(llm_output[input_key])
        invocation = {
            "invocation_phase": llm_input.get("caller_context", {}).get("invocation_phase")
            or f"nine_question_q9_{phase}_task_generation",
            "provider_name": llm_input.get("provider_plugin_id") or llm_input.get("provider_name") or "",
            "model": llm_input.get("model") or "",
            "request_id": llm_input.get("request_id") or "",
            "decision_id": llm_input.get("decision_id") or "",
            "system_prompt": llm_input.get("system_prompt") or "",
            "prompt": llm_input.get("prompt") or "",
            "context_data": deepcopy(llm_input.get("context") or {}),
            "raw_response": deepcopy(llm_output[output_key]),
        }
        invocations.append(invocation)
    return {
        "llm_output_source": "plugins.nine_questions.q9_how_should_i_act.llm_output_table.load_llm_output_from_table",
        "trace_id": llm_output.get("trace_id") or "",
        "invocations": invocations,
        "raw_response": deepcopy(llm_output["q9_external_llm_output"]),
    }


def _ensure_q9_task_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nine_question_q9_llm_tasks (
            session_id TEXT NOT NULL,
            task_scope TEXT NOT NULL,
            task_index INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            decision_id TEXT NOT NULL DEFAULT '',
            provider_name TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            task_name TEXT NOT NULL DEFAULT '',
            task_description TEXT NOT NULL DEFAULT '',
            plan_objective TEXT NOT NULL DEFAULT '',
            q8_task_json TEXT NOT NULL DEFAULT '{}',
            llm_input_json TEXT NOT NULL DEFAULT '{}',
            llm_output_json TEXT NOT NULL DEFAULT '{}',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, task_scope, task_index)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_nine_question_q9_llm_tasks_session_key
        ON nine_question_q9_llm_tasks (session_id, task_key)
        """
    )


def _task_scope_from_key(task_scope: str) -> str:
    scope = str(task_scope or "").strip().lower()
    if scope not in {"internal", "external"}:
        raise RuntimeError(f"q9_llm_task_scope_invalid:{task_scope}")
    return scope


def _plan_objective(llm_output: dict[str, Any], scope: str) -> str:
    plan_key = "InternalActionPlan" if scope == "internal" else "ExternalActionPlan"
    plan = llm_output.get(plan_key) if isinstance(llm_output.get(plan_key), dict) else {}
    if not plan and isinstance(llm_output.get("ActionPlan"), dict):
        plan = llm_output["ActionPlan"]
    return str(plan.get("plan_objective") or plan.get("objective") or "").strip()


def _task_name(q8_task: dict[str, Any], *, scope: str, index: int) -> str:
    return str(
        q8_task.get("task_name")
        or q8_task.get("intent_name")
        or q8_task.get("name")
        or f"Q9 {scope} task {index}"
    ).strip()


def _task_description(q8_task: dict[str, Any]) -> str:
    return str(
        q8_task.get("task_description")
        or q8_task.get("intent_description")
        or q8_task.get("description")
        or q8_task.get("intent_objective")
        or ""
    ).strip()


def _json_load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return deepcopy(parsed) if isinstance(parsed, dict) else {}


def _normalized_q9_task_output(llm_output: dict[str, Any], *, scope: str) -> dict[str, Any]:
    payload = deepcopy(llm_output)
    if scope == "external" and isinstance(payload.get("ActionPlan"), dict) and not isinstance(payload.get("ExternalActionPlan"), dict):
        payload["ExternalActionPlan"] = deepcopy(payload["ActionPlan"])
    if scope == "internal" and isinstance(payload.get("ActionPlan"), dict) and not isinstance(payload.get("InternalActionPlan"), dict):
        payload["InternalActionPlan"] = deepcopy(payload["ActionPlan"])
    return payload


def _with_task_outputs(llm_output: dict[str, Any], *, scope: str) -> dict[str, Any]:
    payload = _normalized_q9_task_output(llm_output, scope=scope)
    if not isinstance(payload.get("task_outputs"), list):
        payload["task_outputs"] = [deepcopy(payload)]
    return payload


def persist_q9_llm_task(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    task_scope: str,
    task_index: int,
    q8_task: dict[str, Any],
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
    trace_id: str = "",
    provider_name: str = "",
    model: str = "",
    token_usage: dict[str, Any] | None = None,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    scope = _task_scope_from_key(task_scope)
    index = int(task_index)
    task_key = f"{scope}-{index}"
    resolved_db_path = _resolve_q9_state_db_path(db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    task_name = _task_name(q8_task, scope=scope, index=index)
    task_description = _task_description(q8_task)
    plan_objective = _plan_objective(llm_output, scope)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        _ensure_q9_task_table(conn)
        conn.execute(
            """
            INSERT INTO nine_question_q9_llm_tasks (
                session_id, task_scope, task_index, task_key, trace_id, request_id,
                decision_id, provider_name, model, task_name, task_description,
                plan_objective, q8_task_json, llm_input_json, llm_output_json,
                token_usage_json, elapsed_ms, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, task_scope, task_index) DO UPDATE SET
                task_key=excluded.task_key,
                trace_id=excluded.trace_id,
                request_id=excluded.request_id,
                decision_id=excluded.decision_id,
                provider_name=excluded.provider_name,
                model=excluded.model,
                task_name=excluded.task_name,
                task_description=excluded.task_description,
                plan_objective=excluded.plan_objective,
                q8_task_json=excluded.q8_task_json,
                llm_input_json=excluded.llm_input_json,
                llm_output_json=excluded.llm_output_json,
                token_usage_json=excluded.token_usage_json,
                elapsed_ms=excluded.elapsed_ms,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                session_id,
                scope,
                index,
                task_key,
                trace_id,
                str(llm_input.get("request_id") or ""),
                str(llm_input.get("decision_id") or ""),
                provider_name,
                model,
                task_name,
                task_description,
                plan_objective,
                json.dumps(q8_task, ensure_ascii=False, sort_keys=True),
                json.dumps(llm_input, ensure_ascii=False, sort_keys=True),
                json.dumps(llm_output, ensure_ascii=False, sort_keys=True),
                json.dumps(token_usage or {}, ensure_ascii=False, sort_keys=True),
                int(elapsed_ms or 0),
            ),
        )
        conn.commit()
    return {
        "session_id": session_id,
        "task_scope": scope,
        "task_index": index,
        "task_key": task_key,
        "task_name": task_name,
        "task_description": task_description,
        "plan_objective": plan_objective,
    }


def _row_to_task(row: sqlite3.Row, *, include_payloads: bool) -> dict[str, Any]:
    task = {
        "session_id": str(row["session_id"] or ""),
        "task_scope": str(row["task_scope"] or ""),
        "task_index": int(row["task_index"]),
        "task_key": str(row["task_key"] or ""),
        "trace_id": str(row["trace_id"] or ""),
        "request_id": str(row["request_id"] or ""),
        "decision_id": str(row["decision_id"] or ""),
        "provider_name": str(row["provider_name"] or ""),
        "model": str(row["model"] or ""),
        "task_name": str(row["task_name"] or ""),
        "task_description": str(row["task_description"] or ""),
        "plan_objective": str(row["plan_objective"] or ""),
        "q8_task": _json_load(row["q8_task_json"]),
        "token_usage": _json_load(row["token_usage_json"]),
        "elapsed_ms": int(row["elapsed_ms"] or 0),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }
    if include_payloads:
        task["llm_input"] = _json_load(row["llm_input_json"])
        task["llm_output"] = _with_task_outputs(_json_load(row["llm_output_json"]), scope=task["task_scope"])
    return task


def _load_dedicated_q9_tasks(
    *,
    conn: sqlite3.Connection,
    session_id: str,
    include_payloads: bool,
) -> list[dict[str, Any]]:
    _ensure_q9_task_table(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM nine_question_q9_llm_tasks
        WHERE session_id = ?
        ORDER BY task_scope ASC, task_index ASC
        """,
        (session_id,),
    ).fetchall()
    return [_row_to_task(row, include_payloads=include_payloads) for row in rows]


def _scope_and_index_from_module_id(module_id: str) -> tuple[str, int] | None:
    text = str(module_id or "")
    if "q9_internal" in text:
        scope = "internal"
    elif "q9_external" in text:
        scope = "external"
    else:
        return None
    digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
    index = int(digits[-1]) if digits else 0
    return scope, index


def _fallback_q8_task(llm_input: dict[str, Any]) -> dict[str, Any]:
    context = llm_input.get("context") if isinstance(llm_input.get("context"), dict) else {}
    for key in ("Q8_Task_Intent_&_Constraints", "selected_external_task", "q8_task"):
        value = context.get(key)
        if isinstance(value, dict):
            return deepcopy(value)
    q8_tasks = context.get("Q8_Tasks")
    if isinstance(q8_tasks, list) and q8_tasks and isinstance(q8_tasks[0], dict):
        return deepcopy(q8_tasks[0])
    return {}


def _load_fallback_module_output_tasks(
    *,
    conn: sqlite3.Connection,
    session_id: str,
    include_payloads: bool,
) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT module_id, output_json, updated_at
            FROM nine_question_module_outputs
            WHERE session_id = ? AND question_id = 'q9'
            ORDER BY module_id ASC
            """,
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    tasks: list[dict[str, Any]] = []
    for row in rows:
        scope_index = _scope_and_index_from_module_id(str(row["module_id"] or ""))
        if scope_index is None:
            continue
        scope, index = scope_index
        payload = _json_load(row["output_json"])
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        input_key = "q9_internal_llm_input" if scope == "internal" else "q9_external_llm_input"
        output_key = "q9_internal_llm_output" if scope == "internal" else "q9_external_llm_output"
        llm_input = _json_load(data.get(input_key)) if isinstance(data, dict) else {}
        llm_output = _json_load(data.get(output_key)) if isinstance(data, dict) else {}
        if not llm_output:
            continue
        q8_task = _fallback_q8_task(llm_input)
        task = {
            "session_id": session_id,
            "task_scope": scope,
            "task_index": index,
            "task_key": f"{scope}-{index}",
            "trace_id": str(payload.get("trace_id") or ""),
            "request_id": str(llm_input.get("request_id") or ""),
            "decision_id": str(llm_input.get("decision_id") or ""),
            "provider_name": str(llm_input.get("provider_plugin_id") or llm_input.get("provider_name") or ""),
            "model": str(llm_input.get("model") or ""),
            "task_name": _task_name(q8_task, scope=scope, index=index),
            "task_description": _task_description(q8_task),
            "plan_objective": _plan_objective(llm_output, scope),
            "q8_task": q8_task,
            "token_usage": _json_load(data.get("token_usage")) if isinstance(data, dict) else {},
            "elapsed_ms": int(data.get("elapsed_ms") or 0) if isinstance(data, dict) else 0,
            "created_at": str(row["updated_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        if include_payloads:
            task["llm_input"] = llm_input
            task["llm_output"] = _with_task_outputs(llm_output, scope=scope)
        tasks.append(task)
    return tasks


def load_q9_llm_tasks(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    include_payloads: bool = False,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q9_state_db_path(db_path)
    if not resolved_db_path.exists():
        return {"source_table": "nine_question_q9_llm_tasks", "session_id": session_id, "task_count": 0, "tasks": []}
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        tasks = _load_dedicated_q9_tasks(conn=conn, session_id=session_id, include_payloads=include_payloads)
        source_table = "nine_question_q9_llm_tasks"
        if not tasks:
            tasks = _load_fallback_module_output_tasks(conn=conn, session_id=session_id, include_payloads=include_payloads)
            if tasks:
                source_table = "nine_question_q9_llm_tasks|nine_question_module_outputs"
    return {
        "source_table": source_table,
        "question_id": "q9",
        "session_id": session_id,
        "task_count": len(tasks),
        "tasks": tasks,
    }


def load_q9_llm_task_detail(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    task_key: str,
) -> dict[str, Any]:
    payload = load_q9_llm_tasks(db_path=db_path, session_id=session_id, include_payloads=True)
    for task in payload["tasks"]:
        if task.get("task_key") == task_key:
            return {
                "source_table": payload["source_table"],
                "question_id": "q9",
                "session_id": session_id,
                "task_key": task_key,
                "task": task,
            }
    raise RuntimeError(f"q9_llm_task_missing:{session_id}:{task_key}")


__all__ = [
    "build_llm_trace_payload_from_table",
    "load_external_llm_output_from_table",
    "load_internal_llm_output_from_table",
    "load_llm_output_from_table",
    "load_q9_llm_task_detail",
    "load_q9_llm_tasks",
    "persist_q9_llm_task",
]
