from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from typing import Any

from plugins.nine_questions.llm_output_table import load_question_llm_output_from_table
from zentex.common.storage_paths import get_storage_paths

Q9_LLM_TASK_TABLE = "nine_question_q9_llm_tasks"


def _resolve_q9_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return deepcopy(default)
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return deepcopy(default)


def ensure_q9_llm_task_table(*, db_path: str | Path | None = None) -> Path:
    resolved_db_path = _resolve_q9_state_db_path(db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {Q9_LLM_TASK_TABLE} (
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
                q8_task_json TEXT NOT NULL DEFAULT '{{}}',
                llm_input_json TEXT NOT NULL DEFAULT '{{}}',
                llm_output_json TEXT NOT NULL DEFAULT '{{}}',
                token_usage_json TEXT NOT NULL DEFAULT '{{}}',
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, task_scope, task_index)
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{Q9_LLM_TASK_TABLE}_session_key
            ON {Q9_LLM_TASK_TABLE} (session_id, task_key)
            """
        )
        conn.commit()
    return resolved_db_path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _extract_action_plan(scope: str, llm_output: Any) -> dict[str, Any]:
    if not isinstance(llm_output, dict):
        return {}
    key = "InternalActionPlan" if scope == "internal" else "ExternalActionPlan"
    plan = llm_output.get(key)
    return deepcopy(plan) if isinstance(plan, dict) else {}


def _canonical_task_llm_output(scope: str, llm_output: Any) -> dict[str, Any]:
    if not isinstance(llm_output, dict):
        return {}
    output = deepcopy(llm_output)
    key = "InternalActionPlan" if scope == "internal" else "ExternalActionPlan"
    task_outputs = output.get("task_outputs")
    if isinstance(task_outputs, list) and task_outputs:
        first_output = task_outputs[0] if isinstance(task_outputs[0], dict) else {}
        if not isinstance(output.get(key), dict) and isinstance(first_output.get(key), dict):
            output[key] = deepcopy(first_output[key])
        return output
    plan = output.get(key)
    if isinstance(plan, dict) and plan:
        task_output = deepcopy(output)
        task_output.pop("task_outputs", None)
        output["task_outputs"] = [task_output]
    return output


def _extract_q8_task_from_llm_input(llm_input: Any) -> Any:
    if not isinstance(llm_input, dict):
        return {}
    context = llm_input.get("context")
    context = context if isinstance(context, dict) else {}
    for key in (
        "Q8_Task_Intent_&_Constraints",
        "Q8_Task_Intent_And_Constraints",
        "Q8_Task",
        "q8_task",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            return deepcopy(value)
    return {}


def _task_name_and_description(q8_task: Any, plan: dict[str, Any], *, task_index: int, scope: str) -> tuple[str, str]:
    if isinstance(q8_task, dict):
        name = _text(
            q8_task.get("task_name")
            or q8_task.get("name")
            or q8_task.get("title")
            or q8_task.get("goal")
            or q8_task.get("objective")
            or plan.get("plan_objective")
        )
        description = _text(
            q8_task.get("task_description")
            or q8_task.get("description")
            or q8_task.get("details")
            or q8_task.get("intent")
            or plan.get("plan_objective")
        )
    else:
        name = _text(q8_task) or _text(plan.get("plan_objective"))
        description = _text(q8_task) or _text(plan.get("plan_objective"))
    if not name:
        name = f"Q9 {scope} task {task_index + 1}"
    return name[:240], description[:2000]


def _scope_index_from_module_id(module_id: str) -> tuple[str, int] | None:
    text = _text(module_id)
    prefixes = {
        "q9_internal_task_generation_task_": "internal",
        "q9_external_task_generation_task_": "external",
    }
    for prefix, scope in prefixes.items():
        if not text.startswith(prefix):
            continue
        try:
            return scope, int(text.removeprefix(prefix))
        except ValueError:
            return None
    return None


def _task_from_module_output_row(row: sqlite3.Row, *, include_payloads: bool) -> dict[str, Any] | None:
    parsed = _scope_index_from_module_id(str(row["module_id"]))
    if parsed is None:
        return None
    scope, index = parsed
    output_payload = _json_loads(row["output_json"], {})
    if not isinstance(output_payload, dict):
        return None
    data = output_payload.get("data") if isinstance(output_payload.get("data"), dict) else output_payload
    data = data if isinstance(data, dict) else {}
    llm_input_key = "q9_internal_llm_input" if scope == "internal" else "q9_external_llm_input"
    llm_output_key = "q9_internal_llm_output" if scope == "internal" else "q9_external_llm_output"
    llm_input = data.get(llm_input_key) if isinstance(data.get(llm_input_key), dict) else {}
    canonical_llm_output = _canonical_task_llm_output(scope, data.get(llm_output_key))
    if not llm_input or not canonical_llm_output:
        return None
    plan = _extract_action_plan(scope, canonical_llm_output)
    q8_task = _extract_q8_task_from_llm_input(llm_input)
    task_name, task_description = _task_name_and_description(q8_task, plan, task_index=index, scope=scope)
    item = {
        "session_id": row["session_id"],
        "task_scope": scope,
        "task_index": index,
        "task_key": f"{scope}-{index}",
        "trace_id": _text(output_payload.get("trace_id")),
        "request_id": _text(llm_input.get("request_id")),
        "decision_id": _text(llm_input.get("decision_id")),
        "provider_name": _text(llm_input.get("provider_plugin_id")),
        "model": "",
        "task_name": task_name,
        "task_description": task_description,
        "plan_objective": _text(plan.get("plan_objective")),
        "elapsed_ms": 0,
        "created_at": row["updated_at"],
        "updated_at": row["updated_at"],
    }
    if include_payloads:
        item.update(
            {
                "q8_task": q8_task,
                "llm_input": llm_input,
                "llm_output": canonical_llm_output,
                "token_usage": {},
            }
        )
    return item


def _load_q9_tasks_from_module_outputs(
    *,
    db_path: Path,
    session_id: str,
    include_payloads: bool,
) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, module_id, output_json, updated_at
                FROM nine_question_module_outputs
                WHERE session_id = ?
                  AND question_id = 'q9'
                  AND (
                    module_id LIKE 'q9_internal_task_generation_task_%'
                    OR module_id LIKE 'q9_external_task_generation_task_%'
                  )
                ORDER BY module_id ASC
                """,
                (_text(session_id) or "nq-baseline",),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    tasks = [
        item
        for row in rows
        if (item := _task_from_module_output_row(row, include_payloads=include_payloads)) is not None
    ]
    return sorted(tasks, key=lambda item: (str(item["task_scope"]), int(item["task_index"])))


def persist_q9_llm_task(
    *,
    db_path: str | Path | None = None,
    session_id: str = "nq-baseline",
    task_scope: str,
    task_index: int,
    q8_task: Any,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
    trace_id: str = "",
    provider_name: str = "",
    model: str = "",
    token_usage: dict[str, Any] | None = None,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    scope = _text(task_scope).lower()
    if scope not in {"internal", "external"}:
        raise ValueError(f"invalid q9 llm task scope: {task_scope!r}")
    index = int(task_index)
    task_key = f"{scope}-{index}"
    resolved_db_path = ensure_q9_llm_task_table(db_path=db_path)
    canonical_llm_output = _canonical_task_llm_output(scope, llm_output)
    plan = _extract_action_plan(scope, canonical_llm_output)
    task_name, task_description = _task_name_and_description(q8_task, plan, task_index=index, scope=scope)
    request_id = _text(llm_input.get("request_id"))
    decision_id = _text(llm_input.get("decision_id"))
    provider = _text(provider_name or llm_input.get("provider_plugin_id"))
    usage = token_usage if isinstance(token_usage, dict) else {}
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.execute(
            f"""
            INSERT INTO {Q9_LLM_TASK_TABLE}
            (session_id, task_scope, task_index, task_key, trace_id, request_id, decision_id,
             provider_name, model, task_name, task_description, plan_objective,
             q8_task_json, llm_input_json, llm_output_json, token_usage_json, elapsed_ms,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, task_scope, task_index) DO UPDATE SET
                task_key = excluded.task_key,
                trace_id = excluded.trace_id,
                request_id = excluded.request_id,
                decision_id = excluded.decision_id,
                provider_name = excluded.provider_name,
                model = excluded.model,
                task_name = excluded.task_name,
                task_description = excluded.task_description,
                plan_objective = excluded.plan_objective,
                q8_task_json = excluded.q8_task_json,
                llm_input_json = excluded.llm_input_json,
                llm_output_json = excluded.llm_output_json,
                token_usage_json = excluded.token_usage_json,
                elapsed_ms = excluded.elapsed_ms,
                updated_at = excluded.updated_at
            """,
            (
                _text(session_id) or "nq-baseline",
                scope,
                index,
                task_key,
                _text(trace_id),
                request_id,
                decision_id,
                provider,
                _text(model),
                task_name,
                task_description,
                _text(plan.get("plan_objective")),
                _json_dumps(q8_task),
                _json_dumps(llm_input),
                _json_dumps(canonical_llm_output),
                _json_dumps(usage),
                int(elapsed_ms or 0),
            ),
        )
        conn.commit()
    return {
        "session_id": _text(session_id) or "nq-baseline",
        "task_key": task_key,
        "task_scope": scope,
        "task_index": index,
        "task_name": task_name,
        "task_description": task_description,
        "plan_objective": _text(plan.get("plan_objective")),
    }


def load_q9_llm_tasks(
    *,
    db_path: str | Path | None = None,
    session_id: str = "nq-baseline",
    include_payloads: bool = False,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q9_state_db_path(db_path)
    base_payload = {
        "question_id": "q9",
        "session_id": _text(session_id) or "nq-baseline",
        "source_table": Q9_LLM_TASK_TABLE,
        "task_count": 0,
        "tasks": [],
    }
    if not resolved_db_path.exists():
        return base_payload
    payload_columns = ", q8_task_json, llm_input_json, llm_output_json, token_usage_json" if include_payloads else ""
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT session_id, task_scope, task_index, task_key, trace_id, request_id,
                       decision_id, provider_name, model, task_name, task_description,
                       plan_objective, elapsed_ms, created_at, updated_at
                       {payload_columns}
                FROM {Q9_LLM_TASK_TABLE}
                WHERE session_id = ?
                ORDER BY task_scope ASC, task_index ASC
                """,
                (_text(session_id) or "nq-baseline",),
            ).fetchall()
    except sqlite3.OperationalError:
        fallback_tasks = _load_q9_tasks_from_module_outputs(
            db_path=resolved_db_path,
            session_id=_text(session_id) or "nq-baseline",
            include_payloads=include_payloads,
        )
        return {
            **base_payload,
            "source_table": f"{Q9_LLM_TASK_TABLE}|nine_question_module_outputs",
            "task_count": len(fallback_tasks),
            "tasks": fallback_tasks,
        }
    tasks: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "session_id": row["session_id"],
            "task_scope": row["task_scope"],
            "task_index": int(row["task_index"]),
            "task_key": row["task_key"],
            "trace_id": row["trace_id"],
            "request_id": row["request_id"],
            "decision_id": row["decision_id"],
            "provider_name": row["provider_name"],
            "model": row["model"],
            "task_name": row["task_name"],
            "task_description": row["task_description"],
            "plan_objective": row["plan_objective"],
            "elapsed_ms": int(row["elapsed_ms"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_payloads:
            item.update(
                {
                    "q8_task": _json_loads(row["q8_task_json"], {}),
                    "llm_input": _json_loads(row["llm_input_json"], {}),
                    "llm_output": _canonical_task_llm_output(row["task_scope"], _json_loads(row["llm_output_json"], {})),
                    "token_usage": _json_loads(row["token_usage_json"], {}),
                }
            )
        tasks.append(item)
    if tasks:
        return {**base_payload, "task_count": len(tasks), "tasks": tasks}
    fallback_tasks = _load_q9_tasks_from_module_outputs(
        db_path=resolved_db_path,
        session_id=_text(session_id) or "nq-baseline",
        include_payloads=include_payloads,
    )
    if fallback_tasks:
        return {
            **base_payload,
            "source_table": f"{Q9_LLM_TASK_TABLE}|nine_question_module_outputs",
            "task_count": len(fallback_tasks),
            "tasks": fallback_tasks,
        }
    return base_payload


def load_q9_llm_task_detail(
    *,
    db_path: str | Path | None = None,
    session_id: str = "nq-baseline",
    task_key: str,
) -> dict[str, Any]:
    all_tasks = load_q9_llm_tasks(db_path=db_path, session_id=session_id, include_payloads=True)
    key = _text(task_key)
    for task in all_tasks["tasks"]:
        if task.get("task_key") == key:
            return {
                "question_id": "q9",
                "session_id": all_tasks["session_id"],
                "source_table": all_tasks.get("source_table") or Q9_LLM_TASK_TABLE,
                "task": task,
            }
    raise RuntimeError(f"q9_llm_task_missing:{key}")


def load_llm_output_from_table(*, db_path: str | Path | None = None, session_id: str = "nq-baseline") -> dict[str, Any]:
    llm_output = load_question_llm_output_from_table("q9", db_path=db_path, session_id=session_id)
    for key in (
        "q9_internal_llm_input",
        "q9_internal_llm_output",
        "q9_external_llm_input",
        "q9_external_llm_output",
    ):
        if not isinstance(llm_output.get(key), dict) or not llm_output.get(key):
            raise RuntimeError(f"{key}_missing")
    return llm_output


def _invocation_from_q9_llm_output(
    *,
    scope: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
    trace_id: str,
) -> dict[str, Any]:
    caller_context = llm_input.get("caller_context")
    caller_context = caller_context if isinstance(caller_context, dict) else {}
    provider_name = str(llm_input.get("provider_plugin_id") or "").strip()
    return {
        "trace_id": f"{trace_id}:q9-{scope}" if trace_id else f"q9:{scope}",
        "request_id": str(llm_input.get("request_id") or ""),
        "decision_id": str(llm_input.get("decision_id") or ""),
        "provider_name": provider_name,
        "model": "",
        "system_prompt": str(llm_input.get("system_prompt") or ""),
        "prompt": str(llm_input.get("prompt") or ""),
        "source_module": str(caller_context.get("source_module") or f"q9_how_should_i_act.{scope}_tasks"),
        "invocation_phase": str(caller_context.get("invocation_phase") or f"nine_question_q9_{scope}_task_generation"),
        "question_driver_refs": caller_context.get("question_driver_refs") if isinstance(caller_context.get("question_driver_refs"), list) else [],
        "context_data": llm_input.get("context") if isinstance(llm_input.get("context"), dict) else {},
        "raw_response": llm_output,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "elapsed_ms": 0,
        "error_type": None,
        "error_message": None,
    }


def _invocations_from_q9_scope_output(
    *,
    scope: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
    trace_id: str,
) -> list[dict[str, Any]]:
    raw_inputs = llm_input.get("invocations")
    raw_outputs = llm_output.get("task_outputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        return [
            _invocation_from_q9_llm_output(
                scope=scope,
                llm_input=llm_input,
                llm_output=llm_output,
                trace_id=trace_id,
            )
        ]
    outputs = raw_outputs if isinstance(raw_outputs, list) else []
    invocations: list[dict[str, Any]] = []
    for index, raw_input in enumerate(raw_inputs):
        if not isinstance(raw_input, dict):
            continue
        raw_output = outputs[index] if index < len(outputs) and isinstance(outputs[index], dict) else {}
        invocation = _invocation_from_q9_llm_output(
            scope=scope,
            llm_input=raw_input,
            llm_output=raw_output,
            trace_id=trace_id,
        )
        invocation["q8_task_index"] = index
        invocation["decomposition_mode"] = str(llm_input.get("decomposition_mode") or "")
        invocations.append(invocation)
    return invocations


def build_llm_trace_payload_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = "nq-baseline",
) -> dict[str, Any]:
    llm_output = load_llm_output_from_table(db_path=db_path, session_id=session_id)
    trace_id = str(llm_output.get("trace_id") or "q9:no-trace").strip()
    invocations = [
        * _invocations_from_q9_scope_output(
            scope="internal",
            llm_input=llm_output["q9_internal_llm_input"],
            llm_output=llm_output["q9_internal_llm_output"],
            trace_id=trace_id,
        ),
        * _invocations_from_q9_scope_output(
            scope="external",
            llm_input=llm_output["q9_external_llm_input"],
            llm_output=llm_output["q9_external_llm_output"],
            trace_id=trace_id,
        ),
    ]
    primary = dict(invocations[-1])
    primary["trace_id"] = trace_id
    primary["question_id"] = "q9"
    primary["invocations"] = invocations
    primary["token_usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    primary["elapsed_ms"] = 0
    primary["llm_output_source"] = "plugins.nine_questions.q9_how_should_i_act.llm_output_table.load_llm_output_from_table"
    return primary
