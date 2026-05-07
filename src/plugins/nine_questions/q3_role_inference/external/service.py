from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q1_where_am_i.llm_output_table import (
    load_llm_output_from_table as load_q1_llm_output_from_table,
)
from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_llm_output_from_table as load_q2_external_llm_output_from_table,
)
from plugins.nine_questions.q3_role_inference.external.llm_prompt import (
    build_q3_external_llm_request,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    require_model_provider,
)
from zentex.common.storage_paths import get_storage_paths

logger = logging.getLogger(__name__)
Q3_SNAPSHOT_TABLE = "nine_question_q3_snapshots"


def _load_identity_kernel_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("identity_kernel_snapshot")
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("q3_identity_kernel_snapshot_missing")
    return json_safe_payload(payload)


def _load_q1_llm_analysis_result(*, session_id: str) -> dict[str, Any]:
    q1_llm_output = load_q1_llm_output_from_table(session_id=session_id)
    q1_analysis_result = q1_llm_output.get("workspace_domain_inference")
    if not isinstance(q1_analysis_result, dict) or not q1_analysis_result:
        raise RuntimeError("q3_q1_llm_analysis_result_missing")
    return json_safe_payload(q1_analysis_result)


def _load_q3_external_prompt_context(context: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    return {
        "identity_kernel_snapshot": _load_identity_kernel_snapshot(context),
        "q1_environment_confirmation": _load_q1_llm_analysis_result(session_id=session_id),
        "q2_external_llm_output": load_q2_external_llm_output_from_table(session_id=session_id),
    }


def _save_q3_llm_io(
    *,
    session_id: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db_path = get_storage_paths().session_db
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT llm_output_json, created_at FROM {Q3_SNAPSHOT_TABLE} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        payload = {}
        created_at = now
        if row is not None:
            created_at = str(row["created_at"] or now)
            try:
                loaded = json.loads(str(row["llm_output_json"] or "{}"))
            except json.JSONDecodeError as exc:
                raise RuntimeError("q3_llm_output_json_invalid") from exc
            if isinstance(loaded, dict):
                payload = loaded
        payload["q3_external_llm_input"] = json_safe_payload(llm_input)
        if llm_output is None:
            payload.pop("q3_external_llm_output", None)
        else:
            payload["q3_external_llm_output"] = json_safe_payload(llm_output)
        conn.execute(
            f"""
            INSERT INTO {Q3_SNAPSHOT_TABLE}
                (session_id, schema_version, record_version, snapshot_schema_version,
                 snapshot_json, llm_output_json, llm_trace_json, result_json,
                 context_updates_json, created_at, updated_at)
            VALUES (?, 3, 1, 3, ?, ?, '{{}}', '{{}}', '{{}}', ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                record_version = record_version + 1,
                llm_output_json = excluded.llm_output_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                json.dumps({"question_id": "q3"}, ensure_ascii=False, separators=(",", ":")),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )


def run_q3_external_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    trace_id = f"{context.get('trace_id') or 'q3'}:external"
    decision_id = f"q3-external:{uuid4().hex}"
    provider = require_model_provider(context)
    external_prompt_context = _load_q3_external_prompt_context(context, session_id=session_id)
    request = build_q3_external_llm_request(context=external_prompt_context)
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q3_external_role",
        question_ref="q3:external",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=trace_id,
    )
    llm_input = {
        "prompt": request["full_prompt"],
    }
    logger.info("[Q3 EXTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    _save_q3_llm_io(session_id=session_id, llm_input=llm_input)
    raw_output = provider.generate_json(
        prompt=request["full_prompt"],
        context={},
        caller_context=caller_context,
        metadata={
            "question_id": "q3",
            "scope": "external",
            "max_json_repair_attempts": 0,
            "output_truncation_forbidden": True,
        },
    )
    llm_output = raw_output if isinstance(raw_output, dict) else {}
    if not llm_output:
        raise RuntimeError("q3_external_llm_output_empty")
    logger.info("[Q3 EXTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
    _save_q3_llm_io(session_id=session_id, llm_input=llm_input, llm_output=llm_output)
    return {
        "llm_input": llm_input,
        "llm_output": llm_output,
        "result": llm_output,
    }
