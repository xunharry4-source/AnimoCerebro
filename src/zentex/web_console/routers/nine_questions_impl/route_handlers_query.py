from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.nine_questions.objective_engine import NineQDrivenObjectiveEngine, ObjectiveProfileMissingError
from zentex.kernel.prompt_contracts import build_contract_summary
from zentex.nine_questions.q8_phase_a_observability import (
    DEFAULT_PHASE_A_LENSES,
    Q8PhaseAExitGateError,
    Q8PhaseALensDistributionError,
    Q8PhaseAObservationGateError,
    Q8PhaseAObservationError,
    build_q8_phase_a_exit_gate_report,
    build_q8_phase_a_lens_distribution_report,
    build_q8_phase_a_observation_gate_report,
    build_q8_phase_a_observation_report,
)
from zentex.nine_questions.q8_phase_b_value_scorer import (
    DEFAULT_REQUIRED_LENSES,
    Q8PhaseBValueScoringError,
    build_q8_phase_b_value_score_report,
)
from zentex.nine_questions.q8_phase_b_llm_value_scorer import (
    DEFAULT_LLM_SAMPLE_COUNT,
    DEFAULT_MINIMUM_CONFIDENCE,
    DEFAULT_MINIMUM_SEMANTIC_SCORE,
    Q8PhaseBLLMValueScoringError,
    build_q8_phase_b_llm_value_score_report,
)
from zentex.nine_questions.q8_phase_b_manual_review import (
    DEFAULT_MANUAL_REVIEW_RATIO,
    DEFAULT_MINIMUM_AGREEMENT_RATE,
    DEFAULT_MINIMUM_REVIEW_COUNT,
    Q8PhaseBManualReviewError,
    build_q8_phase_b_manual_review_report,
)
from zentex.nine_questions.q8_phase_b_production_observation_gate import (
    Q8PhaseBProductionObservationGateError,
    build_q8_phase_b_production_observation_gate_report,
)
from zentex.nine_questions.q8_prompt_v2_gate import (
    DEFAULT_EXPECTED_REPLAY_COUNT,
    DEFAULT_MAX_AVERAGE_LLM_CALLS,
    DEFAULT_MIN_LATENCY_REDUCTION_RATE,
    DEFAULT_MIN_PROMPT_REDUCTION_RATE,
    DEFAULT_MIN_QUALITY_DELTA,
    DEFAULT_MIN_TOKEN_REDUCTION_RATE,
    Q8PromptV2GateError,
    build_q8_prompt_v2_gate_report,
)
from zentex.nine_questions.q8_replay_integrity import Q8ReplayIntegrityError, build_q8_replay_integrity_report
from zentex.nine_questions.plan_completion_gate import (
    PlanCompletionGateError,
    build_plan_completion_gate_report,
)
from zentex.nine_questions.plan_evidence_registry import (
    PlanEvidenceRegistryError,
    build_plan_evidence_summary,
)
from zentex.nine_questions.plan_execution_evidence import (
    PlanExecutionEvidenceError,
    build_plan_execution_evidence_summary,
)
from zentex.nine_questions.plan_remaining_work import (
    PlanRemainingWorkError,
    assert_plan_remaining_work_complete,
    build_plan_remaining_work_report,
)
from zentex.nine_questions.workflow import build_workflow_question_entry
from zentex.reflection.living_self_model import LivingSelfModelError, build_living_self_model_report
from zentex.web_console.contracts.nine_questions import NineQuestionsReportPayload
from zentex.web_console.dependencies import (
    get_cli_service,
    get_enhanced_memory_service,
    get_learning_service,
    get_mcp_service,
    get_reflection_service,
    get_task_service,
)

from .q_commons import build_question_report_items, build_question_report_summary_items
from .q_state import _get_nine_question_service, build_trace_id_map, get_nine_question_state, get_or_create_session
from .route_handlers_shared import QUESTION_TITLES, stringify_timestamp
from .trace_builder import build_trace_detail

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_q9_llm_trace_payload_from_table(*, db_path: Any) -> dict[str, Any]:
    from plugins.nine_questions.q9_how_should_i_act.llm_output_table import (
        build_llm_trace_payload_from_table,
    )

    return build_llm_trace_payload_from_table(db_path=db_path)


