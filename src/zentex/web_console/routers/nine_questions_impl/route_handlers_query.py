from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.nine_questions.workflow import build_workflow_question_entry
from zentex.web_console.contracts.nine_questions import NineQuestionsReportPayload

from .q_commons import build_question_report_items
from .q_state import _get_nine_question_service, build_trace_id_map, get_nine_question_state, get_or_create_session
from .route_handlers_shared import QUESTION_TITLES, stringify_timestamp
from .trace_builder import build_trace_detail

router = APIRouter()


def _is_material_llm_trace(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for key in (
        "provider_name",
        "model",
        "system_prompt",
        "prompt",
        "context_data",
        "raw_response",
        "token_usage",
        "elapsed_ms",
        "error_type",
        "error_message",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def _merge_trace_payloads(*payloads: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                nested = dict(existing)
                nested.update({k: v for k, v in value.items() if v not in (None, "", [], {})})
                merged[key] = nested
            elif existing in (None, "", [], {}):
                merged[key] = value
    return merged


def _first_non_empty_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


@router.get("/nine-questions/status", response_model=NineQuestionsReportPayload)
async def get_nine_questions_status(request: Request):
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request)
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=False,
    )
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids=build_trace_id_map(state, questions),
    )


@router.get("/nine-questions/latest-report", response_model=NineQuestionsReportPayload)
async def get_latest_nine_questions_report(request: Request):
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request)
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=True,
    )
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids=build_trace_id_map(state, questions),
    )


@router.get("/nine-questions/workflow")
async def get_nine_questions_workflow(request: Request):
    session = await get_or_create_session(request)
    service = _get_nine_question_service(request)
    questions = []
    all_events: list[dict] = []
    for qid in [f"q{i}" for i in range(1, 10)]:
        record = await service.get_question_record(qid)
        question, events = build_workflow_question_entry(
            question_id=qid,
            question_title=QUESTION_TITLES.get(qid, qid.upper()),
            record=record,
        )
        all_events.extend(events)
        questions.append(question)
    summary_counts = {
        "completed": sum(1 for q in questions if q["current_status"] in {"ready", "completed", "degraded"}),
        "running": sum(1 for q in questions if q["current_status"] == "running"),
        "failed": sum(1 for q in questions if q["current_status"] in {"failed", "partial_failed"}),
        "not_started": sum(1 for q in questions if q["current_status"] == "not_started"),
    }
    return {
        "questions": questions,
        "events": all_events,
        "session_id": session.session_id,
        "event_count": len(all_events),
        "summary_counts": summary_counts,
    }


async def _get_question_payload(request: Request, question_id: str, attr: str):
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    await get_or_create_session(request)
    service = _get_nine_question_service(request)
    return await getattr(service, attr)(question_id)


@router.get("/nine-questions/{question_id}/summary")
async def get_nine_question_summary(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_summary")


@router.get("/nine-questions/{question_id}/evidence")
async def get_nine_question_evidence(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_evidence")


@router.get("/nine-questions/{question_id}/inference")
async def get_nine_question_inference(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_inference")


@router.get("/nine-questions/{question_id}/trace-payload")
async def get_nine_question_trace_payload(request: Request, question_id: str):
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")

    session = await get_or_create_session(request)
    service = _get_nine_question_service(request)
    trace_payload = await service.get_question_trace(question_id)
    trace_payload = trace_payload if isinstance(trace_payload, dict) else {}

    raw_payload = await service.get_question_raw(question_id)
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    raw_llm_payload = raw_payload.get("llm_trace_payload")
    raw_llm_payload = raw_llm_payload if isinstance(raw_llm_payload, dict) else {}

    snapshot = await service.get_question_snapshot(question_id) or {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    snapshot_llm_payload = snapshot.get("llm_trace_payload")
    snapshot_llm_payload = snapshot_llm_payload if isinstance(snapshot_llm_payload, dict) else {}

    trace_id = _first_non_empty_string(
        trace_payload.get("trace_id"),
        raw_payload.get("trace_id"),
        snapshot.get("trace_id"),
    )

    trace_detail_payload: dict[str, Any] = {}
    if (
        trace_id
        and not trace_id.endswith(":no-trace")
        and not any(
            _is_material_llm_trace(candidate)
            for candidate in (trace_payload, raw_llm_payload, snapshot_llm_payload)
        )
    ):
        trace_detail = await build_trace_detail(
            request=request,
            trace_id=trace_id,
            session_id=session.session_id,
        )
        if isinstance(trace_detail, dict):
            candidate = trace_detail.get("llm_trace_payload")
            trace_detail_payload = candidate if isinstance(candidate, dict) else {}

    merged = _merge_trace_payloads(
        {"trace_id": trace_id, "question_id": question_id},
        trace_payload,
        raw_llm_payload,
        snapshot_llm_payload,
        trace_detail_payload,
    )
    return merged if merged else trace_payload


@router.get("/nine-questions/{question_id}/raw")
async def get_nine_question_raw(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_raw")


@router.get("/nine-questions/{question_id}/modules")
async def get_nine_question_modules_endpoint(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_modules")


@router.get("/nine-questions/{question_id}")
async def get_nine_question_detail(request: Request, question_id: str):
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    state = await get_nine_question_state(request)
    question_item = await build_question_report_items(
        request=request,
        state=state,
        question_filter=question_id,
        include_trace_detail=True,
    )
    if not question_item:
        raise HTTPException(status_code=404, detail=f"Question {question_id} has no snapshot")
    return question_item[0]


@router.get("/nine-questions/traces/{trace_id}")
async def get_nine_question_trace_detail(request: Request, trace_id: str):
    if trace_id.endswith(":no-trace") or trace_id == "none" or trace_id == "":
        raise HTTPException(
            status_code=404,
            detail=f"Trace {trace_id} is a placeholder and has no execution data. This is expected for questions that haven't been executed yet.",
        )
    session = await get_or_create_session(request)
    trace_detail = await build_trace_detail(
        request=request,
        trace_id=trace_id,
        session_id=session.session_id,
    )
    if not trace_detail:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace_detail


@router.post("/nine-questions/{question_id}/test")
async def run_nine_question_sandbox_test(
    request: Request,
    question_id: str,
    test_request: dict[str, Any],
):
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request)
    from .q_handlers import run_question_test
    return await run_question_test(
        request=request,
        question_id=question_id,
        session_id=session.session_id,
        state=state,
        test_payload=test_request,
    )
