from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q3_SNAPSHOT_TABLE = "nine_question_q3_snapshots"
Q3_REQUIRED_LLM_FIELDS = (
    "q3_external_llm_input",
    "q3_external_llm_output",
)


def _resolve_q3_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def load_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q3_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q3_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q3_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q3_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q3_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q3_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q3_llm_output_json_not_object")
    for field in Q3_REQUIRED_LLM_FIELDS:
        if not isinstance(llm_output.get(field), dict) or not llm_output.get(field):
            raise RuntimeError(f"{field}_missing")
    return deepcopy(llm_output)


def load_public_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q3_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q3_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json, context_updates_json
                FROM {Q3_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q3_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q3_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
        context_updates = json.loads(str(row["context_updates_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q3_public_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q3_llm_output_json_not_object")
    if not isinstance(context_updates, dict):
        raise RuntimeError("q3_context_updates_json_not_object")
    for field in Q3_REQUIRED_LLM_FIELDS:
        if not isinstance(llm_output.get(field), dict) or not llm_output.get(field):
            raise RuntimeError(f"{field}_missing")
    role_profile = context_updates.get("q3_role_profile")
    mission_boundary = context_updates.get("q3_mission_boundary")
    if not isinstance(role_profile, dict) or not role_profile:
        raise RuntimeError("q3_role_profile_missing")
    if not isinstance(mission_boundary, dict) or not mission_boundary:
        raise RuntimeError("q3_mission_boundary_missing")
    if not str(mission_boundary.get("current_mission") or "").strip():
        raise RuntimeError("q3_mission_boundary_current_mission_missing")
    public_output = {
        "q3_role_profile": role_profile,
        "q3_mission_boundary": mission_boundary,
    }
    diagnosis = context_updates.get("q3_execution_diagnosis")
    if isinstance(diagnosis, dict) and diagnosis:
        public_output["q3_execution_diagnosis"] = diagnosis
    return deepcopy(public_output)


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return deepcopy(load_llm_output_from_table(db_path=db_path, session_id=session_id)["q3_external_llm_output"])