def _load_q9_llm_tasks(*, db_path: Any, session_id: str, include_payloads: bool) -> dict[str, Any]:
    from plugins.nine_questions.q9_how_should_i_act.llm_output_table import load_q9_llm_tasks

    return load_q9_llm_tasks(db_path=db_path, session_id=session_id, include_payloads=include_payloads)


def _load_q9_llm_task_detail(*, db_path: Any, session_id: str, task_key: str) -> dict[str, Any]:
    from plugins.nine_questions.q9_how_should_i_act.llm_output_table import load_q9_llm_task_detail

    return load_q9_llm_task_detail(db_path=db_path, session_id=session_id, task_key=task_key)


def _merge_trace_payloads(*payloads: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    invocations: list[dict[str, Any]] = []
    seen_invocations: set[str] = set()

    def _has_material(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        return any(
            payload.get(key) not in (None, "", [], {})
            for key in ("provider_name", "model", "prompt", "system_prompt", "context_data", "raw_response", "error_type", "error_message")
        )

    def _invocation_key(payload: dict[str, Any]) -> str:
        content_key = {
            "invocation_phase": payload.get("invocation_phase"),
            "prompt": payload.get("prompt"),
            "raw_response": payload.get("raw_response"),
        }
        if any(value not in (None, "", [], {}) for value in content_key.values()):
            return json.dumps(content_key, ensure_ascii=False, sort_keys=True, default=str)
        return str(payload.get("request_id") or payload.get("decision_id") or json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))

    def _append_invocation(payload: Any) -> None:
        if not isinstance(payload, dict) or not _has_material(payload):
            return
        key = _invocation_key(payload)
        if key in seen_invocations:
            return
        seen_invocations.add(key)
        invocations.append(payload)

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        raw_invocations = payload.get("invocations")
        if isinstance(raw_invocations, list):
            for invocation in raw_invocations:
                _append_invocation(invocation)
        elif _has_material(payload):
            _append_invocation(payload)
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                nested = dict(existing)
                for nested_key, nested_value in value.items():
                    if nested_value in (None, "", [], {}):
                        continue
                    if nested.get(nested_key) in (None, "", [], {}):
                        nested[nested_key] = nested_value
                merged[key] = nested
            elif existing in (None, "", [], {}):
                merged[key] = value
    if invocations:
        merged["invocations"] = invocations
        merged["token_usage"] = {
            "input_tokens": sum(int((item.get("token_usage") or {}).get("input_tokens") or 0) for item in invocations),
            "output_tokens": sum(int((item.get("token_usage") or {}).get("output_tokens") or 0) for item in invocations),
            "total_tokens": sum(int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in invocations),
        }
        elapsed_values = [int(item.get("elapsed_ms") or 0) for item in invocations]
        if any(elapsed_values):
            merged["elapsed_ms"] = sum(elapsed_values)
    return merged


def _module_output_data(module_payload: Any) -> dict[str, Any]:
    if not isinstance(module_payload, dict):
        return {}
    data = module_payload.get("data")
    if isinstance(data, dict):
        return data
    return module_payload


def _build_q8_module_llm_trace_payload(modules_payload: Any) -> dict[str, Any]:
    modules_root = modules_payload.get("modules") if isinstance(modules_payload, dict) else {}
    modules_root = modules_root if isinstance(modules_root, dict) else {}
    invocations: list[dict[str, Any]] = []

    for module_id, input_key, output_key, phase in (
        (
            "q8_internal_task_generation",
            "q8_internal_llm_input",
            "q8_internal_llm_output",
            "nine_question_q8_internal_decision",
        ),
        (
            "q8_external_task_generation",
            "q8_external_llm_input",
            "q8_external_llm_output",
            "nine_question_q8_external_decision",
        ),
    ):
        module_payload = modules_root.get(module_id)
        module_data = _module_output_data(module_payload)
        llm_input = module_data.get(input_key)
        llm_input = llm_input if isinstance(llm_input, dict) else {}
        llm_output = module_data.get(output_key)
        llm_output = llm_output if isinstance(llm_output, dict) else {}
        if not llm_input and not llm_output:
            continue
        caller_context = llm_input.get("caller_context")
        caller_context = caller_context if isinstance(caller_context, dict) else {}
        invocations.append(
            {
                "system_prompt": llm_input.get("system_prompt"),
                "prompt": llm_input.get("prompt"),
                "source_module": caller_context.get("source_module") or module_id,
                "invocation_phase": caller_context.get("invocation_phase") or phase,
                "question_driver_refs": caller_context.get("question_driver_refs") or ["我现在应该做什么"],
                "context_data": llm_input.get("context") if isinstance(llm_input.get("context"), dict) else {},
                "raw_response": llm_output or None,
                "token_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
                "elapsed_ms": 0,
            }
        )

    if not invocations:
        return {}
    return {
        "question_id": "q8",
        "source_module": "q8_module_llm_io_readback",
        "invocation_phase": "nine_question_q8_internal_external_llm_io_readback",
        "invocations": invocations,
    }


def _first_non_empty_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _parse_lens_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_PHASE_A_LENSES
    return tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def _parse_phase_b_lens_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_REQUIRED_LENSES
    return tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def _get_llm_service(request: Request) -> Any:
    candidate = getattr(request.app.state, "llm_service", None)
    if candidate is not None and callable(getattr(candidate, "generate_json", None)):
        return candidate
    from zentex.llm.service import get_service as get_llm_service

    return get_llm_service()


@router.get("/nine-questions/status", response_model=NineQuestionsReportPayload)
async def get_nine_questions_status(request: Request, include_questions: bool = Query(False)):
    started = time.monotonic()
    session = await get_or_create_session(request)
    service = _get_nine_question_service(request)
    state = await service.get_state_metadata()
    questions = []
    if include_questions:
        questions = await build_question_report_items(
            request=request,
            state=state,
            include_trace_detail=False,
        )
    logger.info(
        "[nine-questions] status query complete include_questions=%s question_count=%d elapsed=%.3fs",
        include_questions,
        len(questions),
        time.monotonic() - started,
    )
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=stringify_timestamp((state.get("last_updated_at") or state.get("updated_at")) if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids=build_trace_id_map(state, questions),
    )


@router.get("/nine-questions/latest-report", response_model=NineQuestionsReportPayload)
async def get_latest_nine_questions_report(request: Request):
    started = time.monotonic()
    service = _get_nine_question_service(request)
    state = await service.get_state_metadata()
    questions = await build_question_report_summary_items(
        request=request,
        state=state,
    )
    logger.info(
        "[nine-questions] latest report query complete question_count=%d elapsed=%.3fs",
        len(questions),
        time.monotonic() - started,
    )
    return NineQuestionsReportPayload(
        last_turn_id="",
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=stringify_timestamp((state.get("last_updated_at") or state.get("updated_at")) if isinstance(state, dict) else getattr(state, "updated_at", None)),
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


@router.get("/nine-questions/objectives")
async def get_nine_questions_objectives(request: Request):
    await get_or_create_session(request)
    service = _get_nine_question_service(request)
    snapshot_map = await service.get_snapshot_map()
    engine = NineQDrivenObjectiveEngine()
    try:
        export = engine.derive_profiles(snapshot_map)
    except ObjectiveProfileMissingError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "nine_question_objective_profiles_incomplete",
                "missing_sources": exc.missing_sources,
            },
        ) from exc
    boundary_inputs = _objective_boundary_inputs(snapshot_map)
    violations = engine.check_hard_boundary_violation(
        export,
        non_bypassable_constraints=boundary_inputs["non_bypassable_constraints"],
        forbidden_directions=boundary_inputs["forbidden_directions"],
        identity_locked_fields=boundary_inputs["identity_locked_fields"],
    )
    payload = export.model_dump(mode="json")
    payload["hard_boundary_check"] = {
        "status": "blocked" if violations else "passed",
        "violation_count": len(violations),
        "non_bypassable_constraints_checked": boundary_inputs["non_bypassable_constraints"],
        "forbidden_directions_checked": boundary_inputs["forbidden_directions"],
        "identity_locked_fields_checked": boundary_inputs["identity_locked_fields"],
        "violations": [violation.model_dump(mode="json") for violation in violations],
    }
    return payload


