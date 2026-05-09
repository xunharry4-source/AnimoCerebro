from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zentex.common.nine_questions_shared import json_safe_payload
from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q6_MODULE_OUTPUTS_TABLE = "nine_question_module_outputs"
Q6_INTERNAL_INPUT_MODULE_ID = "q6_internal_llm_request"
Q6_INTERNAL_OUTPUT_MODULE_ID = "q6_internal_consequence_llm"
Q6_EXTERNAL_INPUT_MODULE_ID = "q6_external_llm_request"
Q6_EXTERNAL_OUTPUT_MODULE_ID = "q6_external_consequence_llm"


Q6_SNAPSHOT_TABLE = "nine_question_q6_snapshots"
Q6_OBJECTIVE_LLM_IO_TABLE = "nine_question_q6_objective_llm_io"


def _resolve_q6_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q6_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q6_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q6_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q6_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q6_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q6_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q6_llm_output_json_not_object")
    return llm_output


def save_q6_llm_io_to_table(
    *,
    db_path: str | Path | None = None,
    session_id: str,
    llm_input_field: str,
    llm_input: dict[str, Any],
    llm_output_field: str | None = None,
    llm_output: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    resolved_db_path = _resolve_q6_state_db_path(db_path)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT llm_output_json, created_at FROM {Q6_SNAPSHOT_TABLE} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        payload: dict[str, Any] = {}
        created_at = now
        if row is not None:
            created_at = str(row["created_at"] or now)
            try:
                loaded = json.loads(str(row["llm_output_json"] or "{}"))
            except json.JSONDecodeError:
                loaded = {}
            if isinstance(loaded, dict):
                payload = loaded
        payload[llm_input_field] = json_safe_payload(llm_input)
        if llm_output_field:
            if llm_output is None:
                payload.pop(llm_output_field, None)
            else:
                payload[llm_output_field] = json_safe_payload(llm_output)
        conn.execute(
            f"""
            INSERT INTO {Q6_SNAPSHOT_TABLE}
                (session_id, schema_version, record_version, snapshot_schema_version,
                 snapshot_json, llm_output_json, llm_trace_json, result_json,
                 context_updates_json, created_at, updated_at)
            VALUES (?, 1, 1, 1, '{{}}', ?, '{{}}', '{{}}', '{{}}', ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                record_version = record_version + 1,
                llm_output_json = excluded.llm_output_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )


def save_q6_objective_llm_io_to_table(
    *,
    db_path: str | Path | None = None,
    session_id: str,
    lane: str,
    objective_number: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
    consequence_profile: dict[str, Any],
) -> None:
    normalized_lane = str(lane or "").strip().lower()
    normalized_objective_number = str(objective_number or "").strip()
    if normalized_lane not in {"internal", "external"}:
        raise RuntimeError(f"q6_objective_llm_io_invalid_lane:{lane}")
    if not normalized_objective_number:
        raise RuntimeError("q6_objective_llm_io_objective_number_missing")
    now = datetime.now(timezone.utc).isoformat()
    resolved_db_path = _resolve_q6_state_db_path(db_path)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_q6_objective_llm_io_table(conn)
        row = conn.execute(
            f"""
            SELECT created_at
            FROM {Q6_OBJECTIVE_LLM_IO_TABLE}
            WHERE session_id = ? AND lane = ? AND objective_number = ?
            """,
            (session_id, normalized_lane, normalized_objective_number),
        ).fetchone()
        created_at = str(row["created_at"]) if row is not None else now
        conn.execute(
            f"""
            INSERT INTO {Q6_OBJECTIVE_LLM_IO_TABLE}
                (session_id, lane, objective_number,
                 llm_input_json, llm_output_json, consequence_profile_json,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, lane, objective_number) DO UPDATE SET
                llm_input_json = excluded.llm_input_json,
                llm_output_json = excluded.llm_output_json,
                consequence_profile_json = excluded.consequence_profile_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                normalized_lane,
                normalized_objective_number,
                json.dumps(json_safe_payload(llm_input), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(llm_output), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(consequence_profile), ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )


def load_q6_objective_llm_io_rows_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    lane: str | None = None,
) -> list[dict[str, Any]]:
    resolved_db_path = _resolve_q6_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q6_objective_llm_io_table_missing: {resolved_db_path}")
    normalized_lane = str(lane or "").strip().lower()
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            _ensure_q6_objective_llm_io_table(conn)
            if normalized_lane:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           consequence_profile_json, updated_at
                    FROM {Q6_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ? AND lane = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id, normalized_lane),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           consequence_profile_json, updated_at
                    FROM {Q6_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("q6_objective_llm_io_table_missing") from exc
    return [_decode_q6_objective_llm_io_row(row) for row in rows]


def _ensure_q6_objective_llm_io_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {Q6_OBJECTIVE_LLM_IO_TABLE} (
            session_id TEXT NOT NULL,
            lane TEXT NOT NULL,
            objective_number TEXT NOT NULL,
            llm_input_json TEXT NOT NULL DEFAULT '{{}}',
            llm_output_json TEXT NOT NULL DEFAULT '{{}}',
            consequence_profile_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, lane, objective_number)
        )
        """
    )


def _decode_q6_objective_llm_io_row(row: sqlite3.Row) -> dict[str, Any]:
    def _loads(field: str) -> dict[str, Any]:
        try:
            value = json.loads(str(row[field] or "{}"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"q6_objective_llm_io_json_invalid:{field}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"q6_objective_llm_io_json_not_object:{field}")
        return value

    return {
        "lane": str(row["lane"] or ""),
        "objective_number": str(row["objective_number"] or ""),
        "llm_input": _loads("llm_input_json"),
        "llm_output": _loads("llm_output_json"),
        "consequence_profile": _loads("consequence_profile_json"),
        "updated_at": str(row["updated_at"] or ""),
    }


def _objective_map(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("objective_number") or "").strip(): item
        for item in items
        if isinstance(item, dict) and str(item.get("objective_number") or "").strip()
    }


def build_internal_public_output(
    *,
    q6_llm_output: dict[str, Any],
    q5_public_output: dict[str, Any],
) -> dict[str, Any]:
    upstream = q5_public_output.get("q5_internal_authorization_boundary")
    upstream = upstream if isinstance(upstream, dict) else q5_public_output
    q5_items = _objective_map(upstream.get("allowed_internal_objectives_with_conditions"))
    q6_items = q6_llm_output.get("constraints_by_objective")
    if not isinstance(q6_items, list):
        raise RuntimeError("q6_internal_public_output_constraints_missing")
    merged = [
        {**q5_items.get(str(item.get("objective_number") or "").strip(), {}), **item}
        for item in q6_items
        if isinstance(item, dict)
    ]
    return {
        **deepcopy(q6_llm_output),
        "constraints_by_objective": merged,
        "upstream_q5_public_output": deepcopy(upstream),
    }


def build_external_public_output(
    *,
    q6_llm_output: dict[str, Any],
    q5_public_output: dict[str, Any],
) -> dict[str, Any]:
    upstream = q5_public_output.get("q5_external_authorization_boundary")
    upstream = upstream if isinstance(upstream, dict) else q5_public_output
    q5_items = _objective_map(upstream.get("allowed_external_objectives_with_conditions"))
    q6_items = q6_llm_output.get("objective_constraints")
    if not isinstance(q6_items, list):
        raise RuntimeError("q6_external_public_output_constraints_missing")
    merged = [
        {**q5_items.get(str(item.get("objective_number") or "").strip(), {}), **item}
        for item in q6_items
        if isinstance(item, dict)
    ]
    return {
        **deepcopy(q6_llm_output),
        "objective_constraints": merged,
        "upstream_q5_public_output": deepcopy(upstream),
    }


def _load_objective_aggregate_output(
    *,
    lane: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    rows = load_q6_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane=lane)
    if not rows:
        raise RuntimeError(f"q6_{lane}_objective_llm_io_rows_missing")
    if lane == "internal":
        constraints: list[dict[str, Any]] = []
        for row in rows:
            profile = row.get("consequence_profile") if isinstance(row, dict) else {}
            profile = profile if isinstance(profile, dict) else {}
            items = profile.get("constraints_by_objective")
            if not isinstance(items, list) or not items:
                raise RuntimeError(f"q6_internal_objective_constraints_missing:{row.get('objective_number')}")
            for item in items:
                if not isinstance(item, dict):
                    raise RuntimeError(f"q6_internal_objective_constraint_invalid:{row.get('objective_number')}")
                item_number = str(item.get("objective_number") or row.get("objective_number") or "").strip()
                if not item_number:
                    raise RuntimeError("q6_internal_objective_number_missing")
                constraints.append({**item, "objective_number": item_number})
        return {"type": "InternalPlanConstraintSet", "constraints_by_objective": constraints}

    constraints = []
    for row in rows:
        profile = row.get("consequence_profile") if isinstance(row, dict) else {}
        profile = profile if isinstance(profile, dict) else {}
        items = profile.get("objective_constraints")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"q6_external_objective_constraints_missing:{row.get('objective_number')}")
        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(f"q6_external_objective_constraint_invalid:{row.get('objective_number')}")
            item_number = str(item.get("objective_number") or row.get("objective_number") or "").strip()
            if not item_number:
                raise RuntimeError("q6_external_objective_number_missing")
            constraints.append({**item, "objective_number": item_number})
    return {"type": "ExternalPlanConstraintSet", "objective_constraints": constraints}


def _load_q6_snapshot_field_from_table(
    *,
    field: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    output = load_llm_output_from_table(db_path=db_path, session_id=session_id)
    value = output.get(field)
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{field}_missing")
    return deepcopy(value)


def _load_q6_module_data_from_table(
    *,
    module_id: str,
    field: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q6_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q6_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT output_json
                FROM {Q6_MODULE_OUTPUTS_TABLE}
                WHERE session_id = ?
                  AND question_id = 'q6'
                  AND module_id = ?
                """,
                (session_id, module_id),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q6_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError(f"{module_id}_row_missing")
    try:
        output = json.loads(str(row["output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{module_id}_json_invalid") from exc
    if not isinstance(output, dict):
        raise RuntimeError(f"{module_id}_json_not_object")
    data = output.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{module_id}_data_missing")
    value = data.get(field)
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{field}_missing")
    return deepcopy(value)


def load_internal_llm_input_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_q6_snapshot_field_from_table(
        field="q6_internal_llm_input",
        db_path=db_path,
        session_id=session_id,
    )


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    q6_llm_output = _load_objective_aggregate_output(lane="internal", db_path=db_path, session_id=session_id)
    from plugins.nine_questions.q5_what_am_i_allowed_to_do.service import (
        load_public_output as load_q5_public_output,
    )

    q5_public_output = load_q5_public_output(db_path=db_path, session_id=session_id)
    return build_internal_public_output(q6_llm_output=q6_llm_output, q5_public_output=q5_public_output)


def load_external_llm_input_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_q6_snapshot_field_from_table(
        field="q6_external_llm_input",
        db_path=db_path,
        session_id=session_id,
    )


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    q6_llm_output = _load_objective_aggregate_output(lane="external", db_path=db_path, session_id=session_id)
    from plugins.nine_questions.q5_what_am_i_allowed_to_do.service import (
        load_public_output as load_q5_public_output,
    )

    q5_public_output = load_q5_public_output(db_path=db_path, session_id=session_id)
    return build_external_public_output(q6_llm_output=q6_llm_output, q5_public_output=q5_public_output)
