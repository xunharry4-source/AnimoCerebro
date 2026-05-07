from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q4_SNAPSHOT_TABLE = "nine_question_q4_snapshots"


def _resolve_q4_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def _load_q4_llm_output_json_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q4_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q4_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q4_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q4_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q4_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q4_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q4_llm_output_json_not_object")
    return llm_output


def _require_dict(llm_output: dict[str, Any], key: str) -> dict[str, Any]:
    payload = llm_output.get(key)
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"{key}_missing")
    return payload


def load_internal_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q4_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    return deepcopy(
        {
            "q4_internal_llm_input": _require_dict(llm_output, "q4_internal_llm_input"),
            "q4_internal_llm_output": _require_dict(llm_output, "q4_internal_llm_output"),
        }
    )


def load_external_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q4_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    return deepcopy(
        {
            "q4_external_llm_input": _require_dict(llm_output, "q4_external_llm_input"),
            "q4_external_llm_output": _require_dict(llm_output, "q4_external_llm_output"),
        }
    )


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q4_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    return deepcopy(_require_dict(llm_output, "q4_internal_llm_output"))


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q4_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    return deepcopy(_require_dict(llm_output, "q4_external_llm_output"))