def _objective_boundary_inputs(snapshot_map: dict[str, dict]) -> dict[str, list[str]]:
    q2 = snapshot_map.get("q2") if isinstance(snapshot_map.get("q2"), dict) else {}
    context_updates = q2.get("context_updates") if isinstance(q2.get("context_updates"), dict) else {}
    result = q2.get("result") if isinstance(q2.get("result"), dict) else {}
    identity = (
        context_updates.get("identity_kernel_snapshot")
        or result.get("identity_kernel_snapshot")
        or context_updates.get("identity_kernel")
        or result.get("identity_kernel")
        or {}
    )
    identity = identity if isinstance(identity, dict) else {}
    continuity_lock = identity.get("continuity_lock") if isinstance(identity.get("continuity_lock"), dict) else {}
    return {
        "non_bypassable_constraints": _string_list(identity.get("non_bypassable_constraints")),
        "forbidden_directions": _string_list(identity.get("forbidden_directions")),
        "identity_locked_fields": _string_list(continuity_lock.get("locked_fields")),
    }


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


@router.get("/nine-questions/q8/replay-integrity")
async def get_q8_replay_integrity(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    require_writebacks: bool = Query(default=False),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_replay_integrity_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            require_writebacks=require_writebacks,
            reflection_service=get_reflection_service(request) if require_writebacks else None,
            memory_service=get_enhanced_memory_service(request) if require_writebacks else None,
            learning_service=get_learning_service(request) if require_writebacks else None,
        )
    except Q8ReplayIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_replay_integrity_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/prompt-v2-gate")
