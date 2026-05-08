from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q1_where_am_i.llm_output_table import (
    load_workspace_domain_inference_from_table as load_q1_workspace_domain_inference_from_table,
)
from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_function_signal_from_table as load_q2_external_function_signal_from_table,
)
from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_external_llm_output_from_table as load_q3_external_llm_output_from_table,
)
from plugins.nine_questions.q4_what_can_i_do.external.llm_prompt import (
    build_q4_external_llm_request,
)
from plugins.nine_questions.q4_what_can_i_do.external.instructor_contract import (
    generate_external_objective_candidate_set_with_instructor_contract,
)
from plugins.nine_questions.q4_what_can_i_do.semantic_guard import (
    run_q4_objective_generation_with_semantic_guard,
)
from zentex.common.nine_questions_shared import (
    json_safe_payload,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
)
from zentex.common.storage_paths import get_storage_paths

logger = logging.getLogger(__name__)
Q4_SNAPSHOT_TABLE = "nine_question_q4_snapshots"


def run_q4_external_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    trace_id = f"{context.get('trace_id') or 'q4'}:external"
    decision_id = f"q4-external:{uuid4().hex}"
    provider = require_model_provider(context)
    require_transcript_store(context)
    prompt_context = _build_external_prompt_context(context)
    request = build_q4_external_llm_request(context=prompt_context)
    llm_input = {
        "prompt": request["full_prompt"],
    }
    _save_q4_external_llm_io(session_id=session_id, llm_input=llm_input)
    logger.info("[Q4 EXTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    try:
        generation = run_q4_objective_generation_with_semantic_guard(
            provider=provider,
            lane="external",
            prompt=request["full_prompt"],
            generate_candidate_set=generate_external_objective_candidate_set_with_instructor_contract,
            trace_id=trace_id,
            source_module=__name__,
            invocation_phase="nine_question_q4_external_objective_candidates",
            question_ref="q4:external",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id_prefix=decision_id,
            metadata={
                "question_id": "q4",
                "scope": "external",
                "output_schema": "ExternalObjectiveCandidateSet",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        llm_input = {"prompt": generation["prompt"]}
        llm_output = generation["candidate_set"]
        _save_q4_external_llm_io(session_id=session_id, llm_input=llm_input, llm_output=llm_output)
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_external_objective_candidate_llm",
            payload={
                "q4_external_llm_input": llm_input,
                "q4_external_llm_output": llm_output,
            },
            status="completed",
            output_kind="inference",
            trace_id=trace_id,
        )
        logger.info("[Q4 EXTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "semantic_guard": generation["semantic_guard"],
            "semantic_guard_attempt_count": generation["attempt_count"],
            "result": _extract_external_result(llm_output),
        }
    except Exception as exc:
        logger.exception("[Q4 EXTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _extract_external_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    if llm_output.get("type") == "ExternalObjectiveCandidateSet":
        return llm_output
    raise RuntimeError("q4_external_objective_candidate_set_missing")


def _load_external_reflection_gap_signal(context: dict[str, Any]) -> dict[str, Any]:
    reflection_service = context.get("reflection_service")
    query = getattr(reflection_service, "query_current_problem_contents", None)
    if not callable(query):
        raise RuntimeError("q4_external_reflection_current_problem_content_query_unavailable")

    result = query(problem_scope="external")
    if not isinstance(result, dict):
        raise RuntimeError(
            f"q4_external_reflection_current_problem_content_query_invalid_result:{type(result).__name__}"
        )
    return json_safe_payload(result)


def _build_external_prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "nq-baseline")
    db_path = context.get("nine_question_state_db_path")
    q1_output = _load_q1_business_llm_output(db_path=db_path, session_id=session_id)
    q2_external_output = load_q2_external_function_signal_from_table(db_path=db_path, session_id=session_id)
    q3_external_output = load_q3_external_llm_output_from_table(db_path=db_path, session_id=session_id)

    return {
        "Q3_ExternalDelegationPosture": q3_external_output,
        "Q1_EnvironmentObjectiveSignal_External": q1_output,
        "Q2_SelfObservationObjectiveSignal_External": q2_external_output,
        "Q1Q2_FusedObjectiveSignal_External": _build_q1q2_fused_external_signal(
            q1_output=q1_output,
            q2_external_output=q2_external_output,
        ),
        "Reflection_CapabilityGapSignal_External": _load_external_reflection_gap_signal(context),
        "CapabilityBoundaryEvidence_External": _build_external_capability_boundary_evidence(
            q2_external_output=q2_external_output,
            q3_external_output=q3_external_output,
        ),
        "UserManualTaskGoalLaneAnalysis": context.get(
            "UserManualTaskGoalLaneAnalysis",
            {"type": "ManualTaskGoalLaneAnalysisSet", "manual_task_goals": []},
        ),
    }


def _load_q1_business_llm_output(*, db_path: Any, session_id: str) -> dict[str, Any]:
    return load_q1_workspace_domain_inference_from_table(db_path=db_path, session_id=session_id)


def _build_q1q2_fused_external_signal(
    *,
    q1_output: dict[str, Any],
    q2_external_output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "environment_signal": json_safe_payload(q1_output),
        "external_capability_signal": json_safe_payload(q2_external_output),
    }


def _build_external_capability_boundary_evidence(
    *,
    q2_external_output: dict[str, Any],
    q3_external_output: dict[str, Any],
) -> dict[str, Any]:
    functions = q2_external_output.get("functions") if isinstance(q2_external_output, dict) else []
    tools: list[dict[str, str]] = []
    for item in functions if isinstance(functions, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("function_name") or "").strip()
        description = str(item.get("function_description") or "").strip()
        if name or description:
            tools.append(
                {
                    "tool_or_capability_name": name,
                    "capability_description": description,
                }
            )
    return {
        "external_tools_and_capabilities": tools,
        "external_delegation_posture": json_safe_payload(q3_external_output),
    }


def _save_q4_external_llm_io(
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
            f"SELECT llm_output_json, created_at FROM {Q4_SNAPSHOT_TABLE} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        payload: dict[str, Any] = {}
        created_at = now
        if row is not None:
            created_at = str(row["created_at"] or now)
            try:
                loaded = json.loads(str(row["llm_output_json"] or "{}"))
            except json.JSONDecodeError as exc:
                raise RuntimeError("q4_llm_output_json_invalid") from exc
            if isinstance(loaded, dict):
                payload = loaded
        payload["q4_external_llm_input"] = json_safe_payload(llm_input)
        if llm_output is None:
            payload.pop("q4_external_llm_output", None)
        else:
            payload["q4_external_llm_output"] = json_safe_payload(llm_output)
        conn.execute(
            f"""
            INSERT INTO {Q4_SNAPSHOT_TABLE}
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
                json.dumps({"question_id": "q4"}, ensure_ascii=False, separators=(",", ":")),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )
        if llm_output is not None:
            _upsert_q4_external_module_output(
                conn,
                session_id=session_id,
                payload={
                    "q4_external_llm_input": json_safe_payload(llm_input),
                    "q4_external_llm_output": json_safe_payload(llm_output),
                },
                status="completed",
                updated_at=now,
            )


def _upsert_q4_external_module_output(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    payload: dict[str, Any],
    status: str,
    updated_at: str,
) -> None:
    committed_payload = {
        "question_id": "q4",
        "module_id": "q4_external_objective_candidate_llm",
        "status": status,
        "output_kind": "inference",
        "data": payload,
        "committed_at": updated_at,
        "rollback_available": True,
        "retry_available": True,
    }
    conn.execute(
        """
        INSERT INTO nine_question_module_outputs
            (session_id, question_id, module_id, schema_version, output_version,
             status, output_kind, output_json, created_at, updated_at)
        VALUES (?, 'q4', 'q4_external_objective_candidate_llm', 1, 1, ?, 'inference', ?, ?, ?)
        ON CONFLICT(session_id, question_id, module_id) DO UPDATE SET
            output_version = output_version + 1,
            status = excluded.status,
            output_kind = excluded.output_kind,
            output_json = excluded.output_json,
            updated_at = excluded.updated_at
        """,
        (
            session_id,
            status,
            json.dumps(committed_payload, ensure_ascii=False, separators=(",", ":"), default=str),
            updated_at,
            updated_at,
        ),
    )
