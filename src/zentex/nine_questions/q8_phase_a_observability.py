from __future__ import annotations

from collections import Counter
from typing import Any


class Q8PhaseAObservationError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase A observation check failed")


class Q8PhaseALensDistributionError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase A lens distribution check failed")


class Q8PhaseAObservationGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase A observation gate check failed")


class Q8PhaseAExitGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase A exit gate check failed")


DEFAULT_PHASE_A_LENSES = ("accuracy", "risk_control", "continuity", "speed", "creativity")
VALID_MANUAL_REVIEW_LABELS = {"excellent", "good", "acceptable", "minor_issue", "bad"}
BLOCKING_QUALITY_ISSUE_SEVERITIES = {"p0", "p1"}
OPEN_QUALITY_ISSUE_STATUSES = {"open", "active", "confirmed", "investigating"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _float_or_failure(value: Any, failures: list[dict[str, Any]], *, task_id: str, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        failures.append({"reason": "evaluation_weight_invalid", "task_id": task_id, "field": field, "value": value})
        return 0.0


def _load_q8_session_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PhaseAObservationError([{"reason": "task_service_list_tasks_missing"}])

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


def _phase_a_weights(metadata: dict[str, Any]) -> dict[str, Any]:
    phase_a = _as_dict(metadata.get("phase_a_evaluation"))
    evaluation_profile = _as_dict(metadata.get("evaluation_profile"))
    return _as_dict(phase_a.get("evaluation_weights") or evaluation_profile.get("evaluation_weights"))


def build_q8_phase_a_observation_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
) -> dict[str, Any]:
    if task_service is None:
        raise Q8PhaseAObservationError([{"reason": "task_service_missing"}])
    if expected_task_count <= 0:
        raise Q8PhaseAObservationError([{"reason": "expected_task_count_must_be_positive"}])

    tasks = _load_q8_session_tasks(task_service, session_id)

    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append(
            {
                "reason": "task_count_mismatch",
                "expected": expected_task_count,
                "actual": len(tasks),
            }
        )

    priority_counts: Counter[str] = Counter()
    queue_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    q9_trace_counts: Counter[str] = Counter()
    weight_totals: Counter[str] = Counter()
    receipts: list[dict[str, Any]] = []

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        phase_a = _as_dict(metadata.get("phase_a_evaluation"))
        evaluation_profile = _as_dict(metadata.get("evaluation_profile"))
        weights = _phase_a_weights(metadata)
        actual_priority = _enum_value(_task_value(task, "priority"))
        final_priority = str(phase_a.get("final_priority") or "")
        queue_name = str(metadata.get("queue_name") or "")
        q9_trace_id = str(phase_a.get("source_trace_id") or evaluation_profile.get("source_trace_id") or "")
        applied_rules = [str(item) for item in _as_list(phase_a.get("applied_rules"))]

        if not task_id:
            failures.append({"reason": "task_id_missing", "title": title})
        if metadata.get("source") != "nine_questions.q8":
            failures.append({"reason": "source_mismatch", "task_id": task_id, "source": metadata.get("source")})
        if metadata.get("session_id") != session_id:
            failures.append({"reason": "session_id_mismatch", "task_id": task_id, "session_id": metadata.get("session_id")})
        if phase_a.get("status") != "ready":
            failures.append({"reason": "phase_a_evaluation_not_ready", "task_id": task_id, "status": phase_a.get("status")})
        if not q9_trace_id:
            failures.append({"reason": "q9_trace_id_missing", "task_id": task_id})
        if not final_priority:
            failures.append({"reason": "final_priority_missing", "task_id": task_id})
        elif final_priority != actual_priority:
            failures.append(
                {
                    "reason": "final_priority_mismatch",
                    "task_id": task_id,
                    "metadata_final_priority": final_priority,
                    "actual_priority": actual_priority,
                }
            )
        if not applied_rules:
            failures.append({"reason": "applied_rules_missing", "task_id": task_id})
        if not queue_name:
            failures.append({"reason": "queue_name_missing", "task_id": task_id})

        required_weights = ("accuracy", "risk_control", "continuity")
        normalized_weights: dict[str, float] = {}
        for key in required_weights:
            if key not in weights:
                failures.append({"reason": "evaluation_weight_missing", "task_id": task_id, "field": key})
                normalized_weights[key] = 0.0
                continue
            normalized_weights[key] = _float_or_failure(weights.get(key), failures, task_id=task_id, field=key)
        for key, value in weights.items():
            if key not in normalized_weights:
                normalized_weights[str(key)] = _float_or_failure(value, failures, task_id=task_id, field=str(key))

        priority_counts[actual_priority] += 1
        queue_counts[queue_name] += 1
        q9_trace_counts[q9_trace_id] += 1
        for rule in applied_rules:
            rule_counts[rule] += 1
        for key, value in normalized_weights.items():
            weight_totals[key] += value

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "queue_name": queue_name,
                "task_status": _enum_value(_task_value(task, "status")),
                "base_priority": str(phase_a.get("base_priority") or ""),
                "final_priority": final_priority,
                "actual_priority": actual_priority,
                "risk_level": str(phase_a.get("risk_level") or ""),
                "risk_rank": phase_a.get("risk_rank"),
                "applied_rules": applied_rules,
                "q9_trace_id": q9_trace_id,
                "evaluation_style": str(phase_a.get("evaluation_style") or ""),
                "action_rhythm_hint": str(phase_a.get("action_rhythm_hint") or ""),
                "conservative_mode_triggered": bool(phase_a.get("conservative_mode_triggered")),
                "evaluation_weights": normalized_weights,
            }
        )

    if failures:
        raise Q8PhaseAObservationError(failures)

    denominator = max(len(receipts), 1)
    return {
        "observation_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "observed_task_count": len(receipts),
        "priority_counts": dict(sorted(priority_counts.items())),
        "queue_counts": dict(sorted(queue_counts.items())),
        "applied_rule_counts": dict(sorted(rule_counts.items())),
        "q9_trace_counts": dict(sorted(q9_trace_counts.items())),
        "average_evaluation_weights": {
            key: round(value / denominator, 6)
            for key, value in sorted(weight_totals.items())
        },
        "receipts": receipts,
    }


