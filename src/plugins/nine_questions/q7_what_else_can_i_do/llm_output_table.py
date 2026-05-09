from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths
from zentex.common.nine_questions_shared import json_safe_payload
from plugins.nine_questions.q7_what_else_can_i_do.assessment_contract import (
    normalize_q7_external_creative_possibility_set,
    normalize_q7_internal_creative_possibility_set,
)

NQ_BASELINE_SESSION_ID = "nq-baseline"
_Q7_SCOPE_MODULES = {
    "internal": (
        "q7_internal_creativity_llm",
        "q7_internal_llm_input",
        "q7_internal_llm_output",
    ),
    "external": (
        "q7_external_creativity_llm",
        "q7_external_llm_input",
        "q7_external_llm_output",
    ),
}


Q7_SNAPSHOT_TABLE = "nine_question_q7_snapshots"
Q7_OBJECTIVE_LLM_IO_TABLE = "nine_question_q7_objective_llm_io"


def _resolve_q7_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    raise RuntimeError("q7_combined_llm_output_forbidden")


def _load_scoped_llm_io_from_module_table(
    *,
    scope: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q7_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q7_module_output_table_missing: {resolved_db_path}")
    module_id, input_key, output_key = _Q7_SCOPE_MODULES[scope]
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT output_json
                FROM nine_question_module_outputs
                WHERE session_id = ? AND question_id = 'q7' AND module_id = ?
                """,
                (session_id, module_id),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q7_module_output_table_missing") from exc
    if row is None:
        raise RuntimeError(f"q7_{scope}_module_output_row_missing")
    try:
        module_output = json.loads(str(row["output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"q7_{scope}_module_output_json_invalid") from exc
    if not isinstance(module_output, dict):
        raise RuntimeError(f"q7_{scope}_module_output_json_not_object")
    data = module_output.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"q7_{scope}_module_output_data_missing")
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
    try:
        return _load_scoped_llm_io_from_module_table(scope="internal", db_path=db_path, session_id=session_id)
    except RuntimeError as exc:
        if (
            "q7_internal_module_output_row_missing" not in str(exc)
            and "q7_module_output_table_missing" not in str(exc)
        ):
            raise
    return _load_objective_aggregate_llm_io(lane="internal", db_path=db_path, session_id=session_id)


def load_external_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    try:
        return _load_scoped_llm_io_from_module_table(scope="external", db_path=db_path, session_id=session_id)
    except RuntimeError as exc:
        if (
            "q7_external_module_output_row_missing" not in str(exc)
            and "q7_module_output_table_missing" not in str(exc)
        ):
            raise
    return _load_objective_aggregate_llm_io(lane="external", db_path=db_path, session_id=session_id)


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    q7_output = _load_objective_aggregate_output(lane="internal", db_path=db_path, session_id=session_id)
    if q7_output is None:
        q7_output = load_internal_llm_io_from_table(db_path=db_path, session_id=session_id)["q7_internal_llm_output"]
    normalize_q7_internal_creative_possibility_set(q7_output)
    from plugins.nine_questions.q6_what_should_i_not_do.service import (
        load_internal_public_output as load_q6_internal_public_output,
    )

    q6_public_output = load_q6_internal_public_output(db_path=db_path, session_id=session_id)
    return build_internal_public_output(q7_output=q7_output, q6_public_output=q6_public_output)


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    q7_output = _load_objective_aggregate_output(lane="external", db_path=db_path, session_id=session_id)
    if q7_output is None:
        q7_output = load_external_llm_io_from_table(db_path=db_path, session_id=session_id)["q7_external_llm_output"]
    normalize_q7_external_creative_possibility_set(q7_output)
    from plugins.nine_questions.q6_what_should_i_not_do.service import (
        load_external_public_output as load_q6_external_public_output,
    )

    q6_public_output = load_q6_external_public_output(db_path=db_path, session_id=session_id)
    return build_external_public_output(q7_output=q7_output, q6_public_output=q6_public_output)


def save_q7_objective_llm_io_to_table(
    *,
    db_path: str | Path | None = None,
    session_id: str,
    lane: str,
    objective_number: str,
    llm_input: dict[str, Any],
    output_payload: dict[str, Any],
    creative_profile: dict[str, Any],
) -> None:
    normalized_lane = str(lane or "").strip().lower()
    normalized_objective_number = str(objective_number or "").strip()
    if normalized_lane not in {"internal", "external"}:
        raise RuntimeError(f"q7_objective_llm_io_invalid_lane:{lane}")
    if not normalized_objective_number:
        raise RuntimeError("q7_objective_llm_io_objective_number_missing")
    now = datetime.now(timezone.utc).isoformat()
    resolved_db_path = _resolve_q7_state_db_path(db_path)
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_q7_objective_llm_io_table(conn)
        row = conn.execute(
            f"""
            SELECT created_at
            FROM {Q7_OBJECTIVE_LLM_IO_TABLE}
            WHERE session_id = ? AND lane = ? AND objective_number = ?
            """,
            (session_id, normalized_lane, normalized_objective_number),
        ).fetchone()
        created_at = str(row["created_at"]) if row is not None else now
        conn.execute(
            f"""
            INSERT INTO {Q7_OBJECTIVE_LLM_IO_TABLE}
                (session_id, lane, objective_number,
                 llm_input_json, llm_output_json, creative_profile_json,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, lane, objective_number) DO UPDATE SET
                llm_input_json = excluded.llm_input_json,
                llm_output_json = excluded.llm_output_json,
                creative_profile_json = excluded.creative_profile_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                normalized_lane,
                normalized_objective_number,
                json.dumps(json_safe_payload(llm_input), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(output_payload), ensure_ascii=False, separators=(",", ":"), default=str),
                json.dumps(json_safe_payload(creative_profile), ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )


def load_q7_objective_llm_io_rows_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
    lane: str | None = None,
) -> list[dict[str, Any]]:
    resolved_db_path = _resolve_q7_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q7_objective_llm_io_table_missing: {resolved_db_path}")
    normalized_lane = str(lane or "").strip().lower()
    with sqlite3.connect(str(resolved_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            _ensure_q7_objective_llm_io_table(conn)
            if normalized_lane:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           creative_profile_json, updated_at
                    FROM {Q7_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ? AND lane = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id, normalized_lane),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT lane, objective_number, llm_input_json, llm_output_json,
                           creative_profile_json, updated_at
                    FROM {Q7_OBJECTIVE_LLM_IO_TABLE}
                    WHERE session_id = ?
                    ORDER BY lane, objective_number
                    """,
                    (session_id,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("q7_objective_llm_io_table_missing") from exc
    return [_decode_q7_objective_llm_io_row(row) for row in rows]


def _ensure_q7_objective_llm_io_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {Q7_OBJECTIVE_LLM_IO_TABLE} (
            session_id TEXT NOT NULL,
            lane TEXT NOT NULL,
            objective_number TEXT NOT NULL,
            llm_input_json TEXT NOT NULL DEFAULT '{{}}',
            llm_output_json TEXT NOT NULL DEFAULT '{{}}',
            creative_profile_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, lane, objective_number)
        )
        """
    )


def _decode_q7_objective_llm_io_row(row: sqlite3.Row) -> dict[str, Any]:
    def _loads(field: str) -> dict[str, Any]:
        try:
            value = json.loads(str(row[field] or "{}"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"q7_objective_llm_io_json_invalid:{field}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"q7_objective_llm_io_json_not_object:{field}")
        return value

    return {
        "lane": str(row["lane"] or ""),
        "objective_number": str(row["objective_number"] or ""),
        "llm_input": _loads("llm_input_json"),
        "llm_output": _loads("llm_output_json"),
        "creative_profile": _loads("creative_profile_json"),
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


def _load_objective_aggregate_llm_io(
    *,
    lane: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    rows = load_q7_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane=lane)
    if not rows:
        raise RuntimeError(f"q7_{lane}_objective_llm_io_rows_missing")
    output = _aggregate_objective_creative_profile(lane=lane, rows=rows)
    if output is None:
        raise RuntimeError(f"q7_{lane}_objective_creative_profile_missing")
    input_key = "q7_internal_llm_input" if lane == "internal" else "q7_external_llm_input"
    output_key = "q7_internal_llm_output" if lane == "internal" else "q7_external_llm_output"
    return {
        input_key: {
            "type": "Q7ObjectiveRequestBatch",
            "scope": lane,
            "objective_requests": [
                {
                    "objective_number": row["objective_number"],
                    "llm_input": deepcopy(row["llm_input"]),
                }
                for row in rows
            ],
        },
        output_key: output,
    }


def _load_objective_aggregate_output(
    *,
    lane: str,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any] | None:
    rows = load_q7_objective_llm_io_rows_from_table(db_path=db_path, session_id=session_id, lane=lane)
    if not rows:
        return None
    return _aggregate_objective_creative_profile(lane=lane, rows=rows)


def _aggregate_objective_creative_profile(
    *,
    lane: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None
    possibilities: list[dict[str, Any]] = []
    for row in rows:
        profile = row.get("creative_profile") if isinstance(row, dict) else {}
        profile = profile if isinstance(profile, dict) else {}
        items = profile.get("creative_possibilities")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"q7_{lane}_objective_creative_possibilities_missing:{row.get('objective_number')}")
        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(f"q7_{lane}_objective_creative_possibility_invalid:{row.get('objective_number')}")
            item_number = str(item.get("objective_number") or row.get("objective_number") or "").strip()
            if not item_number:
                raise RuntimeError(f"q7_{lane}_objective_number_missing")
            possibilities.append({**item, "objective_number": item_number})
    output_type = "InternalCreativePossibilitySet" if lane == "internal" else "ExternalCreativePossibilitySet"
    return {"type": output_type, "creative_possibilities": possibilities}


def build_internal_public_output(
    *,
    q7_output: dict[str, Any],
    q6_public_output: dict[str, Any],
) -> dict[str, Any]:
    q7_normalized = normalize_q7_internal_creative_possibility_set(q7_output)
    q6_items = _objective_map(q6_public_output.get("constraints_by_objective"))
    possibilities = q7_normalized.get("creative_possibilities")
    if not isinstance(possibilities, list):
        raise RuntimeError("q7_internal_public_output_possibilities_missing")
    merged = [
        {**q6_items.get(str(item.get("objective_number") or "").strip(), {}), **item}
        for item in possibilities
        if isinstance(item, dict)
    ]
    return {
        **deepcopy(q7_normalized),
        "creative_possibilities": merged,
        "ready_for_q4_objective_candidates": [
            item for item in merged if item.get("possibility_status") == "ready_for_q4_objective_candidate"
        ],
        "upstream_q6_public_output": deepcopy(q6_public_output),
    }


def build_external_public_output(
    *,
    q7_output: dict[str, Any],
    q6_public_output: dict[str, Any],
) -> dict[str, Any]:
    q7_normalized = normalize_q7_external_creative_possibility_set(q7_output)
    q6_items = _objective_map(q6_public_output.get("objective_constraints"))
    possibilities = q7_normalized.get("creative_possibilities")
    if not isinstance(possibilities, list):
        raise RuntimeError("q7_external_public_output_possibilities_missing")
    merged = [
        {**q6_items.get(str(item.get("objective_number") or "").strip(), {}), **item}
        for item in possibilities
        if isinstance(item, dict)
    ]
    return {
        **deepcopy(q7_normalized),
        "creative_possibilities": merged,
        "ready_for_q4_objective_candidates": [
            item for item in merged if item.get("possibility_status") == "ready_for_q4_objective_candidate"
        ],
        "needs_registration_possibilities": [
            item for item in merged if item.get("possibility_status") == "needs_registration"
        ],
        "upstream_q6_public_output": deepcopy(q6_public_output),
    }