async def get_q8_prompt_v2_gate(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_replay_count: int = Query(default=DEFAULT_EXPECTED_REPLAY_COUNT, ge=1),
    min_prompt_reduction_rate: float = Query(default=DEFAULT_MIN_PROMPT_REDUCTION_RATE, ge=0, le=1),
    max_average_llm_calls: float = Query(default=DEFAULT_MAX_AVERAGE_LLM_CALLS, gt=0),
    min_latency_reduction_rate: float = Query(default=DEFAULT_MIN_LATENCY_REDUCTION_RATE, ge=0, le=1),
    min_token_reduction_rate: float = Query(default=DEFAULT_MIN_TOKEN_REDUCTION_RATE, ge=0, le=1),
    min_quality_delta: float = Query(default=DEFAULT_MIN_QUALITY_DELTA, ge=-1, le=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_prompt_v2_gate_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_replay_count=expected_replay_count,
            min_prompt_reduction_rate=min_prompt_reduction_rate,
            max_average_llm_calls=max_average_llm_calls,
            min_latency_reduction_rate=min_latency_reduction_rate,
            min_token_reduction_rate=min_token_reduction_rate,
            min_quality_delta=min_quality_delta,
        )
    except Q8PromptV2GateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_prompt_v2_gate_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/prompt-contracts")
async def get_prompt_contracts():
    summary = build_contract_summary()
    if summary["consistency_errors"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "prompt_contract_consistency_failed",
                "failures": summary["consistency_errors"],
            },
        )
    return summary


@router.get("/nine-questions/plan/completion-gate")
async def get_plan_completion_gate(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_generated_count: int = Query(default=1, ge=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_plan_completion_gate_report(
            task_service=get_task_service(request),
            learning_service=get_learning_service(request),
            session_id=resolved_session_id,
            expected_generated_count=expected_generated_count,
        )
    except PlanCompletionGateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_completion_gate_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
                "report": exc.report,
            },
        ) from exc


