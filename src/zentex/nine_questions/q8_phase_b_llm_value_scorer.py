from __future__ import annotations

from statistics import median
from typing import Any

from zentex.foundation.specs.model_provider import ModelProviderCallerContext


class Q8PhaseBLLMValueScoringError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B LLM value scoring check failed")


DEFAULT_LLM_SCORER_VERSION = "phase-b-llm-v1"
DEFAULT_LLM_SAMPLE_COUNT = 3
DEFAULT_MINIMUM_SEMANTIC_SCORE = 0.70
DEFAULT_MINIMUM_CONFIDENCE = 0.50
EDGE_REVIEW_MARKERS = {"edge", "needs_llm", "llm_required", "review", "manual_review"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _load_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PhaseBLLMValueScoringError([{"reason": "task_service_list_tasks_missing"}])
    tasks = list(
        list_tasks(
            metadata_filters={
                "source": "nine_questions.q8",
                "session_id": session_id,
            }
        )
        or []
    )
    tasks.sort(key=lambda item: str(_task_value(item, "title") or ""))
    return tasks


def _review_marker(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("required") is True:
            return "llm_required"
        return str(value.get("decision") or value.get("status") or value.get("reason") or "").strip().lower()
    return str(value or "").strip().lower()


def _requires_llm_review(task: Any) -> bool:
    metadata = _as_dict(_task_value(task, "metadata"))
    candidates = (
        metadata.get("phase_b_llm_review"),
        metadata.get("phase_b_rule_review"),
        metadata.get("phase_b_rule_score"),
        metadata.get("value_score_review"),
    )
    return any(_review_marker(candidate) in EDGE_REVIEW_MARKERS for candidate in candidates)


def _validate_runtime_inputs(
    *,
    task_service: Any,
    llm_service: Any,
    session_id: str,
    expected_task_count: int,
    expected_review_count: int | None,
    scoring_provider_key: str,
    generation_provider_key: str,
    sample_count: int,
    minimum_semantic_score: float,
    minimum_confidence: float,
) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if llm_service is None or not callable(getattr(llm_service, "generate_json", None)):
        failures.append({"reason": "llm_service_generate_json_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if expected_review_count is not None and expected_review_count < 0:
        failures.append({"reason": "expected_review_count_must_not_be_negative"})
    if not str(scoring_provider_key or "").strip():
        failures.append({"reason": "scoring_provider_key_missing"})
    if not str(generation_provider_key or "").strip():
        failures.append({"reason": "generation_provider_key_missing"})
    if str(scoring_provider_key or "").strip() == str(generation_provider_key or "").strip():
        failures.append(
            {
                "reason": "llm_scorer_not_isolated_from_generation",
                "provider_key": str(scoring_provider_key or "").strip(),
            }
        )
    if sample_count <= 0:
        failures.append({"reason": "sample_count_must_be_positive"})
    if not 0 <= minimum_semantic_score <= 1:
        failures.append({"reason": "minimum_semantic_score_out_of_range"})
    if not 0 <= minimum_confidence <= 1:
        failures.append({"reason": "minimum_confidence_out_of_range"})
    if failures:
        raise Q8PhaseBLLMValueScoringError(failures)


def _task_payload(task: Any, outcome: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(_task_value(task, "metadata"))
    contract = _task_value(task, "contract")
    contract_payload = {
        "success_criteria": _as_list(getattr(contract, "success_criteria", None)),
        "acceptance_conditions": _as_list(getattr(contract, "acceptance_conditions", None)),
        "expected_outcome": getattr(contract, "expected_outcome", None),
        "risk_assessment": getattr(contract, "risk_assessment", None),
    }
    return {
        "task_id": str(_task_value(task, "task_id") or ""),
        "title": str(_task_value(task, "title") or ""),
        "description": str(_task_value(task, "description") or ""),
        "priority": _enum_value(_task_value(task, "priority")),
        "status": _enum_value(_task_value(task, "status")),
        "metadata": {
            "trace_id": metadata.get("trace_id"),
            "session_id": metadata.get("session_id"),
            "phase_a_evaluation": metadata.get("phase_a_evaluation"),
            "phase_b_llm_review": metadata.get("phase_b_llm_review"),
            "objective_profile": metadata.get("objective_profile"),
        },
        "contract": contract_payload,
        "outcome": {
            "overall_passed": outcome.get("overall_passed"),
            "trace_id": outcome.get("trace_id"),
            "actual_outcome": outcome.get("actual_outcome"),
            "verification_result": outcome.get("verification_result"),
        },
    }


def _task_prompt_summary(task: Any, outcome: dict[str, Any]) -> str:
    payload = _task_payload(task, outcome)
    metadata = _as_dict(payload.get("metadata"))
    phase_a = _as_dict(metadata.get("phase_a_evaluation"))
    contract = _as_dict(payload.get("contract"))
    outcome_payload = _as_dict(payload.get("outcome"))
    actual_outcome = _as_dict(outcome_payload.get("actual_outcome"))
    verification_result = _as_dict(outcome_payload.get("verification_result"))
    evidence = [str(item) for item in _as_list(actual_outcome.get("evidence"))]
    return "\n".join(
        [
            f"task_id: {payload.get('task_id')}",
            f"title: {payload.get('title')}",
            f"priority: {payload.get('priority')}",
            f"risk_level: {phase_a.get('risk_level') or _as_dict(contract.get('risk_assessment')).get('risk_level')}",
            f"success_criteria: {contract.get('success_criteria')}",
            f"acceptance_conditions: {contract.get('acceptance_conditions')}",
            f"expected_outcome: {contract.get('expected_outcome')}",
            f"outcome_passed: {outcome_payload.get('overall_passed')}",
            f"verification_passed: {verification_result.get('overall_passed')}",
            f"actual_outcome: {actual_outcome}",
            f"evidence: {evidence}",
        ]
    )


def _llm_prompt(task: Any, outcome: dict[str, Any]) -> str:
    return "\n".join(
        [
            "You are an independent value-quality judge for a Q8 task edge case.",
            "Judge whether the task outcome creates concrete user value and stays aligned with the task contract.",
            "Do not reward vague activity. Do not infer missing evidence.",
            "Return JSON with all keys in this schema. Replace placeholder values with your judgment:",
            '{"semantic_score":<number_0_to_1>,"confidence":<number_0_to_1>,"decision":"accept_or_downgrade_or_reject","reason":"short reason","risk_flags":[]}',
            "semantic_score and confidence must be decimal fractions between 0.00 and 1.00, for example 0.82.",
            "Never use 4, 75, percentages, or a 1-5 rating scale.",
            "Allowed decision values are exactly: accept, downgrade, reject.",
            "Do not copy context keys. Do not return an empty object.",
            "Task evidence:",
            _task_prompt_summary(task, outcome),
        ]
    )


def _coerce_score_payload(output: Any, *, task_id: str, sample_index: int) -> dict[str, Any]:
    payload = _as_dict(output)
    failures: list[dict[str, Any]] = []
    try:
        semantic_score = float(payload.get("semantic_score"))
    except (TypeError, ValueError):
        failures.append({"field": "semantic_score", "reason": "llm_score_missing_or_invalid"})
        semantic_score = 0.0
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        failures.append({"field": "confidence", "reason": "llm_confidence_missing_or_invalid"})
        confidence = 0.0

    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"accept", "downgrade", "reject"}:
        failures.append({"field": "decision", "reason": "llm_decision_invalid", "value": decision})
    if not 0 <= semantic_score <= 1:
        failures.append({"field": "semantic_score", "reason": "llm_score_out_of_range", "value": semantic_score})
    if not 0 <= confidence <= 1:
        failures.append({"field": "confidence", "reason": "llm_confidence_out_of_range", "value": confidence})

    if failures:
        raise Q8PhaseBLLMValueScoringError(
            [
                {
                    "reason": "llm_score_payload_invalid",
                    "task_id": task_id,
                    "sample_index": sample_index,
                    "failures": failures,
                    "raw_output": payload,
                }
            ]
        )
    return {
        "semantic_score": round(semantic_score, 6),
        "confidence": round(confidence, 6),
        "decision": decision,
        "reason": str(payload.get("reason") or "").strip(),
        "risk_flags": [str(item) for item in _as_list(payload.get("risk_flags"))],
    }


def _median_sample(
    samples: list[dict[str, Any]],
    *,
    minimum_semantic_score: float,
    minimum_confidence: float,
) -> dict[str, Any]:
    median_score = round(float(median(sample["semantic_score"] for sample in samples)), 6)
    median_confidence = round(float(median(sample["confidence"] for sample in samples)), 6)
    closest = min(samples, key=lambda item: abs(float(item["semantic_score"]) - median_score))
    if median_score >= minimum_semantic_score and median_confidence >= minimum_confidence:
        decision = "accept"
    else:
        decision = str(closest["decision"])
    return {
        "semantic_score": median_score,
        "confidence": median_confidence,
        "decision": decision,
        "reason": closest.get("reason") or "",
        "risk_flags": closest.get("risk_flags") or [],
    }


def build_q8_phase_b_llm_value_score_report(
    *,
    task_service: Any,
    llm_service: Any,
    session_id: str,
    expected_task_count: int,
    generation_provider_key: str,
    scoring_provider_key: str,
    generation_model: str | None = None,
    scoring_model: str | None = None,
    expected_review_count: int | None = None,
    sample_count: int = DEFAULT_LLM_SAMPLE_COUNT,
    minimum_semantic_score: float = DEFAULT_MINIMUM_SEMANTIC_SCORE,
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
    scorer_version: str = DEFAULT_LLM_SCORER_VERSION,
) -> dict[str, Any]:
    _validate_runtime_inputs(
        task_service=task_service,
        llm_service=llm_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
        expected_review_count=expected_review_count,
        scoring_provider_key=scoring_provider_key,
        generation_provider_key=generation_provider_key,
        sample_count=sample_count,
        minimum_semantic_score=minimum_semantic_score,
        minimum_confidence=minimum_confidence,
    )

    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(get_task_outcome):
        raise Q8PhaseBLLMValueScoringError([{"reason": "task_service_get_task_outcome_missing"}])

    tasks = _load_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    review_tasks = [task for task in tasks if _requires_llm_review(task)]
    if expected_review_count is not None and len(review_tasks) != expected_review_count:
        failures.append(
            {
                "reason": "llm_review_count_mismatch",
                "expected": expected_review_count,
                "actual": len(review_tasks),
            }
        )

    receipts: list[dict[str, Any]] = []
    if failures:
        raise Q8PhaseBLLMValueScoringError(failures)

    for task in review_tasks:
        task_id = str(_task_value(task, "task_id") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        outcome = _as_dict(get_task_outcome(task_id))
        if not outcome:
            failures.append({"reason": "task_outcome_missing", "task_id": task_id})
            continue
        if outcome.get("trace_id") != metadata.get("trace_id"):
            failures.append(
                {
                    "reason": "outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": metadata.get("trace_id"),
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )
            continue

        samples: list[dict[str, Any]] = []
        for sample_index in range(sample_count):
            try:
                call = llm_service.generate_json(
                    prompt=_llm_prompt(task, outcome),
                    context={
                        "scoring_scope": "q8_phase_b_layer_2_edge_case",
                        "task_id": task_id,
                    },
                    caller_context=ModelProviderCallerContext(
                        source_module="zentex.nine_questions.q8_phase_b_llm_value_scorer",
                        invocation_phase="q8_phase_b_layer_2_llm_value_scoring",
                        question_driver_refs=["Q8", "PHASE_B", "LAYER_2_LLM"],
                        decision_id=f"q8-phase-b-llm:{session_id}:{task_id}:{sample_index}",
                        trace_id=str(metadata.get("trace_id") or session_id),
                    ),
                    source_module="zentex.nine_questions.q8_phase_b_llm_value_scorer",
                    invocation_phase="q8_phase_b_layer_2_llm_value_scoring",
                    decision_id=f"q8-phase-b-llm:{session_id}:{task_id}:{sample_index}",
                    model_provider=scoring_provider_key,
                    model=scoring_model,
                    temperature=0.0,
                    max_output_tokens=256,
                    metadata={
                        "strict_real_runtime": True,
                        "q8_phase_b_layer": "llm_value_scoring",
                        "generation_provider_key": generation_provider_key,
                        "generation_model": generation_model,
                        "request_timeout_seconds": 60,
                    },
                )
            except Exception as exc:
                failures.append(
                    {
                        "reason": "llm_scoring_invocation_failed",
                        "task_id": task_id,
                        "sample_index": sample_index,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )
                continue
            sample = _coerce_score_payload(call.output, task_id=task_id, sample_index=sample_index)
            sample["provider_key"] = str(call.provider_key or "")
            sample["model"] = str(call.model or "")
            sample["total_tokens"] = int(getattr(call.usage, "total_tokens", 0) or 0)
            samples.append(sample)

        if len(samples) != sample_count:
            continue

        aggregate = _median_sample(
            samples,
            minimum_semantic_score=minimum_semantic_score,
            minimum_confidence=minimum_confidence,
        )
        receipt_failures: list[dict[str, Any]] = []
        if aggregate["semantic_score"] < minimum_semantic_score:
            receipt_failures.append(
                {
                    "reason": "llm_semantic_score_below_threshold",
                    "semantic_score": aggregate["semantic_score"],
                    "minimum_semantic_score": minimum_semantic_score,
                }
            )
        if aggregate["confidence"] < minimum_confidence:
            receipt_failures.append(
                {
                    "reason": "llm_confidence_below_threshold",
                    "confidence": aggregate["confidence"],
                    "minimum_confidence": minimum_confidence,
                }
            )
        if aggregate["decision"] == "reject":
            receipt_failures.append({"reason": "llm_decision_rejected", "decision": aggregate["decision"]})
        if receipt_failures:
            failures.append(
                {
                    "reason": "llm_value_score_failed",
                    "task_id": task_id,
                    "failures": receipt_failures,
                }
            )

        receipts.append(
            {
                "task_id": task_id,
                "title": str(_task_value(task, "title") or ""),
                "q8_trace_id": str(metadata.get("trace_id") or ""),
                "q9_trace_id": str(_as_dict(metadata.get("phase_a_evaluation")).get("source_trace_id") or ""),
                "priority": _enum_value(_task_value(task, "priority")),
                "semantic_score": aggregate["semantic_score"],
                "confidence": aggregate["confidence"],
                "decision": aggregate["decision"],
                "reason": aggregate["reason"],
                "risk_flags": aggregate["risk_flags"],
                "provider_key": samples[0]["provider_key"],
                "model": samples[0]["model"],
                "samples": samples,
                "outcome_passed": outcome.get("overall_passed") is True,
            }
        )

    if failures:
        raise Q8PhaseBLLMValueScoringError(failures)

    return {
        "value_score_status": "passed",
        "session_id": session_id,
        "scorer_version": scorer_version,
        "scorer_layer": "phase_b_llm",
        "generation_provider_key": generation_provider_key,
        "generation_model": generation_model,
        "scoring_provider_key": scoring_provider_key,
        "scoring_model": scoring_model or (receipts[0]["model"] if receipts else None),
        "expected_task_count": expected_task_count,
        "task_count": len(tasks),
        "expected_review_count": expected_review_count,
        "reviewed_task_count": len(receipts),
        "sample_count": sample_count,
        "minimum_semantic_score": minimum_semantic_score,
        "minimum_confidence": minimum_confidence,
        "average_semantic_score": round(
            sum(receipt["semantic_score"] for receipt in receipts) / max(len(receipts), 1),
            6,
        ),
        "average_confidence": round(
            sum(receipt["confidence"] for receipt in receipts) / max(len(receipts), 1),
            6,
        ),
        "receipts": receipts,
    }
