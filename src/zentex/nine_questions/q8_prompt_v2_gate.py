from __future__ import annotations

from collections import Counter
from typing import Any


class Q8PromptV2GateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 prompt V2 gate failed")


DEFAULT_EXPECTED_REPLAY_COUNT = 100
DEFAULT_MIN_PROMPT_REDUCTION_RATE = 0.5
DEFAULT_MAX_AVERAGE_LLM_CALLS = 1.2
DEFAULT_MIN_LATENCY_REDUCTION_RATE = 0.4
DEFAULT_MIN_TOKEN_REDUCTION_RATE = 0.5
DEFAULT_MIN_QUALITY_DELTA = 0.0


def build_q8_prompt_v2_gate_report(
    *,
    task_service: Any,
    session_id: str,
    expected_replay_count: int = DEFAULT_EXPECTED_REPLAY_COUNT,
    min_prompt_reduction_rate: float = DEFAULT_MIN_PROMPT_REDUCTION_RATE,
    max_average_llm_calls: float = DEFAULT_MAX_AVERAGE_LLM_CALLS,
    min_latency_reduction_rate: float = DEFAULT_MIN_LATENCY_REDUCTION_RATE,
    min_token_reduction_rate: float = DEFAULT_MIN_TOKEN_REDUCTION_RATE,
    min_quality_delta: float = DEFAULT_MIN_QUALITY_DELTA,
) -> dict[str, Any]:
    _validate_inputs(
        task_service=task_service,
        session_id=session_id,
        expected_replay_count=expected_replay_count,
        min_prompt_reduction_rate=min_prompt_reduction_rate,
        max_average_llm_calls=max_average_llm_calls,
        min_latency_reduction_rate=min_latency_reduction_rate,
        min_token_reduction_rate=min_token_reduction_rate,
        min_quality_delta=min_quality_delta,
    )
    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(get_task_outcome):
        raise Q8PromptV2GateError([{"reason": "task_service_get_task_outcome_missing"}])

    tasks = _load_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_replay_count:
        failures.append(
            {
                "reason": "q8_prompt_v2_replay_count_mismatch",
                "expected": expected_replay_count,
                "actual": len(tasks),
            }
        )

    receipts: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    environment_counts: Counter[str] = Counter()
    sums = {
        "baseline_prompt_chars": 0.0,
        "current_prompt_chars": 0.0,
        "current_llm_calls": 0.0,
        "baseline_latency_ms": 0.0,
        "current_latency_ms": 0.0,
        "baseline_token_cost": 0.0,
        "current_token_cost": 0.0,
        "baseline_quality_score": 0.0,
        "current_quality_score": 0.0,
    }

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        metrics = _as_dict(metadata.get("q8_prompt_v2_metrics"))
        outcome = _as_dict(get_task_outcome(task_id))
        task_failures = _validate_task_metrics(
            task_id=task_id,
            metadata=metadata,
            metrics=metrics,
            outcome=outcome,
        )
        failures.extend(task_failures)
        if task_failures:
            continue

        baseline_prompt_chars = _positive_float(metrics.get("baseline_prompt_chars"))
        current_prompt_chars = _positive_float(metrics.get("current_prompt_chars"))
        baseline_llm_calls = _positive_float(metrics.get("baseline_llm_calls"))
        current_llm_calls = _positive_float(metrics.get("current_llm_calls"))
        baseline_latency_ms = _positive_float(metrics.get("baseline_latency_ms"))
        current_latency_ms = _positive_float(metrics.get("current_latency_ms"))
        baseline_token_cost = _positive_float(metrics.get("baseline_token_cost"))
        current_token_cost = _positive_float(metrics.get("current_token_cost"))
        baseline_quality_score = _score_float(metrics.get("baseline_quality_score"))
        current_quality_score = _score_float(metrics.get("current_quality_score"))

        source = str(metrics.get("source") or "")
        environment = str(metrics.get("environment") or "")
        source_counts[source] += 1
        environment_counts[environment] += 1
        sums["baseline_prompt_chars"] += baseline_prompt_chars
        sums["current_prompt_chars"] += current_prompt_chars
        sums["current_llm_calls"] += current_llm_calls
        sums["baseline_latency_ms"] += baseline_latency_ms
        sums["current_latency_ms"] += current_latency_ms
        sums["baseline_token_cost"] += baseline_token_cost
        sums["current_token_cost"] += current_token_cost
        sums["baseline_quality_score"] += baseline_quality_score
        sums["current_quality_score"] += current_quality_score

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "q8_trace_id": str(metadata.get("trace_id") or ""),
                "source": source,
                "environment": environment,
                "sample_id": str(metrics.get("sample_id") or ""),
                "baseline_prompt_chars": int(baseline_prompt_chars),
                "current_prompt_chars": int(current_prompt_chars),
                "baseline_llm_calls": baseline_llm_calls,
                "current_llm_calls": current_llm_calls,
                "baseline_latency_ms": int(baseline_latency_ms),
                "current_latency_ms": int(current_latency_ms),
                "baseline_token_cost": baseline_token_cost,
                "current_token_cost": current_token_cost,
                "baseline_quality_score": baseline_quality_score,
                "current_quality_score": current_quality_score,
                "outcome_passed": outcome.get("overall_passed") is True,
                "evidence_uri": str(metrics.get("evidence_uri") or ""),
            }
        )

    replay_count = len(receipts)
    averages = _build_averages(sums, replay_count)
    threshold_results = _build_threshold_results(
        averages=averages,
        min_prompt_reduction_rate=min_prompt_reduction_rate,
        max_average_llm_calls=max_average_llm_calls,
        min_latency_reduction_rate=min_latency_reduction_rate,
        min_token_reduction_rate=min_token_reduction_rate,
        min_quality_delta=min_quality_delta,
    )
    failures.extend(_threshold_failures(threshold_results))
    if replay_count < expected_replay_count:
        failures.append(
            {
                "reason": "q8_prompt_v2_real_replay_count_below_required",
                "required": expected_replay_count,
                "actual": replay_count,
            }
        )

    if failures:
        raise Q8PromptV2GateError(failures)

    return {
        "gate_status": "passed",
        "phase": "v2_phase_0_q8_prompt_engineering",
        "session_id": session_id,
        "expected_replay_count": expected_replay_count,
        "replay_count": replay_count,
        "source_counts": dict(sorted(source_counts.items())),
        "environment_counts": dict(sorted(environment_counts.items())),
        "averages": averages,
        "thresholds": {
            "min_prompt_reduction_rate": min_prompt_reduction_rate,
            "max_average_llm_calls": max_average_llm_calls,
            "min_latency_reduction_rate": min_latency_reduction_rate,
            "min_token_reduction_rate": min_token_reduction_rate,
            "min_quality_delta": min_quality_delta,
        },
        "threshold_results": threshold_results,
        "receipts": receipts,
    }


