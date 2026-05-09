from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zentex.tasks.models import TaskPriority, TaskStatus


class Q8PhaseBRealtimeGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B realtime value gate failed")


@dataclass(frozen=True)
class Q8PhaseBRealtimeGateDecision:
    decision: str
    original_priority: TaskPriority
    final_priority: TaskPriority
    original_status: TaskStatus
    final_status: TaskStatus
    overall_score: float
    dimensions: dict[str, float]
    dimension_failures: dict[str, list[str]]
    threshold: dict[str, float]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "decision": self.decision,
            "original_priority": self.original_priority.value,
            "final_priority": self.final_priority.value,
            "original_status": self.original_status.value,
            "final_status": self.final_status.value,
            "overall_score": self.overall_score,
            "dimensions": dict(self.dimensions),
            "dimension_failures": {
                key: list(value) for key, value in self.dimension_failures.items()
            },
            "threshold": dict(self.threshold),
        }


VALUE_MECHANISM_KEYWORDS = (
    "节省",
    "避免",
    "消除",
    "减少",
    "自动化",
    "阻断",
    "降低",
    "验证",
    "量化",
    "可追踪",
    "save",
    "avoid",
    "reduce",
    "automate",
    "verify",
    "block",
    "prevent",
    "measure",
)


def evaluate_q8_phase_b_realtime_task_gate(
    *,
    task: dict[str, Any],
    target_status: TaskStatus,
    base_priority: TaskPriority,
    accept_threshold: float = 0.75,
    reject_threshold: float = 0.4,
) -> Q8PhaseBRealtimeGateDecision:
    _validate_thresholds(accept_threshold=accept_threshold, reject_threshold=reject_threshold)

    title_score, title_failures = _score_title(task)
    mechanism_score, mechanism_failures = _score_value_mechanism(task)
    acceptance_score, acceptance_failures = _score_acceptance_contract(task)
    risk_score, risk_failures = _score_risk_control(task)

    dimensions = {
        "title_specificity": title_score,
        "value_mechanism": mechanism_score,
        "acceptance_contract": acceptance_score,
        "risk_control": risk_score,
    }
    failures = {
        "title_specificity": title_failures,
        "value_mechanism": mechanism_failures,
        "acceptance_contract": acceptance_failures,
        "risk_control": risk_failures,
    }
    overall_score = round(sum(dimensions.values()) / len(dimensions), 6)

    if overall_score < reject_threshold:
        decision = "reject"
        final_status = TaskStatus.BLOCKED
        final_priority = TaskPriority.LOW
    elif overall_score < accept_threshold:
        decision = "downgrade"
        final_status = target_status
        final_priority = _downgrade_priority(base_priority)
    else:
        decision = "accept"
        final_status = target_status
        final_priority = base_priority

    return Q8PhaseBRealtimeGateDecision(
        decision=decision,
        original_priority=base_priority,
        final_priority=final_priority,
        original_status=target_status,
        final_status=final_status,
        overall_score=overall_score,
        dimensions=dimensions,
        dimension_failures=failures,
        threshold={
            "accept_threshold": accept_threshold,
            "reject_threshold": reject_threshold,
        },
    )


def resolve_phase_b_realtime_gate_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    config = raw_config if isinstance(raw_config, dict) else {}
    enabled = bool(config.get("enabled", False))
    accept_threshold = float(config.get("accept_threshold", 0.75))
    reject_threshold = float(config.get("reject_threshold", 0.4))
    _validate_thresholds(accept_threshold=accept_threshold, reject_threshold=reject_threshold)
    return {
        "enabled": enabled,
        "accept_threshold": accept_threshold,
        "reject_threshold": reject_threshold,
    }


def _validate_thresholds(*, accept_threshold: float, reject_threshold: float) -> None:
    failures: list[dict[str, Any]] = []
    if not 0 <= reject_threshold <= 1:
        failures.append({"reason": "reject_threshold_out_of_range", "value": reject_threshold})
    if not 0 <= accept_threshold <= 1:
        failures.append({"reason": "accept_threshold_out_of_range", "value": accept_threshold})
    if not failures and reject_threshold > accept_threshold:
        failures.append(
            {
                "reason": "reject_threshold_above_accept_threshold",
                "reject_threshold": reject_threshold,
                "accept_threshold": accept_threshold,
            }
        )
    if failures:
        raise Q8PhaseBRealtimeGateError(failures)


def _score_title(task: dict[str, Any]) -> tuple[float, list[str]]:
    title = str(task.get("title") or "").strip()
    failures: list[str] = []
    if len(title) < 10:
        failures.append("title_too_short")
    if len(title) > 300:
        failures.append("title_too_long")
    return (1.0 if not failures else 0.0), failures


def _score_value_mechanism(task: dict[str, Any]) -> tuple[float, list[str]]:
    text = " ".join(
        [
            str(task.get("title") or ""),
            str(task.get("reason") or ""),
            str(task.get("value_justification") or ""),
            " ".join(str(item) for item in _as_list(task.get("success_criteria"))),
            " ".join(str(item) for item in _as_list(task.get("acceptance_conditions"))),
        ]
    ).lower()
    if any(keyword.lower() in text for keyword in VALUE_MECHANISM_KEYWORDS):
        return 1.0, []
    return 0.0, ["value_mechanism_missing"]


def _score_acceptance_contract(task: dict[str, Any]) -> tuple[float, list[str]]:
    if _as_list(task.get("success_criteria")) and (
        _as_list(task.get("acceptance_conditions")) or _as_dict(task.get("expected_outcome"))
    ):
        return 1.0, []
    return 0.0, ["acceptance_contract_incomplete"]


def _score_risk_control(task: dict[str, Any]) -> tuple[float, list[str]]:
    risk = str(_as_dict(task.get("risk_assessment")).get("risk_level") or "").lower()
    if risk not in {"high", "critical"}:
        return 1.0, []
    controls = _as_list(task.get("pause_conditions")) + _as_list(task.get("escalation_conditions"))
    text = " ".join(str(item) for item in controls).lower()
    if controls and any(keyword in text for keyword in ("risk", "evidence", "verify", "approval", "escalat", "风险", "证据", "验证", "审批", "升级")):
        return 1.0, []
    return 0.0, ["high_risk_control_missing"]


def _downgrade_priority(priority: TaskPriority) -> TaskPriority:
    if priority == TaskPriority.CRITICAL:
        return TaskPriority.HIGH
    if priority == TaskPriority.HIGH:
        return TaskPriority.MEDIUM
    if priority == TaskPriority.MEDIUM:
        return TaskPriority.LOW
    return TaskPriority.LOW


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
