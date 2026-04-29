from __future__ import annotations

from collections import Counter
from typing import Any


class Q8PhaseBValueScoringError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B value scoring check failed")


DEFAULT_REQUIRED_LENSES = ("accuracy", "risk_control", "continuity")
DEFAULT_DIMENSION_WEIGHTS = {
    "outcome_verification": 0.40,
    "evidence_completeness": 0.25,
    "risk_control_alignment": 0.20,
    "lens_activation": 0.15,
}
DEFAULT_SCORER_VERSION = "phase-b-rule-v1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _normalize_required_lenses(required_lenses: tuple[str, ...] | None) -> tuple[str, ...]:
    lenses = required_lenses or DEFAULT_REQUIRED_LENSES
    normalized = tuple(dict.fromkeys(str(lens).strip() for lens in lenses if str(lens).strip()))
    if not normalized:
        raise Q8PhaseBValueScoringError([{"reason": "required_lenses_missing"}])
    return normalized


def _normalized_dimension_weights(dimension_weights: dict[str, Any] | None) -> dict[str, float]:
    raw = dimension_weights or DEFAULT_DIMENSION_WEIGHTS
    weights: dict[str, float] = {}
    failures: list[dict[str, Any]] = []
    for dimension in DEFAULT_DIMENSION_WEIGHTS:
        value = raw.get(dimension)
        try:
            number = float(value)
        except (TypeError, ValueError):
            failures.append({"reason": "dimension_weight_invalid", "dimension": dimension, "value": value})
            continue
        if number < 0:
            failures.append({"reason": "dimension_weight_negative", "dimension": dimension, "value": number})
            continue
        weights[dimension] = number
    if failures:
        raise Q8PhaseBValueScoringError(failures)
    total = sum(weights.values())
    if total <= 0:
        raise Q8PhaseBValueScoringError([{"reason": "dimension_weights_sum_must_be_positive"}])
    return {dimension: value / total for dimension, value in weights.items()}


def _load_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PhaseBValueScoringError([{"reason": "task_service_list_tasks_missing"}])
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


def _score_outcome_verification(outcome: dict[str, Any]) -> tuple[float, list[str]]:
    failures: list[str] = []
    verification_result = _as_dict(outcome.get("verification_result"))
    if outcome.get("overall_passed") is not True:
        failures.append("outcome_not_passed")
    if verification_result.get("overall_passed") is not True:
        failures.append("verification_not_passed")
    if not _as_list(verification_result.get("verifier_results")):
        failures.append("verifier_results_missing")
    return (1.0 if not failures else 0.0), failures


def _score_evidence_completeness(outcome: dict[str, Any], task_id: str) -> tuple[float, list[str]]:
    failures: list[str] = []
    actual_outcome = _as_dict(outcome.get("actual_outcome"))
    if actual_outcome.get("task_id") != task_id:
        failures.append("actual_outcome_task_id_mismatch")
    evidence = actual_outcome.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        failures.append("actual_outcome_evidence_missing")
    if not str(actual_outcome.get("q8_trace_id") or outcome.get("trace_id") or "").strip():
        failures.append("actual_outcome_trace_missing")
    return (1.0 if not failures else 0.0), failures


def _score_risk_control_alignment(task: Any) -> tuple[float, list[str]]:
    failures: list[str] = []
    metadata = _as_dict(_task_value(task, "metadata"))
    phase_a = _as_dict(metadata.get("phase_a_evaluation"))
    risk_level = str(phase_a.get("risk_level") or _as_dict(metadata.get("risk_assessment")).get("risk_level") or "").lower()
    final_priority = str(phase_a.get("final_priority") or _enum_value(_task_value(task, "priority"))).lower()
    applied_rules = [str(item) for item in _as_list(phase_a.get("applied_rules"))]
    if not risk_level:
        failures.append("risk_level_missing")
    if risk_level in {"high", "critical"} and final_priority not in {"high", "critical"}:
        failures.append("high_risk_priority_not_elevated")
    if risk_level in {"high", "critical"} and not any("risk_control" in rule or "conservative" in rule for rule in applied_rules):
        failures.append("high_risk_rule_missing")
    return (1.0 if not failures else 0.0), failures


def _score_lens_activation(task: Any, required_lenses: tuple[str, ...]) -> tuple[float, list[str], list[str]]:
    failures: list[str] = []
    metadata = _as_dict(_task_value(task, "metadata"))
    phase_a = _as_dict(metadata.get("phase_a_evaluation"))
    weights = _as_dict(phase_a.get("evaluation_weights") or _as_dict(metadata.get("evaluation_profile")).get("evaluation_weights"))
    normalized_weights: dict[str, float] = {}
    for lens in required_lenses:
        if lens not in weights:
            failures.append(f"lens_weight_missing:{lens}")
            normalized_weights[lens] = 0.0
            continue
        try:
            normalized_weights[lens] = float(weights.get(lens))
        except (TypeError, ValueError):
            failures.append(f"lens_weight_invalid:{lens}")
            normalized_weights[lens] = 0.0
    positive = {lens: value for lens, value in normalized_weights.items() if value > 0}
    if not positive:
        failures.append("lens_activation_missing")
        return 0.0, failures, []
    max_weight = max(positive.values())
    dominant_lenses = sorted(lens for lens, value in positive.items() if value == max_weight)
    return (1.0 if not failures else 0.0), failures, dominant_lenses


