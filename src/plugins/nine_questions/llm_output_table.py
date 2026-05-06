from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"


def load_question_llm_output_from_table(
    question_id: str,
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    qid = str(question_id or "").strip().lower()
    if qid not in {f"q{index}" for index in range(1, 10)}:
        raise RuntimeError(f"nine_question_llm_output_question_invalid: {qid}")
    resolved_db_path = Path(str(db_path)) if db_path not in (None, "", [], {}) else get_storage_paths().session_db
    if not resolved_db_path.exists():
        raise RuntimeError(f"{qid}_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM nine_question_{qid}_snapshots
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"{qid}_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError(f"{qid}_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{qid}_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict) or not llm_output:
        raise RuntimeError(f"{qid}_llm_output_missing")
    return deepcopy(llm_output)