def build_q8_phase_a_lens_distribution_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    required_lenses: tuple[str, ...] = DEFAULT_PHASE_A_LENSES,
) -> dict[str, Any]:
    if task_service is None:
        raise Q8PhaseALensDistributionError([{"reason": "task_service_missing"}])
    if expected_task_count <= 0:
        raise Q8PhaseALensDistributionError([{"reason": "expected_task_count_must_be_positive"}])

    normalized_required_lenses = tuple(dict.fromkeys(str(lens).strip() for lens in required_lenses if str(lens).strip()))
    if not normalized_required_lenses:
        raise Q8PhaseALensDistributionError([{"reason": "required_lenses_missing"}])

    try:
        tasks = _load_q8_session_tasks(task_service, session_id)
    except Q8PhaseAObservationError as exc:
        raise Q8PhaseALensDistributionError(exc.failures) from exc

    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append(
            {
                "reason": "task_count_mismatch",
                "expected": expected_task_count,
                "actual": len(tasks),
            }
        )

    lens_activation_counts: Counter[str] = Counter()
    lens_positive_counts: Counter[str] = Counter()
    task_status_counts: Counter[str] = Counter()
    q9_trace_counts: Counter[str] = Counter()
    receipts: list[dict[str, Any]] = []

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        phase_a = _as_dict(metadata.get("phase_a_evaluation"))
        weights = _phase_a_weights(metadata)
        task_status = _enum_value(_task_value(task, "status"))
        q9_trace_id = str(phase_a.get("source_trace_id") or _as_dict(metadata.get("evaluation_profile")).get("source_trace_id") or "")
        normalized_weights: dict[str, float] = {}

        if metadata.get("source") != "nine_questions.q8":
            failures.append({"reason": "source_mismatch", "task_id": task_id, "source": metadata.get("source")})
        if metadata.get("session_id") != session_id:
            failures.append({"reason": "session_id_mismatch", "task_id": task_id, "session_id": metadata.get("session_id")})
        if phase_a.get("status") != "ready":
            failures.append({"reason": "phase_a_evaluation_not_ready", "task_id": task_id, "status": phase_a.get("status")})
        if not q9_trace_id:
            failures.append({"reason": "q9_trace_id_missing", "task_id": task_id})

        for lens in normalized_required_lenses:
            if lens not in weights:
                failures.append({"reason": "lens_weight_missing", "task_id": task_id, "lens": lens})
                normalized_weights[lens] = 0.0
                continue
            value = _float_or_failure(weights.get(lens), failures, task_id=task_id, field=lens)
            normalized_weights[lens] = value
            if value > 0:
                lens_positive_counts[lens] += 1

        positive_weights = {lens: value for lens, value in normalized_weights.items() if value > 0}
        if positive_weights:
            max_weight = max(positive_weights.values())
            dominant_lenses = sorted(lens for lens, value in positive_weights.items() if value == max_weight)
        else:
            max_weight = 0.0
            dominant_lenses = []
            failures.append({"reason": "lens_activation_missing", "task_id": task_id})

        for lens in dominant_lenses:
            lens_activation_counts[lens] += 1
        task_status_counts[task_status] += 1
        q9_trace_counts[q9_trace_id] += 1

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "task_status": task_status,
                "queue_name": str(metadata.get("queue_name") or ""),
                "q9_trace_id": q9_trace_id,
                "dominant_lenses": dominant_lenses,
                "max_weight": max_weight,
                "evaluation_weights": normalized_weights,
                "phase_a_status": str(phase_a.get("status") or ""),
            }
        )

    inactive_required_lenses = [lens for lens in normalized_required_lenses if lens_activation_counts.get(lens, 0) <= 0]
    for lens in inactive_required_lenses:
        failures.append({"reason": "required_lens_not_activated", "lens": lens})

    if failures:
        raise Q8PhaseALensDistributionError(failures)

    coverage_ratio = len(normalized_required_lenses) / max(len(normalized_required_lenses), 1)
    return {
        "lens_distribution_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "observed_task_count": len(receipts),
        "required_lenses": list(normalized_required_lenses),
        "lens_activation_counts": {lens: lens_activation_counts.get(lens, 0) for lens in normalized_required_lenses},
        "lens_positive_counts": {lens: lens_positive_counts.get(lens, 0) for lens in normalized_required_lenses},
        "task_status_counts": dict(sorted(task_status_counts.items())),
        "q9_trace_counts": dict(sorted(q9_trace_counts.items())),
        "dominant_lens_coverage_ratio": round(coverage_ratio, 6),
        "receipts": receipts,
    }