@router.get("/nine-questions/plan/evidence-manifests")
async def get_plan_evidence_manifests(request: Request):
    try:
        return build_plan_evidence_summary(learning_service=get_learning_service(request))
    except PlanEvidenceRegistryError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_evidence_summary_failed",
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/plan/execution-evidence")
async def get_plan_execution_evidence(request: Request):
    try:
        return build_plan_execution_evidence_summary(learning_service=get_learning_service(request))
    except PlanExecutionEvidenceError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_execution_evidence_summary_failed",
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/plan/remaining-work")
async def get_plan_remaining_work(
    request: Request,
    require_complete: bool = Query(default=False),
):
    try:
        if require_complete:
            return assert_plan_remaining_work_complete(learning_service=get_learning_service(request))
        return build_plan_remaining_work_report(learning_service=get_learning_service(request))
    except (PlanEvidenceRegistryError, PlanExecutionEvidenceError, PlanRemainingWorkError) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plan_remaining_work_not_complete",
                "failures": getattr(exc, "failures", [{"reason": "plan_remaining_work_failed"}]),
                "report": getattr(exc, "report", None),
            },
        ) from exc


@router.get("/nine-questions/q8/phase-a-observation")
async def get_q8_phase_a_observation(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_a_observation_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
        )
    except Q8PhaseAObservationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_a_observation_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-a-lens-distribution")
