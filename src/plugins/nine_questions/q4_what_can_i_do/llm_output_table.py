from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Any

from plugins.nine_questions.llm_output_table import load_question_llm_output_from_table
from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q4_LLM_IO_TABLE = "nine_question_q4_llm_io"
Q4_INFERRED_CAPABILITIES_TABLE = "nine_question_q4_inferred_capabilities"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_q4_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return deepcopy(default)
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return deepcopy(default)


def _coerce_filter_flag(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    text = _text(value).lower()
    if text in {"", "0", "false", "f", "no", "off", "none", "null"}:
        return 0
    if text in {"1", "true", "t", "yes", "on"}:
        return 1
    try:
        return 1 if int(text) > 0 else 0
    except ValueError:
        return 0


def _coerce_filter_reason(value: Any) -> str:
    return _text(value)


def _ensure_q4_inferred_capabilities_columns(*, conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({Q4_INFERRED_CAPABILITIES_TABLE})").fetchall()
    }
    column_alterations: tuple[tuple[str, str], ...] = (
        ("q5_filtered", "INTEGER NOT NULL DEFAULT 0"),
        ("q5_filter_reason", "TEXT NOT NULL DEFAULT ''"),
        ("q6_filtered", "INTEGER NOT NULL DEFAULT 0"),
        ("q6_filter_reason", "TEXT NOT NULL DEFAULT ''"),
        ("q7_filtered", "INTEGER NOT NULL DEFAULT 0"),
        ("q7_filter_reason", "TEXT NOT NULL DEFAULT ''"),
    )
    for column_name, definition in column_alterations:
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {Q4_INFERRED_CAPABILITIES_TABLE} ADD COLUMN {column_name} {definition}"
            )


