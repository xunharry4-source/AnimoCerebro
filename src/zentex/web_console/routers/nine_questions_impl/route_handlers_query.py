from __future__ import annotations

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
    get_enhanced_memory_service,
    get_learning_service,
    get_reflection_service,
    get_task_service,
)

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