async def get_q8_phase_a_lens_distribution(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    required_lenses: str | None = Query(default=None, min_length=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_a_lens_distribution_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            required_lenses=_parse_lens_csv(required_lenses),
        )
    except Q8PhaseALensDistributionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_a_lens_distribution_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-a-observation-gate")
async def get_q8_phase_a_observation_gate(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    required_lenses: str | None = Query(default=None, min_length=1),
    minimum_manual_reviews: int = Query(default=0, ge=0),
    max_weight_delta: float = Query(default=0.75, ge=0),
    max_obvious_drift_rate: float = Query(default=0.05, ge=0, le=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_a_observation_gate_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            required_lenses=_parse_lens_csv(required_lenses),
            minimum_manual_reviews=minimum_manual_reviews,
            max_weight_delta=max_weight_delta,
            max_obvious_drift_rate=max_obvious_drift_rate,
        )
    except Q8PhaseAObservationGateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_a_observation_gate_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-a-exit-gate")
async def get_q8_phase_a_exit_gate(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    required_lenses: str | None = Query(default=None, min_length=1),
    minimum_manual_reviews: int = Query(default=0, ge=0),
    max_weight_delta: float = Query(default=0.75, ge=0),
    max_obvious_drift_rate: float = Query(default=0.05, ge=0, le=1),
    max_open_p1_quality_issues: int = Query(default=0, ge=0),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_a_exit_gate_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            required_lenses=_parse_lens_csv(required_lenses),
            minimum_manual_reviews=minimum_manual_reviews,
            max_weight_delta=max_weight_delta,
            max_obvious_drift_rate=max_obvious_drift_rate,
            max_open_p1_quality_issues=max_open_p1_quality_issues,
        )
    except Q8PhaseAExitGateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_a_exit_gate_failed",
                "session_id": resolved_session_id,
                "phase_b_required": True,
                "phase_b_skip_allowed": False,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-b/value-score")
async def get_q8_phase_b_value_score(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    minimum_overall_score: float = Query(default=0.75, ge=0, le=1),
    required_lenses: str | None = Query(default=None, min_length=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_b_value_score_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            minimum_overall_score=minimum_overall_score,
            required_lenses=_parse_phase_b_lens_csv(required_lenses),
        )
    except Q8PhaseBValueScoringError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_b_value_scoring_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-b/llm-value-score")
async def get_q8_phase_b_llm_value_score(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    generation_provider_key: str = Query(..., min_length=1),
    scoring_provider_key: str = Query(..., min_length=1),
    generation_model: str | None = Query(default=None, min_length=1),
    scoring_model: str | None = Query(default=None, min_length=1),
    expected_review_count: int | None = Query(default=None, ge=0),
    sample_count: int = Query(default=DEFAULT_LLM_SAMPLE_COUNT, ge=1, le=5),
    minimum_semantic_score: float = Query(default=DEFAULT_MINIMUM_SEMANTIC_SCORE, ge=0, le=1),
    minimum_confidence: float = Query(default=DEFAULT_MINIMUM_CONFIDENCE, ge=0, le=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_b_llm_value_score_report(
            task_service=get_task_service(request),
            llm_service=_get_llm_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            generation_provider_key=generation_provider_key,
            scoring_provider_key=scoring_provider_key,
            generation_model=generation_model,
            scoring_model=scoring_model,
            expected_review_count=expected_review_count,
            sample_count=sample_count,
            minimum_semantic_score=minimum_semantic_score,
            minimum_confidence=minimum_confidence,
        )
    except Q8PhaseBLLMValueScoringError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_b_llm_value_scoring_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-b/manual-review-calibration")
async def get_q8_phase_b_manual_review_calibration(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    minimum_review_count: int = Query(default=DEFAULT_MINIMUM_REVIEW_COUNT, ge=0),
    minimum_review_ratio: float = Query(default=DEFAULT_MANUAL_REVIEW_RATIO, ge=0, le=1),
    minimum_agreement_rate: float = Query(default=DEFAULT_MINIMUM_AGREEMENT_RATE, ge=0, le=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_b_manual_review_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            minimum_review_count=minimum_review_count,
            minimum_review_ratio=minimum_review_ratio,
            minimum_agreement_rate=minimum_agreement_rate,
        )
    except Q8PhaseBManualReviewError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_b_manual_review_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-b/production-observation-gate")
async def get_q8_phase_b_production_observation_gate(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    minimum_production_history_count: int = Query(default=100, ge=1),
    minimum_manual_label_count: int = Query(default=100, ge=1),
    minimum_observation_days: int = Query(default=7, ge=1),
    maximum_false_kill_rate: float = Query(default=0.05, ge=0, le=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_q8_phase_b_production_observation_gate_report(
            task_service=get_task_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            minimum_production_history_count=minimum_production_history_count,
            minimum_manual_label_count=minimum_manual_label_count,
            minimum_observation_days=minimum_observation_days,
            maximum_false_kill_rate=maximum_false_kill_rate,
        )
    except Q8PhaseBProductionObservationGateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_b_production_observation_gate_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


@router.get("/nine-questions/q8/phase-m/living-self-model")
async def get_q8_phase_m_living_self_model(
    request: Request,
    session_id: str | None = Query(default=None, min_length=1),
    expected_task_count: int = Query(..., ge=1),
    minimum_signal_count: int = Query(default=2, ge=1),
):
    session = await get_or_create_session(request)
    resolved_session_id = str(session_id or session.session_id)
    try:
        return build_living_self_model_report(
            task_service=get_task_service(request),
            learning_service=get_learning_service(request),
            session_id=resolved_session_id,
            expected_task_count=expected_task_count,
            minimum_signal_count=minimum_signal_count,
        )
    except LivingSelfModelError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "q8_phase_m_living_self_model_failed",
                "session_id": resolved_session_id,
                "failures": exc.failures,
            },
        ) from exc


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

    await get_or_create_session(request)
    service = _get_nine_question_service(request)
    if question_id == "q8":
        modules_payload = await service.get_question_modules(question_id)
        return _build_q8_module_llm_trace_payload(modules_payload)
    if question_id == "q9":
        get_db_path = getattr(service, "sqlite_db_path", None)
        db_path = get_db_path() if callable(get_db_path) else None
        return _build_q9_llm_trace_payload_from_table(db_path=db_path)

    trace_payload = await service.get_question_trace(question_id)
    trace_payload = trace_payload if isinstance(trace_payload, dict) else {}

    raw_payload = await service.get_question_raw(question_id)
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    raw_llm_payload = raw_payload.get("llm_trace_payload")
    raw_llm_payload = raw_llm_payload if isinstance(raw_llm_payload, dict) else {}
    raw_context_updates = raw_payload.get("context_updates")
    raw_context_updates = raw_context_updates if isinstance(raw_context_updates, dict) else {}
    raw_context_llm_payload = raw_context_updates.get("llm_trace_payload")
    raw_context_llm_payload = raw_context_llm_payload if isinstance(raw_context_llm_payload, dict) else {}

    snapshot = await service.get_question_snapshot(question_id) or {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    snapshot_llm_payload = snapshot.get("llm_trace_payload")
    snapshot_llm_payload = snapshot_llm_payload if isinstance(snapshot_llm_payload, dict) else {}

    trace_id = _first_non_empty_string(
        trace_payload.get("trace_id"),
        raw_payload.get("trace_id"),
        snapshot.get("trace_id"),
    )

    merged = _merge_trace_payloads(
        {"trace_id": trace_id, "question_id": question_id},
        trace_payload,
        raw_llm_payload,
        raw_context_llm_payload,
        snapshot_llm_payload,
    )
    return merged


def _q9_state_db_path(request: Request) -> Any:
    service = _get_nine_question_service(request)
    get_db_path = getattr(service, "sqlite_db_path", None)
    return get_db_path() if callable(get_db_path) else None


def _q9_session_candidates(session_id: str) -> list[str]:
    candidates: list[str] = []
    for candidate in ("nq-baseline", session_id, "zentex-default-session"):
        text = str(candidate or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    return candidates


@router.get("/nine-questions/q9/llm-tasks")
async def get_q9_llm_tasks(request: Request):
    session = await get_or_create_session(request)
    db_path = _q9_state_db_path(request)
    last_payload: dict[str, Any] | None = None
    for session_id in _q9_session_candidates(str(session.session_id)):
        payload = _load_q9_llm_tasks(
            db_path=db_path,
            session_id=session_id,
            include_payloads=False,
        )
        last_payload = payload
        if payload.get("tasks"):
            return payload
    return last_payload or _load_q9_llm_tasks(db_path=db_path, session_id="nq-baseline", include_payloads=False)


@router.get("/nine-questions/q9/llm-tasks/{task_key}")
async def get_q9_llm_task_detail(request: Request, task_key: str):
    session = await get_or_create_session(request)
    db_path = _q9_state_db_path(request)
    last_error: RuntimeError | None = None
    for session_id in _q9_session_candidates(str(session.session_id)):
        try:
            return _load_q9_llm_task_detail(
                db_path=db_path,
                session_id=session_id,
                task_key=task_key,
            )
        except RuntimeError as exc:
            if "q9_llm_task_missing" in str(exc):
                last_error = exc
                continue
            raise
    try:
        raise last_error or RuntimeError(f"q9_llm_task_missing:{task_key}")
    except RuntimeError as exc:
        if "q9_llm_task_missing" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.get("/nine-questions/{question_id}/raw")
async def get_nine_question_raw(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_raw")


@router.get("/nine-questions/q2/llm")
async def get_q2_llm(request: Request):
    await get_or_create_session(request)
    service = _get_nine_question_service(request)
    return await service.get_q2_llm_trace()


@router.get("/nine-questions/q2/asset-statistics")
async def get_q2_asset_statistics(request: Request):
    await get_or_create_session(request)
    service = _get_nine_question_service(request)
    app_state = getattr(request.app, "state", None)
    from zentex.external_connectors.service import resolve_service as resolve_external_connector_service
    from zentex.mcp.service import resolve_service as resolve_mcp_service

    candidate_external_connector_service = (
        getattr(app_state, "external_connector_service", None)
        if app_state is not None
        else None
    )
    return await service.get_q2_asset_statistics(
        cli_service=get_cli_service(request),
        mcp_service=resolve_mcp_service(get_mcp_service(request)),
        agent_service=(
            getattr(app_state, "agent_service", None)
            or getattr(app_state, "agent_coordination_service", None)
        )
        if app_state is not None
        else None,
        external_connector_service=resolve_external_connector_service(candidate_external_connector_service),
    )


@router.get("/nine-questions/{question_id}/modules")
async def get_nine_question_modules_endpoint(request: Request, question_id: str):
    return await _get_question_payload(request, question_id, "get_question_modules")


@router.get("/nine-questions/{question_id}")
async def get_nine_question_detail(request: Request, question_id: str):
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    state = await _get_nine_question_service(request).get_state_metadata()
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