def ensure_q4_tables(*, db_path: str | Path | None = None) -> Path:
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {Q4_LLM_IO_TABLE} (
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                request_id TEXT NOT NULL DEFAULT '',
                decision_id TEXT NOT NULL DEFAULT '',
                provider_name TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT '',
                error_type TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                internal_llm_input_json TEXT NOT NULL DEFAULT '{{}}',
                internal_llm_output_json TEXT NOT NULL DEFAULT '{{}}',
                external_llm_input_json TEXT NOT NULL DEFAULT '{{}}',
                external_llm_output_json TEXT NOT NULL DEFAULT '{{}}',
                token_usage_json TEXT NOT NULL DEFAULT '{{}}',
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, run_id)
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{Q4_LLM_IO_TABLE}_session
            ON {Q4_LLM_IO_TABLE} (session_id, updated_at, trace_id)
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {Q4_INFERRED_CAPABILITIES_TABLE} (
                session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                capability_index INTEGER NOT NULL,
                capability_name TEXT NOT NULL,
                capability_description TEXT NOT NULL,
                q1_resources_json TEXT NOT NULL DEFAULT '[]',
                q2_capabilities_json TEXT NOT NULL DEFAULT '[]',
                q5_filtered INTEGER NOT NULL DEFAULT 0,
                q5_filter_reason TEXT NOT NULL DEFAULT '',
                q6_filtered INTEGER NOT NULL DEFAULT 0,
                q6_filter_reason TEXT NOT NULL DEFAULT '',
                q7_filtered INTEGER NOT NULL DEFAULT 0,
                q7_filter_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, run_id, capability_index),
                FOREIGN KEY (session_id, run_id)
                    REFERENCES {Q4_LLM_IO_TABLE}(session_id, run_id)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{Q4_INFERRED_CAPABILITIES_TABLE}_run
            ON {Q4_INFERRED_CAPABILITIES_TABLE} (session_id, run_id)
            """
        )
        _ensure_q4_inferred_capabilities_columns(conn=conn)
        conn.commit()
    return resolved_db_path


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = "nq-baseline",
) -> dict[str, Any]:
    return load_question_llm_output_from_table("q4", db_path=db_path, session_id=session_id)


def persist_q4_llm_io(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    run_id: str,
    trace_id: str = "",
    request_id: str = "",
    decision_id: str = "",
    provider_name: str = "",
    model: str = "",
    status: str = "completed",
    attempt_count: int = 0,
    error_type: str = "",
    error_message: str = "",
    internal_llm_input: dict[str, Any] | None = None,
    internal_llm_output: dict[str, Any] | None = None,
    external_llm_input: dict[str, Any] | None = None,
    external_llm_output: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    elapsed_ms: int = 0,
) -> str:
    if not _text(run_id):
        raise ValueError("run_id is required for q4 llm io persistence")

    now = _utc_now_iso()
    resolved_db_path = ensure_q4_tables(db_path=db_path)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.execute(
            f"""
            INSERT INTO {Q4_LLM_IO_TABLE} (
                session_id, run_id, trace_id, request_id, decision_id, provider_name, model,
                attempt_count, status, error_type, error_message,
                internal_llm_input_json, internal_llm_output_json,
                external_llm_input_json, external_llm_output_json,
                token_usage_json, elapsed_ms, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, run_id) DO UPDATE SET
                trace_id = excluded.trace_id,
                request_id = excluded.request_id,
                decision_id = excluded.decision_id,
                provider_name = excluded.provider_name,
                model = excluded.model,
                attempt_count = excluded.attempt_count,
                status = excluded.status,
                error_type = excluded.error_type,
                error_message = excluded.error_message,
                internal_llm_input_json = excluded.internal_llm_input_json,
                internal_llm_output_json = excluded.internal_llm_output_json,
                external_llm_input_json = excluded.external_llm_input_json,
                external_llm_output_json = excluded.external_llm_output_json,
                token_usage_json = excluded.token_usage_json,
                elapsed_ms = excluded.elapsed_ms,
                updated_at = excluded.updated_at
            """,
            (
                _text(session_id) or NQ_BASELINE_SESSION_ID,
                _text(run_id),
                _text(trace_id),
                _text(request_id),
                _text(decision_id),
                _text(provider_name),
                _text(model),
                int(attempt_count or 0),
                _text(status),
                _text(error_type),
                _text(error_message),
                _json_dumps(internal_llm_input or {}),
                _json_dumps(internal_llm_output or {}),
                _json_dumps(external_llm_input or {}),
                _json_dumps(external_llm_output or {}),
                _json_dumps(token_usage or {}),
                int(elapsed_ms or 0),
                now,
                now,
            ),
        )
        conn.commit()
    return _text(run_id)


def persist_q4_inferred_capabilities(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    run_id: str,
    inferred_capabilities: list[dict[str, Any]] | None,
) -> int:
    if not _text(run_id):
        raise ValueError("run_id is required for q4 inferred capability persistence")

    ensure_q4_tables(db_path=db_path)
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    now = _utc_now_iso()
    capabilities = inferred_capabilities or []
    normalized_session_id = _text(session_id) or NQ_BASELINE_SESSION_ID
    normalized_run_id = _text(run_id)
    if not capabilities:
        return 0

    count = 0
    with sqlite3.connect(str(resolved_db_path)) as conn:
        for index, item in enumerate(capabilities):
            source = item if isinstance(item, dict) else {}
            name = _text(source.get("capability_name"))
            description = _text(source.get("capability_description"))
            if not name or not description:
                continue
            resources_bundle = source.get("used_q1_resources_and_q2_capabilities")
            if isinstance(resources_bundle, dict):
                q1_resources = _coerce_string_list(resources_bundle.get("q1_resources"))
                q2_capabilities = _coerce_string_list(resources_bundle.get("q2_capabilities"))
            else:
                q1_resources = _coerce_string_list(source.get("q1_resources"))
                q2_capabilities = _coerce_string_list(source.get("q2_capabilities"))
            conn.execute(
                f"""
                INSERT INTO {Q4_INFERRED_CAPABILITIES_TABLE} (
                    session_id, run_id, capability_index, capability_name,
                    capability_description, q1_resources_json, q2_capabilities_json,
                    q5_filtered, q5_filter_reason, q6_filtered, q6_filter_reason, q7_filtered, q7_filter_reason,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, run_id, capability_index) DO UPDATE SET
                    capability_name = excluded.capability_name,
                    capability_description = excluded.capability_description,
                    q1_resources_json = excluded.q1_resources_json,
                    q2_capabilities_json = excluded.q2_capabilities_json,
                    q5_filtered = excluded.q5_filtered,
                    q5_filter_reason = excluded.q5_filter_reason,
                    q6_filtered = excluded.q6_filtered,
                    q6_filter_reason = excluded.q6_filter_reason,
                    q7_filtered = excluded.q7_filtered,
                    q7_filter_reason = excluded.q7_filter_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_session_id,
                    normalized_run_id,
                    int(index),
                    name,
                    description,
                    _json_dumps(q1_resources),
                    _json_dumps(q2_capabilities),
                    _coerce_filter_flag(
                        source.get("q5_filtered", source.get("q5_filter"))
                    ),
                    _coerce_filter_reason(
                        source.get("q5_filter_reason", source.get("q5_reason"))
                    ),
                    _coerce_filter_flag(
                        source.get("q6_filtered", source.get("q6_filter"))
                    ),
                    _coerce_filter_reason(
                        source.get("q6_filter_reason", source.get("q6_reason"))
                    ),
                    _coerce_filter_flag(
                        source.get("q7_filtered", source.get("q7_filter"))
                    ),
                    _coerce_filter_reason(
                        source.get("q7_filter_reason", source.get("q7_reason"))
                    ),
                    now,
                    now,
                ),
            )
            count += 1
        conn.commit()
    return count