def _created_at_sort_value(task: Any) -> str:
    created_at = _task_value(task, "created_at")
    isoformat = getattr(created_at, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(created_at or "")


def build_q8_phase_a_observation_gate_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    required_lenses: tuple[str, ...] = DEFAULT_PHASE_A_LENSES,
    minimum_manual_reviews: int = 0,
    max_weight_delta: float = 0.75,
    max_obvious_drift_rate: float = 0.05,
) -> dict[str, Any]:
    if task_service is None:
        raise Q8PhaseAObservationGateError([{"reason": "task_service_missing"}])
    if minimum_manual_reviews < 0:
        raise Q8PhaseAObservationGateError([{"reason": "minimum_manual_reviews_must_be_non_negative"}])
    if max_weight_delta < 0:
        raise Q8PhaseAObservationGateError([{"reason": "max_weight_delta_must_be_non_negative"}])
    if not 0 <= max_obvious_drift_rate <= 1:
        raise Q8PhaseAObservationGateError([{"reason": "max_obvious_drift_rate_out_of_range"}])

    failures: list[dict[str, Any]] = []
    try:
        lens_report = build_q8_phase_a_lens_distribution_report(
            task_service=task_service,
            session_id=session_id,
            expected_task_count=expected_task_count,
            required_lenses=required_lenses,
        )
    except Q8PhaseALensDistributionError as exc:
        lens_report = None
        failures.extend(exc.failures)

    try:
        tasks = _load_q8_session_tasks(task_service, session_id)
    except Q8PhaseAObservationError as exc:
        raise Q8PhaseAObservationGateError([*failures, *exc.failures]) from exc

    normalized_required_lenses = tuple(dict.fromkeys(str(lens).strip() for lens in required_lenses if str(lens).strip()))
    ordered_tasks = sorted(tasks, key=_created_at_sort_value)
    weight_shift_receipts: list[dict[str, Any]] = []
    max_delta_observed = 0.0

    previous_task: Any | None = None
    previous_weights: dict[str, float] | None = None
    for task in ordered_tasks:
        task_id = str(_task_value(task, "task_id") or "")
        weights = _phase_a_weights(_as_dict(_task_value(task, "metadata")))
        current_weights: dict[str, float] = {}
        for lens in normalized_required_lenses:
            try:
                current_weights[lens] = float(weights.get(lens, 0.0))
            except (TypeError, ValueError):
                current_weights[lens] = 0.0

        if previous_task is not None and previous_weights is not None:
            deltas = {
                lens: round(abs(current_weights.get(lens, 0.0) - previous_weights.get(lens, 0.0)), 6)
                for lens in normalized_required_lenses
            }
            largest_lens = max(deltas, key=deltas.get) if deltas else ""
            largest_delta = deltas.get(largest_lens, 0.0)
            max_delta_observed = max(max_delta_observed, largest_delta)
            receipt = {
                "from_task_id": str(_task_value(previous_task, "task_id") or ""),
                "to_task_id": task_id,
                "largest_lens": largest_lens,
                "largest_delta": largest_delta,
                "deltas": deltas,
            }
            weight_shift_receipts.append(receipt)
            if largest_delta > max_weight_delta:
                failures.append(
                    {
                        "reason": "evaluation_weight_shift_too_large",
                        "from_task_id": receipt["from_task_id"],
                        "to_task_id": task_id,
                        "lens": largest_lens,
                        "delta": largest_delta,
                        "max_allowed": max_weight_delta,
                    }
                )

        previous_task = task
        previous_weights = current_weights

    reviewed_count = 0
    obvious_drift_count = 0
    manual_review_receipts: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        review = _as_dict(metadata.get("phase_a_manual_review"))
        if not review:
            continue
        if review.get("review_status") != "completed":
            continue
        reviewed_count += 1
        reviewer_id = str(review.get("reviewer_id") or "").strip()
        reviewed_at = str(review.get("reviewed_at") or "").strip()
        quality_label = str(review.get("task_quality_label") or "").strip()
        obvious_drift = review.get("obvious_drift")
        if not reviewer_id:
            failures.append({"reason": "manual_review_reviewer_missing", "task_id": task_id})
        if not reviewed_at:
            failures.append({"reason": "manual_review_timestamp_missing", "task_id": task_id})
        if quality_label not in VALID_MANUAL_REVIEW_LABELS:
            failures.append({"reason": "manual_review_quality_label_invalid", "task_id": task_id, "label": quality_label})
        if not isinstance(obvious_drift, bool):
            failures.append({"reason": "manual_review_obvious_drift_invalid", "task_id": task_id, "value": obvious_drift})
            obvious_drift_value = False
        else:
            obvious_drift_value = obvious_drift
        if obvious_drift_value:
            obvious_drift_count += 1
        manual_review_receipts.append(
            {
                "task_id": task_id,
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "task_quality_label": quality_label,
                "obvious_drift": obvious_drift_value,
            }
        )

    if reviewed_count < minimum_manual_reviews:
        failures.append(
            {
                "reason": "manual_review_count_below_minimum",
                "reviewed_count": reviewed_count,
                "minimum_manual_reviews": minimum_manual_reviews,
            }
        )
    drift_rate = round(obvious_drift_count / reviewed_count, 6) if reviewed_count else 0.0
    if reviewed_count and drift_rate > max_obvious_drift_rate:
        failures.append(
            {
                "reason": "manual_review_obvious_drift_rate_too_high",
                "obvious_drift_rate": drift_rate,
                "max_allowed": max_obvious_drift_rate,
            }
        )

    if failures:
        raise Q8PhaseAObservationGateError(failures)

    return {
        "observation_gate_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "observed_task_count": len(tasks),
        "lens_distribution": lens_report,
        "weight_trend": {
            "max_weight_delta_allowed": max_weight_delta,
            "max_weight_delta_observed": round(max_delta_observed, 6),
            "shift_count": len(weight_shift_receipts),
            "receipts": weight_shift_receipts,
        },
        "manual_review": {
            "minimum_manual_reviews": minimum_manual_reviews,
            "reviewed_count": reviewed_count,
            "obvious_drift_count": obvious_drift_count,
            "obvious_drift_rate": drift_rate,
            "max_obvious_drift_rate": max_obvious_drift_rate,
            "receipts": manual_review_receipts,
        },
    }


