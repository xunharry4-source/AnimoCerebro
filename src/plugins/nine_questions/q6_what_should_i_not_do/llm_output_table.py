from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q6_MODULE_OUTPUTS_TABLE = "nine_question_module_outputs"
Q6_INTERNAL_INPUT_MODULE_ID = "q6_internal_llm_request"
Q6_INTERNAL_OUTPUT_MODULE_ID = "q6_internal_consequence_llm"
Q6_EXTERNAL_INPUT_MODULE_ID = "q6_external_llm_request"
Q6_EXTERNAL_OUTPUT_MODULE_ID = "q6_external_consequence_llm"


def _resolve_q6_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    raise RuntimeError("q6_combined_internal_external_llm_output_forbidden")


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
    return _load_q6_module_data_from_table(
        module_id=Q6_INTERNAL_INPUT_MODULE_ID,
        field="q6_internal_llm_input",
        db_path=db_path,
        session_id=session_id,
    )


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_q6_module_data_from_table(
        module_id=Q6_INTERNAL_OUTPUT_MODULE_ID,
        field="q6_internal_llm_output",
        db_path=db_path,
        session_id=session_id,
    )


def load_external_llm_input_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_q6_module_data_from_table(
        module_id=Q6_EXTERNAL_INPUT_MODULE_ID,
        field="q6_external_llm_input",
        db_path=db_path,
        session_id=session_id,
    )


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_q6_module_data_from_table(
        module_id=Q6_EXTERNAL_OUTPUT_MODULE_ID,
        field="q6_external_llm_output",
        db_path=db_path,
        session_id=session_id,
    )
