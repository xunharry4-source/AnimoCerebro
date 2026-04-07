from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException, Request

from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession
from zentex.runtime.transcript import BrainTranscriptEntryType
from zentex.web_console.contracts.interventions import InterventionRequest


def post_intervention(payload: InterventionRequest, runtime: BrainRuntime, request: Request) -> Dict[str, Any]:
    session = getattr(request.app.state, "session", None)
    if session is not None and not isinstance(session, BrainSession):
        session = None

    if session is None:
        session = runtime.create_session("web-console")
        request.app.state.session = session

    existing_receipt = runtime.get_intervention_receipt(payload.idempotency_key)
    if existing_receipt is not None:
        return {**existing_receipt, "idempotent_replay": True}

    existing_intervention_entry = next(
        (
            entry
            for entry in reversed(runtime.transcript_store.get_entries_snapshot())
            if entry.entry_type == BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED
            and isinstance(entry.payload, dict)
            and entry.payload.get("idempotency_key") == payload.idempotency_key
        ),
        None,
    )
    if existing_intervention_entry is not None and isinstance(existing_intervention_entry.payload, dict):
        payload_dict = existing_intervention_entry.payload
        replay_receipt = {
            "ok": True,
            "idempotent_replay": True,
            "action": payload_dict.get("action"),
            "operator_id": payload_dict.get("operator_id"),
            "idempotency_key": payload.idempotency_key,
            "trace_id": payload_dict.get("trace_id") or existing_intervention_entry.trace_id,
            "control_state": payload_dict.get("control_state"),
            "nine_question_state": {
                "question_driver_refs": runtime.nine_question_state.question_driver_refs,
                "revision": runtime.nine_question_state.revision,
                "last_refresh_reason": runtime.nine_question_state.last_refresh_reason,
                "refreshed_at": runtime.nine_question_state.refreshed_at,
                "current_role_hypothesis": runtime.nine_question_state.current_role_hypothesis,
                "current_context": runtime.nine_question_state.current_context,
                "active_constraints": runtime.nine_question_state.active_constraints,
                "operator_patch": runtime.nine_question_state.operator_patch,
            },
        }
        runtime.store_intervention_receipt(payload.idempotency_key, replay_receipt)
        return replay_receipt

    trace_id = f"intervention:{payload.idempotency_key}"
    processed_at = datetime.now(timezone.utc)

    try:
        control_state = runtime.request_intervention(
            action=payload.action,
            operator_id=payload.operator_id,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
            trace_id=trace_id,
            phase_name=payload.phase_name,
            manual_context_patch=payload.manual_context_patch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    priority_working_memory = runtime.build_priority_intervention_working_memory()
    question_driver_refs = list(runtime.nine_question_state.question_driver_refs)
    session.advance_turn(
        {
            "turn_id": f"intervention-{payload.idempotency_key}",
            "trace_id": trace_id,
            "phase_trace_ids": {
                "context_snapshot": trace_id,
                "working_memory": trace_id,
                "human_intervention": trace_id,
            },
            "timestamp": processed_at,
            "status": "completed",
            "context_snapshot": {
                "target_phase": payload.phase_name,
                "intervention_trace_id": trace_id,
                "nine_question_state": {
                    "question_driver_refs": question_driver_refs,
                    "revision": runtime.nine_question_state.revision,
                    "last_refresh_reason": runtime.nine_question_state.last_refresh_reason,
                    "refreshed_at": runtime.nine_question_state.refreshed_at,
                    "current_role_hypothesis": runtime.nine_question_state.current_role_hypothesis,
                    "current_context": runtime.nine_question_state.current_context,
                    "active_constraints": runtime.nine_question_state.active_constraints,
                    "operator_patch": runtime.nine_question_state.operator_patch,
                },
            },
            "working_memory": priority_working_memory,
            "human_intervention": {
                "action": payload.action,
                "reason": payload.reason,
                "operator_id": payload.operator_id,
                "phase_name": payload.phase_name,
                "idempotency_key": payload.idempotency_key,
                "trace_id": trace_id,
                "question_driver_refs": question_driver_refs,
                "manual_context_patch": payload.manual_context_patch,
                "control_state": control_state,
            },
        }
    )
    receipt = {
        "ok": True,
        "idempotent_replay": False,
        "action": payload.action,
        "operator_id": payload.operator_id,
        "idempotency_key": payload.idempotency_key,
        "trace_id": trace_id,
        "control_state": control_state,
        "nine_question_state": {
            "question_driver_refs": question_driver_refs,
            "revision": runtime.nine_question_state.revision,
            "last_refresh_reason": runtime.nine_question_state.last_refresh_reason,
            "refreshed_at": runtime.nine_question_state.refreshed_at,
            "current_role_hypothesis": runtime.nine_question_state.current_role_hypothesis,
            "current_context": runtime.nine_question_state.current_context,
            "active_constraints": runtime.nine_question_state.active_constraints,
            "operator_patch": runtime.nine_question_state.operator_patch,
        },
    }
    runtime.store_intervention_receipt(payload.idempotency_key, receipt)
    return receipt