def build_q8_phase_b_value_score_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_overall_score: float = 0.75,
    required_lenses: tuple[str, ...] | None = None,
    dimension_weights: dict[str, Any] | None = None,
    scorer_version: str = DEFAULT_SCORER_VERSION,
) -> dict[str, Any]:
    if task_service is None:
        raise Q8PhaseBValueScoringError([{"reason": "task_service_missing"}])
    if expected_task_count <= 0:
        raise Q8PhaseBValueScoringError([{"reason": "expected_task_count_must_be_positive"}])
    if not 0 <= minimum_overall_score <= 1:
        raise Q8PhaseBValueScoringError([{"reason": "minimum_overall_score_out_of_range"}])

    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(get_task_outcome):
        raise Q8PhaseBValueScoringError([{"reason": "task_service_get_task_outcome_missing"}])

    normalized_required_lenses = _normalize_required_lenses(required_lenses)
    normalized_weights = _normalized_dimension_weights(dimension_weights)
    tasks = _load_tasks(task_service, session_id)

    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    receipts: list[dict[str, Any]] = []
    dominant_lens_counts: Counter[str] = Counter()
    dimension_totals: Counter[str] = Counter()
    low_score_count = 0

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        outcome = _as_dict(get_task_outcome(task_id))
        if not outcome:
            failures.append({"reason": "task_outcome_missing", "task_id": task_id})
            continue

        if metadata.get("source") != "nine_questions.q8":
            failures.append({"reason": "source_mismatch", "task_id": task_id, "source": metadata.get("source")})
        if metadata.get("session_id") != session_id:
            failures.append({"reason": "session_id_mismatch", "task_id": task_id, "session_id": metadata.get("session_id")})
        if outcome.get("trace_id") != metadata.get("trace_id"):
            failures.append(
                {
                    "reason": "outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": metadata.get("trace_id"),
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )

        outcome_score, outcome_failures = _score_outcome_verification(outcome)
        evidence_score, evidence_failures = _score_evidence_completeness(outcome, task_id)
        risk_score, risk_failures = _score_risk_control_alignment(task)
        lens_score, lens_failures, dominant_lenses = _score_lens_activation(task, normalized_required_lenses)

        dimensions = {
            "outcome_verification": outcome_score,
            "evidence_completeness": evidence_score,
            "risk_control_alignment": risk_score,
            "lens_activation": lens_score,
        }
        overall_score = round(sum(dimensions[name] * normalized_weights[name] for name in dimensions), 6)
        for name, value in dimensions.items():
            dimension_totals[name] += value
        for lens in dominant_lenses:
            dominant_lens_counts[lens] += 1

        receipt_failures = {
            "outcome_verification": outcome_failures,
            "evidence_completeness": evidence_failures,
            "risk_control_alignment": risk_failures,
            "lens_activation": lens_failures,
        }
        failed_dimensions = [name for name, items in receipt_failures.items() if items]
        if failed_dimensions:
            failures.append(
                {
                    "reason": "phase_b_task_dimension_failed",
                    "task_id": task_id,
                    "failed_dimensions": failed_dimensions,
                    "dimension_failures": receipt_failures,
                }
            )
        if overall_score < minimum_overall_score:
            low_score_count += 1
            failures.append(
                {
                    "reason": "phase_b_task_score_below_threshold",
                    "task_id": task_id,
                    "overall_score": overall_score,
                    "minimum_overall_score": minimum_overall_score,
                }
            )

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "q8_trace_id": str(metadata.get("trace_id") or ""),
                "q9_trace_id": str(_as_dict(metadata.get("phase_a_evaluation")).get("source_trace_id") or ""),
                "priority": _enum_value(_task_value(task, "priority")),
                "overall_score": overall_score,
                "dimensions": dimensions,
                "dimension_failures": receipt_failures,
                "dominant_lenses": dominant_lenses,
                "outcome_passed": outcome.get("overall_passed") is True,
            }
        )

    if failures:
        raise Q8PhaseBValueScoringError(failures)

    denominator = max(len(receipts), 1)
    return {
        "value_score_status": "passed",
        "session_id": session_id,
        "scorer_version": scorer_version,
        "scorer_layer": "phase_b_rule_based",
        "expected_task_count": expected_task_count,
        "scored_task_count": len(receipts),
        "minimum_overall_score": minimum_overall_score,
        "low_score_count": low_score_count,
        "average_overall_score": round(sum(receipt["overall_score"] for receipt in receipts) / denominator, 6),
        "average_dimension_scores": {
            name: round(dimension_totals[name] / denominator, 6)
            for name in sorted(DEFAULT_DIMENSION_WEIGHTS)
        },
        "dominant_lens_counts": {lens: dominant_lens_counts.get(lens, 0) for lens in normalized_required_lenses},
        "dimension_weights": normalized_weights,
        "required_lenses": list(normalized_required_lenses),
        "receipts": receipts,
    }
