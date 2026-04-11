"""
Q9 (我应该如何行动) evidence building and extraction.

Contains functions for building and extracting EVIDENCE_Q9 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q9PreprocessedEvidence,
    Q9ActionPostureInferenceView,
    Q9CognitiveSnapshotEvidence,
    Q9SelfModelEvidence,
    Q9ReasoningBudgetEvidence,
    Q9RecentWeaknessView,
)

from .helpers import _coerce_string_list, _normalize_ratio


def _extract_q9_snapshot_dict(context_payload: dict[str, Any]) -> dict[str, Any]:
    raw = context_payload.get("q1_q8") or context_payload.get("q1_q8_snapshot") or {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if str(k).strip()}
    return {}


def _count_q9_uncertainties(snapshot: dict[str, Any]) -> int:
    q1 = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    return len(_coerce_string_list(q1.get("uncertainties")))


def _count_q9_redlines(snapshot: dict[str, Any]) -> int:
    q5 = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q6 = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    return len(
        _coerce_string_list(q5.get("explicitly_forbidden_actions"))
        + _coerce_string_list(q6.get("absolute_red_lines"))
    )


def _normalize_ratio(value: object) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return 0.0


def _build_q9_preprocessed_evidence(context_payload: dict[str, Any]) -> Q9PreprocessedEvidence | None:
    snapshot = _extract_q9_snapshot_dict(context_payload)
    self_model_raw = context_payload.get("living_self_model") or context_payload.get("self_model") or {}
    budget_raw = context_payload.get("reasoning_budget") or context_payload.get("budget") or {}
    drift_raw = context_payload.get("confidence_drift_indicator") or {}
    if not isinstance(self_model_raw, dict):
        self_model_raw = {}
    if not isinstance(budget_raw, dict):
        budget_raw = {}
    if not isinstance(drift_raw, dict):
        drift_raw = {}

    recent_weaknesses_raw = self_model_raw.get("recent_weaknesses") or []
    recent_weaknesses: list[Q9RecentWeaknessView] = []
    if isinstance(recent_weaknesses_raw, list):
        for item in recent_weaknesses_raw:
            if not isinstance(item, dict):
                continue
            recent_weaknesses.append(
                Q9RecentWeaknessView(
                    pattern_id=str(item.get("pattern_id")) if item.get("pattern_id") else None,
                    pattern_type=str(item.get("pattern_type") or "unknown"),
                    frequency=int(item.get("frequency")) if isinstance(item.get("frequency"), int) else None,
                    severity=str(item.get("severity")) if item.get("severity") else None,
                )
            )

    if not snapshot and not self_model_raw and not budget_raw:
        return None

    return Q9PreprocessedEvidence(
        cognitive_snapshot=Q9CognitiveSnapshotEvidence(
            q1_to_q8_snapshot=snapshot,
            uncertainty_count=_count_q9_uncertainties(snapshot),
            absolute_red_line_count=_count_q9_redlines(snapshot),
        ),
        self_model=Q9SelfModelEvidence(
            cognitive_load=str(
                self_model_raw.get("current_cognitive_load")
                or self_model_raw.get("cognitive_load")
                or "unknown"
            ),
            stability_level=str(
                (self_model_raw.get("current_state") or {}).get("stability_level")
            )
            if isinstance(self_model_raw.get("current_state"), dict)
            and (self_model_raw.get("current_state") or {}).get("stability_level")
            else None,
            confidence_drift=float(drift_raw.get("drift_score"))
            if isinstance(drift_raw.get("drift_score"), (int, float))
            else None,
            recent_weaknesses=recent_weaknesses,
        ),
        reasoning_budget=Q9ReasoningBudgetEvidence(
            compute_remaining_ratio=_normalize_ratio(
                budget_raw.get("compute_remaining_ratio")
                or budget_raw.get("remaining")
                or budget_raw.get("compute_remaining")
            ),
            token_remaining_ratio=_normalize_ratio(
                budget_raw.get("token_remaining_ratio")
                or budget_raw.get("token_remaining")
            ),
            time_remaining_ratio=_normalize_ratio(
                budget_raw.get("time_remaining_ratio")
                or budget_raw.get("time_remaining")
            ),
            budget_pressure=str(budget_raw.get("budget_pressure")) if budget_raw.get("budget_pressure") else None,
        ),
    )


def _extract_q9_preprocessed_evidence(context_payload: object) -> Q9PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(key in context_payload for key in ("q1_q8", "q1_q8_snapshot", "living_self_model", "self_model", "reasoning_budget", "budget")):
        return None
    return _build_q9_preprocessed_evidence(context_payload)


def _extract_q9_inference_result(result_payload: object) -> Q9ActionPostureInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    payload = result_payload.get("q9_action_posture_profile") if isinstance(result_payload.get("q9_action_posture_profile"), dict) else result_payload
    required = {"evaluation_style", "risk_tolerance", "action_rhythm", "confirmation_strategy", "evolution_direction"}
    if not isinstance(payload, dict) or not required.issubset(payload.keys()):
        return None
    return Q9ActionPostureInferenceView(
        evaluation_style=str(payload.get("evaluation_style") or ""),
        risk_tolerance=str(payload.get("risk_tolerance") or ""),
        action_rhythm=str(payload.get("action_rhythm") or ""),
        confirmation_strategy=str(payload.get("confirmation_strategy") or ""),
        evolution_direction=str(payload.get("evolution_direction") or ""),
    )