def _validate_inputs(
    *,
    task_service: Any,
    session_id: str,
    expected_replay_count: int,
    min_prompt_reduction_rate: float,
    max_average_llm_calls: float,
    min_latency_reduction_rate: float,
    min_token_reduction_rate: float,
    min_quality_delta: float,
) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_replay_count <= 0:
        failures.append({"reason": "expected_replay_count_must_be_positive"})
    for name, value in (
        ("min_prompt_reduction_rate", min_prompt_reduction_rate),
        ("min_latency_reduction_rate", min_latency_reduction_rate),
        ("min_token_reduction_rate", min_token_reduction_rate),
    ):
        if not 0 <= value <= 1:
            failures.append({"reason": f"{name}_out_of_range", "value": value})
    if max_average_llm_calls <= 0:
        failures.append({"reason": "max_average_llm_calls_must_be_positive"})
    if not -1 <= min_quality_delta <= 1:
        failures.append({"reason": "min_quality_delta_out_of_range", "value": min_quality_delta})
    if failures:
        raise Q8PromptV2GateError(failures)


def _load_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PromptV2GateError([{"reason": "task_service_list_tasks_missing"}])
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


def _validate_task_metrics(
    *,
    task_id: str,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    outcome: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not metrics:
        return [{"reason": "q8_prompt_v2_metrics_missing", "task_id": task_id}]
    if metrics.get("source") != "production_history":
        failures.append(
            {
                "reason": "q8_prompt_v2_source_invalid",
                "task_id": task_id,
                "source": metrics.get("source"),
            }
        )
    if metrics.get("environment") != "production":
        failures.append(
            {
                "reason": "q8_prompt_v2_environment_invalid",
                "task_id": task_id,
                "environment": metrics.get("environment"),
            }
        )
    if str(metrics.get("q8_trace_id") or "") != str(metadata.get("trace_id") or ""):
        failures.append(
            {
                "reason": "q8_prompt_v2_trace_mismatch",
                "task_id": task_id,
                "task_trace_id": metadata.get("trace_id"),
                "metrics_trace_id": metrics.get("q8_trace_id"),
            }
        )
    for key in (
        "sample_id",
        "evidence_uri",
        "baseline_prompt_chars",
        "current_prompt_chars",
        "baseline_llm_calls",
        "current_llm_calls",
        "baseline_latency_ms",
        "current_latency_ms",
        "baseline_token_cost",
        "current_token_cost",
        "baseline_quality_score",
        "current_quality_score",
    ):
        if metrics.get(key) in (None, "", [], {}):
            failures.append({"reason": "q8_prompt_v2_metric_field_missing", "task_id": task_id, "field": key})
    for key in (
        "baseline_prompt_chars",
        "current_prompt_chars",
        "baseline_llm_calls",
        "current_llm_calls",
        "baseline_latency_ms",
        "current_latency_ms",
        "baseline_token_cost",
        "current_token_cost",
    ):
        if _positive_float(metrics.get(key)) <= 0:
            failures.append({"reason": "q8_prompt_v2_metric_not_positive", "task_id": task_id, "field": key})
    for key in ("baseline_quality_score", "current_quality_score"):
        value = _score_float(metrics.get(key))
        if not 0 <= value <= 1:
            failures.append({"reason": "q8_prompt_v2_quality_score_out_of_range", "task_id": task_id, "field": key})
    if _positive_float(metrics.get("current_prompt_chars")) > 4000:
        failures.append(
            {
                "reason": "q8_prompt_v2_current_prompt_above_hard_cap",
                "task_id": task_id,
                "current_prompt_chars": metrics.get("current_prompt_chars"),
                "hard_cap": 4000,
            }
        )
    if not outcome:
        failures.append({"reason": "q8_prompt_v2_task_outcome_missing", "task_id": task_id})
    elif outcome.get("overall_passed") is not True:
        failures.append(
            {
                "reason": "q8_prompt_v2_task_outcome_not_passed",
                "task_id": task_id,
                "overall_passed": outcome.get("overall_passed"),
            }
        )
    return failures


def _build_averages(sums: dict[str, float], count: int) -> dict[str, float]:
    if count <= 0:
        return {
            "baseline_prompt_chars": 0.0,
            "current_prompt_chars": 0.0,
            "prompt_reduction_rate": 0.0,
            "current_llm_calls": 0.0,
            "baseline_latency_ms": 0.0,
            "current_latency_ms": 0.0,
            "latency_reduction_rate": 0.0,
            "baseline_token_cost": 0.0,
            "current_token_cost": 0.0,
            "token_reduction_rate": 0.0,
            "baseline_quality_score": 0.0,
            "current_quality_score": 0.0,
            "quality_delta": 0.0,
        }
    averages = {key: round(value / count, 6) for key, value in sums.items()}
    averages["prompt_reduction_rate"] = _reduction_rate(
        averages["baseline_prompt_chars"],
        averages["current_prompt_chars"],
    )
    averages["latency_reduction_rate"] = _reduction_rate(
        averages["baseline_latency_ms"],
        averages["current_latency_ms"],
    )
    averages["token_reduction_rate"] = _reduction_rate(
        averages["baseline_token_cost"],
        averages["current_token_cost"],
    )
    averages["quality_delta"] = round(
        averages["current_quality_score"] - averages["baseline_quality_score"],
        6,
    )
    return averages


def _build_threshold_results(
    *,
    averages: dict[str, float],
    min_prompt_reduction_rate: float,
    max_average_llm_calls: float,
    min_latency_reduction_rate: float,
    min_token_reduction_rate: float,
    min_quality_delta: float,
) -> dict[str, dict[str, Any]]:
    return {
        "prompt_reduction": {
            "passed": averages["prompt_reduction_rate"] >= min_prompt_reduction_rate,
            "actual": averages["prompt_reduction_rate"],
            "required": min_prompt_reduction_rate,
        },
        "llm_call_consolidation": {
            "passed": averages["current_llm_calls"] <= max_average_llm_calls,
            "actual": averages["current_llm_calls"],
            "required": max_average_llm_calls,
        },
        "latency_reduction": {
            "passed": averages["latency_reduction_rate"] >= min_latency_reduction_rate,
            "actual": averages["latency_reduction_rate"],
            "required": min_latency_reduction_rate,
        },
        "token_reduction": {
            "passed": averages["token_reduction_rate"] >= min_token_reduction_rate,
            "actual": averages["token_reduction_rate"],
            "required": min_token_reduction_rate,
        },
        "quality_non_regression": {
            "passed": averages["quality_delta"] >= min_quality_delta,
            "actual": averages["quality_delta"],
            "required": min_quality_delta,
        },
    }


def _threshold_failures(threshold_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for name, result in threshold_results.items():
        if result.get("passed") is True:
            continue
        failures.append(
            {
                "reason": f"q8_prompt_v2_{name}_threshold_failed",
                "actual": result.get("actual"),
                "required": result.get("required"),
            }
        )
    return failures


def _reduction_rate(baseline: float, current: float) -> float:
    if baseline <= 0:
        return 0.0
    return round((baseline - current) / baseline, 6)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _positive_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0