def load_q4_inferred_capabilities(
    *,
    db_path: str | Path | None = None,
    session_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    if not resolved_db_path.exists():
        return []
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT *
                FROM {Q4_INFERRED_CAPABILITIES_TABLE}
                WHERE session_id = ? AND run_id = ?
                ORDER BY capability_index ASC
                """,
                (_text(session_id) or NQ_BASELINE_SESSION_ID, _text(run_id)),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        row_keys = set(row.keys())
        result.append(
            {
                "capability_index": int(row["capability_index"]),
                "capability_name": _text(row["capability_name"]),
                "capability_description": _text(row["capability_description"]),
                "q1_resources": _json_loads(row["q1_resources_json"], []),
                "q2_capabilities": _json_loads(row["q2_capabilities_json"], []),
                "q5_filtered": int(row["q5_filtered"]) if "q5_filtered" in row_keys else 0,
                "q5_filter_reason": _text(row["q5_filter_reason"]) if "q5_filter_reason" in row_keys else "",
                "q6_filtered": int(row["q6_filtered"]) if "q6_filtered" in row_keys else 0,
                "q6_filter_reason": _text(row["q6_filter_reason"]) if "q6_filter_reason" in row_keys else "",
                "q7_filtered": int(row["q7_filtered"]) if "q7_filtered" in row_keys else 0,
                "q7_filter_reason": _text(row["q7_filter_reason"]) if "q7_filter_reason" in row_keys else "",
                "created_at": _text(row["created_at"]),
                "updated_at": _text(row["updated_at"]),
            }
        )
    return result


def _load_latest_q4_inferred_capabilities_by_filter(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    filter_column: str,
    filter_value: int = 0,
) -> list[dict[str, Any]]:
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    if not resolved_db_path.exists():
        return []
    if filter_column not in {"q5_filtered", "q6_filtered", "q7_filtered"}:
        raise ValueError("filter_column must be one of q5_filtered, q6_filtered, q7_filtered")

    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            run_id_row = conn.execute(
                f"""
                SELECT run_id
                FROM {Q4_LLM_IO_TABLE}
                WHERE session_id = ?
                ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
                LIMIT 1
                """,
                (_text(session_id) or NQ_BASELINE_SESSION_ID,),
            ).fetchone()
            if run_id_row is None:
                return []
            run_id = _text(run_id_row["run_id"])

            rows = conn.execute(
                f"""
                SELECT *
                FROM {Q4_INFERRED_CAPABILITIES_TABLE}
                WHERE session_id = ? AND run_id = ? AND {filter_column} = ?
                ORDER BY capability_index ASC
                """,
                (_text(session_id) or NQ_BASELINE_SESSION_ID, run_id, int(filter_value)),
            ).fetchall()
    except sqlite3.OperationalError:
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        row_keys = set(row.keys())
        result.append(
            {
                "capability_index": int(row["capability_index"]),
                "capability_name": _text(row["capability_name"]),
                "capability_description": _text(row["capability_description"]),
                "q1_resources": _json_loads(row["q1_resources_json"], []),
                "q2_capabilities": _json_loads(row["q2_capabilities_json"], []),
                "q5_filtered": int(row["q5_filtered"]) if "q5_filtered" in row_keys else 0,
                "q5_filter_reason": _text(row["q5_filter_reason"]) if "q5_filter_reason" in row_keys else "",
                "q6_filtered": int(row["q6_filtered"]) if "q6_filtered" in row_keys else 0,
                "q6_filter_reason": _text(row["q6_filter_reason"]) if "q6_filter_reason" in row_keys else "",
                "q7_filtered": int(row["q7_filtered"]) if "q7_filtered" in row_keys else 0,
                "q7_filter_reason": _text(row["q7_filter_reason"]) if "q7_filter_reason" in row_keys else "",
                "created_at": _text(row["created_at"]),
                "updated_at": _text(row["updated_at"]),
            }
        )
    return result


def load_q4_internal_inferred_capabilities(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> list[dict[str, Any]]:
    """Return the latest Q4 run's internally unfiltered inferred capabilities."""
    return _load_latest_q4_inferred_capabilities_by_filter(
        db_path=db_path,
        session_id=session_id,
        filter_column="q5_filtered",
        filter_value=0,
    )


def load_q4_external_inferred_capabilities(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> list[dict[str, Any]]:
    """Return the latest Q4 run's externally unfiltered inferred capabilities."""
    return _load_latest_q4_inferred_capabilities_by_filter(
        db_path=db_path,
        session_id=session_id,
        filter_column="q6_filtered",
        filter_value=0,
    )


def load_q4_llm_io_latest(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError("q4_llm_io_table_missing")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT *
                FROM {Q4_LLM_IO_TABLE}
                WHERE session_id = ?
                ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
                LIMIT 1
                """,
                (_text(session_id) or NQ_BASELINE_SESSION_ID,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q4_llm_io_table_missing") from exc
    if row is None:
        raise RuntimeError("q4_llm_io_row_missing")

    run_id = _text(row["run_id"])
    latest: dict[str, Any] = {
        "session_id": _text(row["session_id"]),
        "run_id": run_id,
        "trace_id": _text(row["trace_id"]),
        "request_id": _text(row["request_id"]),
        "decision_id": _text(row["decision_id"]),
        "provider_name": _text(row["provider_name"]),
        "model": _text(row["model"]),
        "attempt_count": int(row["attempt_count"] or 0),
        "status": _text(row["status"]),
        "error_type": _text(row["error_type"]),
        "error_message": _text(row["error_message"]),
        "internal_llm_input": _json_loads(row["internal_llm_input_json"], {}),
        "internal_llm_output": _json_loads(row["internal_llm_output_json"], {}),
        "external_llm_input": _json_loads(row["external_llm_input_json"], {}),
        "external_llm_output": _json_loads(row["external_llm_output_json"], {}),
        "token_usage": _json_loads(row["token_usage_json"], {}),
        "elapsed_ms": int(row["elapsed_ms"] or 0),
        "created_at": _text(row["created_at"]),
        "updated_at": _text(row["updated_at"]),
    }
    latest["capabilities"] = load_q4_inferred_capabilities(
        db_path=resolved_db_path,
        session_id=session_id,
        run_id=run_id,
    )
    return latest
