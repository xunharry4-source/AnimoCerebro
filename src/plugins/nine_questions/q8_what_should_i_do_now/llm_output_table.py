from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q8_SNAPSHOT_TABLE = "nine_question_q8_snapshots"


def _resolve_q8_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def _load_q8_llm_output_json_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q8_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q8_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q8_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q8_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q8_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q8_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict) or not llm_output:
        raise RuntimeError("q8_llm_output_missing")
    return llm_output


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q8_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    if not isinstance(llm_output.get("q8_external_execution_tasks"), list):
        raise RuntimeError("q8_external_execution_tasks_missing")
    if not isinstance(llm_output.get("q8_internal_cognitive_tasks"), list):
        raise RuntimeError("q8_internal_cognitive_tasks_missing")
    return deepcopy(llm_output)


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> list[Any]:
    llm_output = load_llm_output_from_table(db_path=db_path, session_id=session_id)
    payload = llm_output.get("q8_external_execution_tasks")
    if not isinstance(payload, list):
        raise RuntimeError("q8_external_execution_tasks_missing")
    return deepcopy(payload)


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> list[Any]:
    llm_output = load_llm_output_from_table(db_path=db_path, session_id=session_id)
    payload = llm_output.get("q8_internal_cognitive_tasks")
    if not isinstance(payload, list):
        raise RuntimeError("q8_internal_cognitive_tasks_missing")
    return deepcopy(payload)
