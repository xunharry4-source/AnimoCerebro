from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

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


def _resolve_q8_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    raise RuntimeError(
        "q8_combined_llm_output_forbidden: use load_internal_llm_io_from_table "
        "and load_external_llm_io_from_table separately"
    )


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
    return _load_scoped_llm_io_from_module_table(scope="internal", db_path=db_path, session_id=session_id)


def load_external_llm_io_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return _load_scoped_llm_io_from_module_table(scope="external", db_path=db_path, session_id=session_id)


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return deepcopy(load_internal_llm_io_from_table(db_path=db_path, session_id=session_id)["q8_internal_llm_output"])


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return deepcopy(load_external_llm_io_from_table(db_path=db_path, session_id=session_id)["q8_external_llm_output"])