def _quality_issue_entries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    single_issue = _as_dict(metadata.get("phase_a_quality_issue"))
    if single_issue:
        entries.append(single_issue)
    for item in _as_list(metadata.get("phase_a_quality_issues")):
        issue = _as_dict(item)
        if issue:
            entries.append(issue)
    return entries


def build_q8_phase_a_exit_gate_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    required_lenses: tuple[str, ...] = DEFAULT_PHASE_A_LENSES,
    minimum_manual_reviews: int = 0,
    max_weight_delta: float = 0.75,
    max_obvious_drift_rate: float = 0.05,
    max_open_p1_quality_issues: int = 0,
) -> dict[str, Any]:
    if max_open_p1_quality_issues < 0:
        raise Q8PhaseAExitGateError([{"reason": "max_open_p1_quality_issues_must_be_non_negative"}])

    failures: list[dict[str, Any]] = []
    try:
        observation_gate = build_q8_phase_a_observation_gate_report(
            task_service=task_service,
            session_id=session_id,
            expected_task_count=expected_task_count,
            required_lenses=required_lenses,
            minimum_manual_reviews=minimum_manual_reviews,
            max_weight_delta=max_weight_delta,
            max_obvious_drift_rate=max_obvious_drift_rate,
        )
    except Q8PhaseAObservationGateError as exc:
        observation_gate = None
        failures.extend(exc.failures)

    try:
        tasks = _load_q8_session_tasks(task_service, session_id)
    except Q8PhaseAObservationError as exc:
        raise Q8PhaseAExitGateError([*failures, *exc.failures]) from exc

    open_quality_issue_counts: Counter[str] = Counter()
    quality_issue_receipts: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        for issue in _quality_issue_entries(metadata):
            severity = str(issue.get("severity") or "").strip().lower()
            status = str(issue.get("status") or "").strip().lower()
            issue_type = str(issue.get("issue_type") or "").strip().lower()
            issue_id = str(issue.get("issue_id") or "").strip()
            if issue_type != "task_quality":
                continue
            if severity in BLOCKING_QUALITY_ISSUE_SEVERITIES and status in OPEN_QUALITY_ISSUE_STATUSES:
                open_quality_issue_counts[severity] += 1
                quality_issue_receipts.append(
                    {
                        "task_id": task_id,
                        "title": title,
                        "issue_id": issue_id,
                        "severity": severity,
                        "status": status,
                        "issue_type": issue_type,
                        "summary": str(issue.get("summary") or ""),
                    }
                )

    open_p1_or_p0_count = sum(open_quality_issue_counts.get(severity, 0) for severity in BLOCKING_QUALITY_ISSUE_SEVERITIES)
    if open_p1_or_p0_count > max_open_p1_quality_issues:
        failures.append(
            {
                "reason": "phase_a_open_p1_quality_issue_limit_exceeded",
                "open_p1_quality_issue_count": open_p1_or_p0_count,
                "max_allowed": max_open_p1_quality_issues,
            }
        )

    if failures:
        raise Q8PhaseAExitGateError(failures)

    return {
        "phase_a_exit_status": "passed",
        "session_id": session_id,
        "phase_b_skip_allowed": True,
        "phase_b_required": False,
        "decision_reason": "phase_a_observation_gate_passed_and_no_open_p1_task_quality_issue",
        "observation_gate": observation_gate,
        "quality_issues": {
            "max_open_p1_quality_issues": max_open_p1_quality_issues,
            "open_p1_quality_issue_count": open_p1_or_p0_count,
            "open_quality_issue_counts": {
                severity: open_quality_issue_counts.get(severity, 0)
                for severity in sorted(BLOCKING_QUALITY_ISSUE_SEVERITIES)
            },
            "receipts": quality_issue_receipts,
        },
    }
