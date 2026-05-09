from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from plugins.weights.assembler.weight_assembler_plugin import (
    SubjectiveWeightPlugin,
    build_cost_guard_weight,
    build_creative_exploration_weight,
    build_default_conservative_weight,
    build_risk_balanced_weight,
)
from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
BLOCKED_BUDGET_CAPABILITIES = {"G14", "G16", "G24", "high_frequency_sensing", "curiosity"}
RISK_SCORE = {"low": 0.15, "medium": 0.4, "high": 0.75, "critical": 1.0}


class ThoughtMode(str, Enum):
    FAST = "fast"
    DEEP = "deep"
    EMERGENCY = "emergency"


class ThoughtCostProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    compute_remaining_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    token_remaining_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    time_remaining_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    budget_pressure: str = "normal"
    minimum_remaining_ratio: float = Field(default=1.0, ge=0.0, le=1.0)


class ValueEngine:
    """Feature 13 value engine facade; service.py delegates here only."""

    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel

    def evaluate(
        self,
        *,
        session_id: str,
        candidate_goals: list[dict[str, Any]],
        candidate_plans: Optional[list[dict[str, Any]]] = None,
        resource_state: Optional[dict[str, Any]] = None,
        risk_state: Optional[dict[str, Any]] = None,
        role_state: Optional[dict[str, Any]] = None,
        self_state: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        requested_capabilities: Optional[list[str]] = None,
        weight_profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return _evaluate_value_engine_record(
            self.kernel,
            session_id=session_id,
            candidate_goals=candidate_goals,
            candidate_plans=candidate_plans,
            resource_state=resource_state,
            risk_state=risk_state,
            role_state=role_state,
            self_state=self_state,
            context=context,
            requested_capabilities=requested_capabilities,
            weight_profile=weight_profile,
        )

    def query(self, *, session_id: str, decision_id: str) -> dict[str, Any]:
        return _query_value_engine_decision(self.kernel, session_id=session_id, decision_id=decision_id)


def evaluate_value_engine(
    kernel: Any,
    *,
    session_id: str,
    candidate_goals: list[dict[str, Any]],
    candidate_plans: Optional[list[dict[str, Any]]] = None,
    resource_state: Optional[dict[str, Any]] = None,
    risk_state: Optional[dict[str, Any]] = None,
    role_state: Optional[dict[str, Any]] = None,
    self_state: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
    requested_capabilities: Optional[list[str]] = None,
    weight_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return ValueEngine(kernel).evaluate(
        session_id=session_id,
        candidate_goals=candidate_goals,
        candidate_plans=candidate_plans,
        resource_state=resource_state,
        risk_state=risk_state,
        role_state=role_state,
        self_state=self_state,
        context=context,
        requested_capabilities=requested_capabilities,
        weight_profile=weight_profile,
    )


def _evaluate_value_engine_record(
    kernel: Any,
    *,
    session_id: str,
    candidate_goals: list[dict[str, Any]],
    candidate_plans: Optional[list[dict[str, Any]]] = None,
    resource_state: Optional[dict[str, Any]] = None,
    risk_state: Optional[dict[str, Any]] = None,
    role_state: Optional[dict[str, Any]] = None,
    self_state: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
    requested_capabilities: Optional[list[str]] = None,
    weight_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not candidate_goals:
        raise ValueError("candidate_goals is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    resource_state = dict(resource_state or {})
    risk_state = dict(risk_state or {})
    context = dict(context or {})
    requested_capabilities = list(requested_capabilities or [])
    weight_snapshot, weight_audit = _resolve_weight_snapshot(weight_profile, context)
    budget_gate = _evaluate_budget_gate(resource_state, risk_state, requested_capabilities)
    thought_mode = _select_thought_mode(resource_state, risk_state, budget_gate)
    ranked_goals = _rank_candidates(
        candidate_goals,
        candidate_plans or [],
        weight_snapshot,
        resource_state,
        risk_state,
        budget_gate,
    )
    allowed_goals = [item for item in ranked_goals if not item["hard_boundary_blocked"]]
    recommended_goal = allowed_goals[0] if allowed_goals else None
    decision_id = f"g13-value-{uuid4().hex}"
    posture = _select_posture(weight_snapshot, budget_gate, risk_state)
    record = {
        "feature_code": "G13",
        "session_id": session_id,
        "decision_id": decision_id,
        "thought_mode": thought_mode,
        "budget_gate": budget_gate,
        "weight_snapshot": weight_snapshot,
        "weight_audit": weight_audit,
        "ranked_goals": ranked_goals,
        "recommended_goal_id": recommended_goal["goal_id"] if recommended_goal else None,
        "recommended_strategy": _recommended_strategy(recommended_goal, posture, thought_mode),
        "posture": posture,
        "inputs": {
            "candidate_goals": candidate_goals,
            "candidate_plans": candidate_plans or [],
            "resource_state": resource_state,
            "risk_state": risk_state,
            "role_state": role_state or {},
            "self_state": self_state or {},
            "context": context,
            "requested_capabilities": requested_capabilities,
        },
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, record)
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_value_engine_decisions", decision_id, record)
    _append_transcript(state, record, "g13_value_engine_evaluated")
    return record


def query_value_engine_decision(kernel: Any, *, session_id: str, decision_id: str) -> dict[str, Any]:
    return ValueEngine(kernel).query(session_id=session_id, decision_id=decision_id)


def _query_value_engine_decision(kernel: Any, *, session_id: str, decision_id: str) -> dict[str, Any]:
    if not session_id or not decision_id:
        raise ValueError("session_id and decision_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    decision = getattr(kernel, "_value_engine_decisions", {}).get(decision_id)
    if not decision or decision["session_id"] != session_id:
        raise KeyError(f"G13 value engine decision not found: {decision_id}")
    _append_transcript(state, decision, "g13_value_engine_decision_queried")
    return {**decision, "query_visible": True}


def _resolve_weight_snapshot(weight_profile: Optional[dict[str, Any]], context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback = build_default_conservative_weight()
    if weight_profile:
        try:
            profile_payload = {**weight_profile}
            profile_payload.setdefault("plugin_id", "g13_runtime_weight")
            profile_payload.setdefault("version", "1.0.0")
            profile_payload.setdefault("purpose", "Runtime value engine subjective profile.")
            profile_payload.setdefault("is_concurrency_safe", True)
            profile_payload.setdefault("lifecycle_status", "active")
            profile_payload.setdefault("health_status", "healthy")
            profile_payload.setdefault("rollback_conditions", ["weight_drift_detected", "g25_audit_rejected"])
            profile_payload.setdefault("revocation_reasons", ["reserved_for_weight_audit"])
            profile_payload.setdefault("rationale_tags", ["runtime_supplied"])
            plugin = SubjectiveWeightPlugin.model_validate(profile_payload)
            audit = _audit_weight_profile(plugin)
            if audit["status"] != "passed":
                return _snapshot_from_plugin(fallback, True, audit["reason"]), audit
            return _snapshot_from_plugin(plugin, False, None), audit
        except (ValidationError, ValueError) as exc:
            audit = {"status": "rejected", "reason": str(exc), "rollback_profile": fallback.plugin_id}
            return _snapshot_from_plugin(fallback, True, str(exc)), audit

    scenario = str(context.get("scenario") or "").lower()
    if "creative" in scenario:
        plugin = build_creative_exploration_weight()
    elif "cost" in scenario or "low_budget" in scenario:
        plugin = build_cost_guard_weight()
    elif "balanced" in scenario:
        plugin = build_risk_balanced_weight()
    else:
        plugin = fallback
    return _snapshot_from_plugin(plugin, False, None), {"status": "passed", "reason": "profile_selected_by_context"}


def _audit_weight_profile(plugin: SubjectiveWeightPlugin) -> dict[str, Any]:
    total = plugin.risk_tolerance + plugin.cost_sensitivity + plugin.creativity_bias + plugin.continuity_bias
    if abs(total - 1.0) > 0.25:
        return {
            "status": "rejected",
            "reason": f"weight_total_drift:{total:.3f}",
            "rollback_profile": "default_conservative_weight",
        }
    if plugin.continuity_bias < 0.1:
        return {
            "status": "rejected",
            "reason": "continuity_boundary_drift",
            "rollback_profile": "default_conservative_weight",
        }
    return {"status": "passed", "reason": "g25_weight_audit_passed"}


def _snapshot_from_plugin(plugin: SubjectiveWeightPlugin, fallback: bool, reason: Optional[str]) -> dict[str, Any]:
    return {
        "active_weight_plugin_id": plugin.plugin_id,
        "weight_fallback_occurred": fallback,
        "fallback_reason": reason,
        "purpose": plugin.purpose,
        "risk_tolerance": plugin.risk_tolerance,
        "cost_sensitivity": plugin.cost_sensitivity,
        "creativity_bias": plugin.creativity_bias,
        "continuity_bias": plugin.continuity_bias,
        "rationale_tags": list(plugin.rationale_tags),
    }


def _evaluate_budget_gate(
    resource_state: dict[str, Any],
    risk_state: dict[str, Any],
    requested_capabilities: list[str],
) -> dict[str, Any]:
    remaining = {
        "compute_remaining_ratio": _ratio(resource_state.get("compute_remaining_ratio"), 1.0),
        "token_remaining_ratio": _ratio(resource_state.get("token_remaining_ratio"), 1.0),
        "time_remaining_ratio": _ratio(resource_state.get("time_remaining_ratio"), 1.0),
    }
    minimum = min(remaining.values())
    pressure = str(resource_state.get("budget_pressure") or "normal").lower()
    cost_profile = ThoughtCostProfile(
        compute_remaining_ratio=remaining["compute_remaining_ratio"],
        token_remaining_ratio=remaining["token_remaining_ratio"],
        time_remaining_ratio=remaining["time_remaining_ratio"],
        budget_pressure=pressure,
        minimum_remaining_ratio=minimum,
    )
    risk_level = str(risk_state.get("risk_level") or "low").lower()
    insufficient = minimum < 0.15 or pressure in {"high", "critical"} or (
        risk_level == "critical" and not risk_state.get("emergency_override")
    )
    blocked = sorted(set(requested_capabilities).intersection(BLOCKED_BUDGET_CAPABILITIES)) if insufficient else []
    return {
        "status": "blocked" if blocked else "approved",
        "budget_sufficient": not insufficient,
        "thought_cost_profile": cost_profile.model_dump(mode="json"),
        "remaining": remaining,
        "minimum_remaining_ratio": minimum,
        "budget_pressure": pressure,
        "risk_level": risk_level,
        "blocked_capabilities": blocked,
        "reason": "budget_insufficient_for_high_frequency_or_curiosity" if blocked else "budget_available",
    }


def _select_thought_mode(resource_state: dict[str, Any], risk_state: dict[str, Any], gate: dict[str, Any]) -> str:
    risk_level = str(risk_state.get("risk_level") or "low").lower()
    entropy = float(risk_state.get("entropy") or 0.0)
    if bool(risk_state.get("emergency")) or risk_level == "critical":
        return ThoughtMode.EMERGENCY.value
    if gate["budget_sufficient"] and (risk_level == "high" or entropy >= 0.65):
        return ThoughtMode.DEEP.value
    return ThoughtMode.FAST.value


def _rank_candidates(
    goals: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    weight: dict[str, Any],
    resource_state: dict[str, Any],
    risk_state: dict[str, Any],
    gate: dict[str, Any],
) -> list[dict[str, Any]]:
    plan_by_goal = {str(plan.get("goal_id")): plan for plan in plans if plan.get("goal_id")}
    rows: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        goal_id = str(goal.get("goal_id") or goal.get("id") or f"goal-{index + 1}")
        plan = plan_by_goal.get(goal_id, {})
        hard_boundary_reasons = _hard_boundary_reasons(goal)
        risk = _goal_float(goal, plan, "risk", RISK_SCORE.get(str(risk_state.get("risk_level") or "low").lower(), 0.4))
        cost = _goal_float(goal, plan, "cost", 0.5)
        creativity = _goal_float(goal, plan, "creativity", 0.0)
        continuity = _goal_float(goal, plan, "continuity", 0.5)
        expected_value = _goal_float(goal, plan, "expected_value", 0.5)
        urgency = _goal_float(goal, plan, "urgency", 0.3)
        budget_penalty = 0.25 if gate["status"] == "blocked" and goal.get("capability") in gate["blocked_capabilities"] else 0.0
        score = (
            0.35 * expected_value
            + 0.2 * urgency
            + weight["creativity_bias"] * creativity
            + weight["continuity_bias"] * continuity
            - weight["cost_sensitivity"] * cost
            - max(0.0, risk - weight["risk_tolerance"])
            - budget_penalty
        )
        if hard_boundary_reasons:
            score = -1.0
        rows.append(
            {
                "rank": 0,
                "goal_id": goal_id,
                "title": str(goal.get("title") or goal.get("name") or goal_id),
                "value_score": round(score, 6),
                "hard_boundary_blocked": bool(hard_boundary_reasons),
                "hard_boundary_reasons": hard_boundary_reasons,
                "components": {
                    "expected_value": expected_value,
                    "urgency": urgency,
                    "risk": risk,
                    "cost": cost,
                    "creativity": creativity,
                    "continuity": continuity,
                    "budget_penalty": budget_penalty,
                },
                "plan": plan,
            }
        )
    rows.sort(key=lambda item: (item["hard_boundary_blocked"], -item["value_score"], item["goal_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _hard_boundary_reasons(goal: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if goal.get("safety_level") in {"blocked", "unsafe"}:
        reasons.append("safety_boundary")
    if goal.get("requires_authorization") and not goal.get("authorized"):
        reasons.append("authorization_boundary")
    if goal.get("audit_required") and not goal.get("audit_passed"):
        reasons.append("audit_boundary")
    if goal.get("rollback_required") and not goal.get("rollback_ready"):
        reasons.append("rollback_boundary")
    if goal.get("breaks_subject_continuity"):
        reasons.append("subject_continuity_boundary")
    return reasons


def _goal_float(goal: dict[str, Any], plan: dict[str, Any], key: str, default: float) -> float:
    return _ratio(goal.get(key, plan.get(key, default)), default)


def _ratio(value: Any, default: float) -> float:
    if value is None:
        return default
    number = float(value)
    if number < 0 or number > 1:
        raise ValueError(f"ratio value out of range [0, 1]: {value}")
    return number


def _select_posture(weight: dict[str, Any], gate: dict[str, Any], risk_state: dict[str, Any]) -> str:
    risk_level = str(risk_state.get("risk_level") or "low").lower()
    if gate["status"] == "blocked" or risk_level in {"high", "critical"}:
        return "conservative"
    if weight["risk_tolerance"] >= 0.5 and weight["creativity_bias"] >= 0.2:
        return "aggressive"
    return "conservative"


def _recommended_strategy(goal: Optional[dict[str, Any]], posture: str, thought_mode: str) -> dict[str, Any]:
    if not goal:
        return {"strategy_id": None, "summary": "No allowed goal after hard-boundary evaluation."}
    return {
        "strategy_id": f"strategy-{goal['goal_id']}",
        "summary": f"{posture} posture with {thought_mode} reasoning for {goal['goal_id']}",
        "goal_id": goal["goal_id"],
    }


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    memory = memory_service.remember(
        title=f"G13 value decision {record['decision_id']}",
        summary=f"G13 {record['thought_mode']} recommended {record['recommended_goal_id']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g13_value_engine",
        trace_id=record["decision_id"],
        target_id=record["decision_id"],
        tags=["G13", "value_engine", record["thought_mode"], record["budget_gate"]["status"]],
        value_engine_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if memory_id and getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G13 memory writeback query verification failed: {memory_id}")
    return memory_id or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G13", "entry_type": entry_type, **record},
        )
    )
