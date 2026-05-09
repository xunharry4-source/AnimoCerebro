import json
import logging
import sqlite3
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q5_what_am_i_allowed_to_do.boundary_projection import (
    normalize_q5_internal_boundary,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal.llm_prompt import (
    build_q5_internal_llm_request,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_flow import (
    persist_q5_model_completed,
    persist_q5_model_invoked,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    record_model_failed,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.common.storage_paths import get_storage_paths

logger = logging.getLogger(__name__)
Q5_SNAPSHOT_TABLE = "nine_question_q5_snapshots"


def run_q5_internal_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q5'}:internal"
    request_id = f"q5-internal-request:{uuid4().hex}"
    decision_id = f"q5-internal:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q5_internal_llm_request(context=dict(context))
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q5_internal_authorization",
        question_ref="q5:internal",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=trace_id,
    )
    llm_input = {
        "request_id": request_id,
        "decision_id": decision_id,
        "provider_plugin_id": safe_provider_plugin_id(provider),
        "system_prompt": request["system_prompt"],
        "prompt": request["prompt"],
        "context": request["model_context"],
        "caller_context": caller_context.model_dump(mode="json"),
    }
    _save_q5_internal_llm_io(session_id=session_id, llm_input=llm_input)
    persist_q5_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q5_internal_llm_input": llm_input},
    )
    logger.info("[Q5 INTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    try:
        from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal.instructor_contract import (
            generate_internal_goal_compliance_assessment_with_instructor_contract,
        )

        llm_output = generate_internal_goal_compliance_assessment_with_instructor_contract(
            provider,
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q5",
                "scope": "internal",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        result = normalize_q5_internal_boundary(llm_output)
        _save_q5_internal_llm_io(session_id=session_id, llm_input=llm_input, llm_output=llm_output)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_internal_authorization_llm",
            payload={
                "q5_internal_llm_input": llm_input,
                "q5_internal_llm_output": llm_output,
            },
            status="completed",
            output_kind="inference",
            trace_id=trace_id,
        )
        persist_q5_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q5_internal_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        logger.info("[Q5 INTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": result,
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q5_internal_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q5 INTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _save_q5_internal_llm_io(
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
            f"SELECT llm_output_json, created_at FROM {Q5_SNAPSHOT_TABLE} WHERE session_id = ?",
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
        payload["q5_internal_llm_input"] = json_safe_payload(llm_input)
        if llm_output is None:
            payload.pop("q5_internal_llm_output", None)
        else:
            payload["q5_internal_llm_output"] = json_safe_payload(llm_output)
        conn.execute(
            f"""
            INSERT INTO {Q5_SNAPSHOT_TABLE}
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
