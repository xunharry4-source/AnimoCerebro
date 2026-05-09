from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from zentex.nine_questions.q8_evaluation_lens_mapper import enrich_evaluation_profile_with_meta_value_lenses
from zentex.tasks.models import TaskPriority


class Q8EvaluationProfileError(RuntimeError):
    def __init__(self, missing_sources: list[str]) -> None:
        self.missing_sources = missing_sources
        super().__init__("Q8 task evaluation profile is incomplete")


_PRIORITY_RANK = {
    TaskPriority.LOW: 1,
    TaskPriority.MEDIUM: 2,
    TaskPriority.HIGH: 3,
    TaskPriority.CRITICAL: 4,
}
_PRIORITY_BY_RANK = {value: key for key, value in _PRIORITY_RANK.items()}
_RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class Q8EvaluationPlan:
    status: Literal["missing", "ready"]
    evaluation_profile: dict[str, Any]
    missing_sources: list[str]


@dataclass(frozen=True)
class Q8TaskPriorityDecision:
    priority: TaskPriority
    metadata: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float_weight(weights: dict[str, Any], key: str, missing_sources: list[str]) -> float:
    value = weights.get(key)
    if value in (None, "", [], {}):
        missing_sources.append(f"q9.evaluation_profile.evaluation_weights.{key}")
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        missing_sources.append(f"q9.evaluation_profile.evaluation_weights.{key}")
        raise Q8EvaluationProfileError(missing_sources) from exc


def _require_text(profile: dict[str, Any], key: str, missing_sources: list[str]) -> str:
    text = str(profile.get(key) or "").strip()
    if not text:
        missing_sources.append(f"q9.evaluation_profile.{key}")
    return text


def _extract_evaluation_profile(snapshot_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    q9_snapshot = _as_dict(snapshot_map.get("q9"))
    context_updates = _as_dict(q9_snapshot.get("context_updates"))
    result_payload = _as_dict(q9_snapshot.get("result"))
    q9_action_posture = _as_dict(context_updates.get("q9_action_posture") or result_payload.get("q9_action_posture"))
    return _as_dict(
        context_updates.get("q9_evaluation_profile")
        or result_payload.get("q9_evaluation_profile")
        or q9_action_posture.get("q9_evaluation_profile")
        or q9_action_posture.get("evaluation_profile")
        or result_payload.get("evaluation_profile")
    )


def derive_q8_evaluation_plan(snapshot_map: dict[str, dict[str, Any]]) -> Q8EvaluationPlan:
    q9_snapshot = _as_dict(snapshot_map.get("q9"))
    if not q9_snapshot:
        return Q8EvaluationPlan(
            status="missing",
            evaluation_profile={},
            missing_sources=["q9.snapshot"],
        )

    missing_sources: list[str] = []
    trace_id = str(q9_snapshot.get("trace_id") or "").strip()
    if not trace_id:
        missing_sources.append("q9.trace_id")

    profile = _extract_evaluation_profile(snapshot_map)
    if not profile:
        missing_sources.append("q9.evaluation_profile")
        raise Q8EvaluationProfileError(missing_sources)

    _require_text(profile, "role_context", missing_sources)
    _require_text(profile, "resource_context", missing_sources)
    _require_text(profile, "risk_level", missing_sources)
    _require_text(profile, "evaluation_style", missing_sources)
    _require_text(profile, "action_rhythm_hint", missing_sources)

    weights = _as_dict(profile.get("evaluation_weights"))
    if not weights:
        missing_sources.append("q9.evaluation_profile.evaluation_weights")
    else:
        for key in ("accuracy", "risk_control", "continuity"):
            _float_weight(weights, key, missing_sources)

    if missing_sources:
        raise Q8EvaluationProfileError(missing_sources)

    normalized_profile = enrich_evaluation_profile_with_meta_value_lenses({
        **profile,
        "evaluation_weights": {str(key): float(value) for key, value in weights.items()},
        "source_trace_id": trace_id,
    })
    return Q8EvaluationPlan(
        status="ready",
        evaluation_profile=normalized_profile,
        missing_sources=[],
    )


def _risk_level(task: dict[str, Any]) -> str:
    risk_assessment = _as_dict(task.get("risk_assessment"))
    return str(risk_assessment.get("risk_level") or risk_assessment.get("level") or "medium").strip().lower()


def _raise_priority(base: TaskPriority, minimum: TaskPriority) -> TaskPriority:
    return _PRIORITY_BY_RANK[max(_PRIORITY_RANK[base], _PRIORITY_RANK[minimum])]


def apply_evaluation_profile_to_task_priority(
    *,
    task: dict[str, Any],
    base_priority: TaskPriority,
    evaluation_plan: Q8EvaluationPlan,
) -> Q8TaskPriorityDecision:
    if evaluation_plan.status != "ready":
        return Q8TaskPriorityDecision(
            priority=base_priority,
            metadata={
                "status": evaluation_plan.status,
                "missing_sources": list(evaluation_plan.missing_sources),
                "priority_rule": "base_q8_priority",
                "base_priority": base_priority.value,
                "final_priority": base_priority.value,
            },
        )

    profile = evaluation_plan.evaluation_profile
    weights = _as_dict(profile.get("evaluation_weights"))
    risk_control = float(weights.get("risk_control", 0.0))
    speed = float(weights.get("speed", 0.0))
    accuracy = float(weights.get("accuracy", 0.0))
    conservative = bool(profile.get("conservative_mode_triggered"))
    risk_level = _risk_level(task)
    risk_rank = _RISK_RANK.get(risk_level, 2)

    final_priority = base_priority
    applied_rules: list[str] = []
    if conservative and risk_rank >= 3:
        final_priority = _raise_priority(final_priority, TaskPriority.CRITICAL)
        applied_rules.append("conservative_high_risk_to_critical")
    elif risk_control >= max(speed, accuracy) and risk_rank >= 3:
        final_priority = _raise_priority(final_priority, TaskPriority.HIGH)
        applied_rules.append("risk_control_high_risk_to_high")
    elif speed > risk_control and risk_rank <= 1:
        final_priority = _raise_priority(final_priority, TaskPriority.HIGH)
        applied_rules.append("speed_low_risk_to_high")

    if not applied_rules:
        applied_rules.append("base_q8_priority")

    return Q8TaskPriorityDecision(
        priority=final_priority,
        metadata={
            "status": "ready",
            "source_trace_id": str(profile.get("source_trace_id") or ""),
            "risk_level": risk_level,
            "risk_rank": risk_rank,
            "evaluation_style": str(profile.get("evaluation_style") or ""),
            "action_rhythm_hint": str(profile.get("action_rhythm_hint") or ""),
            "evaluation_weights": weights,
            "meta_value_lens_weights": profile.get("meta_value_lens_weights", {}),
            "dominant_meta_value_lenses": profile.get("dominant_meta_value_lenses", []),
            "conservative_mode_triggered": conservative,
            "base_priority": base_priority.value,
            "final_priority": final_priority.value,
            "applied_rules": applied_rules,
        },
    )
