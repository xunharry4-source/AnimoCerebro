from __future__ import annotations

"""Feature 54 MetaCognitionController deterministic scheduling rules."""

import hashlib
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc


@dataclass
class ReasoningModeDecision:
    decision_id: str
    thought_mode: str
    reasoning_depth: int
    interaction_posture: str
    exploration_policy: str
    selection_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolInvocationPlan:
    plan_id: str
    selected_tools: list[dict[str, Any]]
    rejected_tools: list[dict[str, Any]]
    phase_order: list[str]
    parallel_groups: list[list[str]]
    serial_groups: list[list[str]]
    fallback_plan: dict[str, Any]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EscalationDecision:
    decision_id: str
    decision_type: str
    reason: str
    required_context: list[str] = field(default_factory=list)
    blocking_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetaCognitionDecisionBundle:
    decision_bundle_id: str
    reasoning_mode_decision: ReasoningModeDecision
    tool_invocation_plan: ToolInvocationPlan
    escalation_decision: EscalationDecision
    input_summary: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_bundle_id": self.decision_bundle_id,
            "reasoning_mode_decision": self.reasoning_mode_decision.to_dict(),
            "tool_invocation_plan": self.tool_invocation_plan.to_dict(),
            "escalation_decision": self.escalation_decision.to_dict(),
            "input_summary": dict(self.input_summary),
            "created_at": self.created_at,
        }


class MetaCognitionController:
    """Deterministically decides how the next cognitive phase should think."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._last_decision: MetaCognitionDecisionBundle | None = None
        self._lock = threading.Lock()

    def decide(
        self,
        *,
        wm_frame: dict[str, Any],
        self_model: dict[str, Any],
        budget: dict[str, Any],
        nine_q_state: dict[str, Any],
        agenda: list[dict[str, Any]] | dict[str, Any],
        tool_registry: list[dict[str, Any]] | dict[str, Any],
    ) -> dict[str, Any]:
        _require_dict(wm_frame, "wm_frame")
        _require_dict(self_model, "self_model")
        _require_dict(budget, "budget")
        _require_dict(nine_q_state, "nine_q_state")
        tools = _normalize_tools(tool_registry)
        if not tools:
            raise ValueError("tool_registry must contain at least one registered tool")
        agenda_items = _normalize_agenda(agenda)
        context = self._summarize_inputs(wm_frame, self_model, budget, nine_q_state, agenda_items, tools)
        mode = self._decide_mode(context)
        escalation = self._decide_escalation(context)
        plan = self._build_tool_plan(context, tools, agenda_items, escalation)
        bundle = MetaCognitionDecisionBundle(
            decision_bundle_id=_stable_id("metacognition-bundle", self._session_id, _now(), mode.thought_mode),
            reasoning_mode_decision=mode,
            tool_invocation_plan=plan,
            escalation_decision=escalation,
            input_summary=context,
            created_at=_now(),
        )
        with self._lock:
            self._last_decision = bundle
        return {
            "feature_code": "B7-54",
            "operation": "decide",
            "metacognition_status": "decided",
            "deterministic": True,
            "llm_required": False,
            "decision_bundle": bundle.to_dict(),
        }

    def last_decision_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_decision.to_dict() if self._last_decision else None

    def _summarize_inputs(
        self,
        wm_frame: dict[str, Any],
        self_model: dict[str, Any],
        budget: dict[str, Any],
        nine_q_state: dict[str, Any],
        agenda_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        living = self_model.get("living_self_model") if isinstance(self_model.get("living_self_model"), dict) else self_model
        state = living.get("current_state") if isinstance(living.get("current_state"), dict) else {}
        weaknesses = living.get("recent_weaknesses") or self_model.get("recent_weaknesses") or []
        indicators = living.get("confidence_drift_indicators") or []
        active = len(wm_frame.get("active_focus_ids") or wm_frame.get("active_items") or [])
        suspended = len(wm_frame.get("suspended_focus_ids") or wm_frame.get("suspended_items") or [])
        risk_level = _max_risk_level(
            [str(nine_q_state.get("risk_level") or nine_q_state.get("current_risk_level") or "low")]
            + [str(item.get("risk_level") or item.get("risk") or "low") for item in agenda_items]
        )
        evidence_score = _clamp01(float(nine_q_state.get("evidence_score") or nine_q_state.get("evidence_support") or budget.get("evidence_score") or 0.5))
        remaining_ratio = _remaining_ratio(budget)
        return {
            "load_level": str(state.get("load_level") or living.get("current_cognitive_load") or self_model.get("load_level") or "low"),
            "stability_level": str(state.get("stability_level") or self_model.get("stability_level") or "stable"),
            "reasoning_posture": str(state.get("reasoning_posture") or "balanced"),
            "evidence_posture": str(state.get("evidence_posture") or "evidence_first"),
            "weaknesses": weaknesses,
            "max_weakness_frequency": max([int(item.get("frequency") or 0) for item in weaknesses if isinstance(item, dict)] + [0]),
            "drift_alert": any(bool(item.get("triggered_alert")) for item in indicators if isinstance(item, dict)),
            "active_focus_count": active,
            "suspended_focus_count": suspended,
            "risk_level": risk_level,
            "evidence_score": evidence_score,
            "remaining_budget_ratio": remaining_ratio,
            "agenda_high_relevance_count": sum(1 for item in agenda_items if _clamp01(float(item.get("goal_relevance") or item.get("relevance") or 0.0)) >= 0.7),
            "registered_tool_ids": [str(item["tool_id"]) for item in tools],
            "tool_count": len(tools),
        }

    def _decide_mode(self, context: dict[str, Any]) -> ReasoningModeDecision:
        load = context["load_level"]
        risk = context["risk_level"]
        evidence = context["evidence_score"]
        drift_alert = context["drift_alert"]
        if risk == "critical":
            mode, depth, posture, exploration, reason = (
                "emergency",
                1,
                "first_review",
                "closed",
                "critical risk requires emergency handling",
            )
        elif load == "high":
            mode, depth, posture, exploration, reason = (
                "shallow",
                1,
                "first_review" if drift_alert or evidence < 0.35 else "direct_answer",
                "limited",
                "high cognitive load forbids deep reasoning",
            )
        elif risk in {"high", "critical"} and evidence < 0.45:
            mode, depth, posture, exploration, reason = (
                "deep",
                3,
                "first_review",
                "limited",
                "high risk with low evidence requires review before answer",
            )
        elif drift_alert and evidence < 0.5:
            mode, depth, posture, exploration, reason = (
                "standard",
                2,
                "clarify_first",
                "limited",
                "confidence drift alert requires clarification",
            )
        elif context["remaining_budget_ratio"] < 0.2:
            mode, depth, posture, exploration, reason = (
                "fast",
                1,
                "defer_noncritical",
                "closed",
                "budget remaining ratio is below 20 percent",
            )
        else:
            mode, depth, posture, exploration, reason = (
                "standard",
                2,
                "direct_answer",
                "open",
                "normal load, evidence, and budget",
            )
        return ReasoningModeDecision(
            decision_id=_stable_id("reasoning-mode", self._session_id, mode, reason),
            thought_mode=mode,
            reasoning_depth=depth,
            interaction_posture=posture,
            exploration_policy=exploration,
            selection_reason=reason,
        )

    def _decide_escalation(self, context: dict[str, Any]) -> EscalationDecision:
        if context["drift_alert"] and context["evidence_score"] < 0.45:
            decision_type = "clarify"
            reason = "confidence drift is triggered while evidence is below decision threshold"
            required_context = ["stronger evidence for high-confidence statements"]
            blocking_risks = ["high_confidence_low_evidence"]
        elif context["max_weakness_frequency"] >= 3:
            decision_type = "revisit"
            reason = "repeated weakness frequency reached revisit threshold"
            required_context = ["prior failure evidence", "countermeasure tool result"]
            blocking_risks = ["repeated_failure_pattern"]
        elif context["remaining_budget_ratio"] < 0.2:
            decision_type = "defer"
            reason = "remaining budget below 20 percent"
            required_context = ["budget refill or scope reduction"]
            blocking_risks = ["resource_tight"]
        elif context["risk_level"] == "critical":
            decision_type = "request_help"
            reason = "critical risk cannot be resolved by normal autonomous scheduling"
            required_context = ["human or supervisory confirmation"]
            blocking_risks = ["critical_risk"]
        else:
            decision_type = "continue"
            reason = "no escalation rule was triggered"
            required_context = []
            blocking_risks = []
        return EscalationDecision(
            decision_id=_stable_id("escalation", self._session_id, decision_type, reason),
            decision_type=decision_type,
            reason=reason,
            required_context=required_context,
            blocking_risks=blocking_risks,
        )

    def _build_tool_plan(
        self,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
        agenda_items: list[dict[str, Any]],
        escalation: EscalationDecision,
    ) -> ToolInvocationPlan:
        selected_ids: list[str] = []
        reasons: dict[str, str] = {}
        weakness_types = {
            str(item.get("pattern_type") or item.get("weakness_type") or "")
            for item in context["weaknesses"]
            if isinstance(item, dict)
        }
        desired_capabilities = _countermeasure_capabilities(weakness_types)
        if context["drift_alert"]:
            desired_capabilities.add("evidence_check")
        if context["risk_level"] in {"high", "critical"}:
            desired_capabilities.add("risk_compare")
        if context["agenda_high_relevance_count"] > 0:
            desired_capabilities.add("agenda_review")
        for tool in tools:
            capabilities = set(_listify(tool.get("capabilities") or tool.get("counters_weaknesses")))
            tool_id = str(tool["tool_id"])
            if capabilities & desired_capabilities:
                selected_ids.append(tool_id)
                reasons[tool_id] = f"matches capabilities {sorted(capabilities & desired_capabilities)}"
        if not selected_ids:
            for tool in tools:
                selected_ids.append(str(tool["tool_id"]))
                reasons[str(tool["tool_id"])] = "fallback registered cognitive tool"
                if len(selected_ids) >= 2:
                    break
        selected_tools = [
            {
                "tool_id": str(tool["tool_id"]),
                "tool_name": str(tool.get("tool_name") or tool.get("name") or tool["tool_id"]),
                "selection_reason": reasons[str(tool["tool_id"])],
                "is_concurrency_safe": bool(tool.get("is_concurrency_safe", True)),
                "mutates_working_memory": bool(tool.get("mutates_working_memory", False)),
            }
            for tool in tools
            if str(tool["tool_id"]) in selected_ids
        ]
        rejected_tools = [
            {
                "tool_id": str(tool["tool_id"]),
                "rejection_reason": "not relevant to current weaknesses, agenda, risk, or evidence state",
            }
            for tool in tools
            if str(tool["tool_id"]) not in selected_ids
        ]
        parallel_groups = [
            [item["tool_id"] for item in selected_tools if item["is_concurrency_safe"] and not item["mutates_working_memory"]]
        ]
        parallel_groups = [group for group in parallel_groups if group]
        serial_groups = [[item["tool_id"]] for item in selected_tools if item["mutates_working_memory"] or not item["is_concurrency_safe"]]
        phase_order = [item["tool_id"] for item in selected_tools]
        if escalation.decision_type in {"clarify", "revisit"}:
            explanation = "prioritize evidence and weakness countermeasure tools before continuing"
        elif escalation.decision_type == "defer":
            explanation = "keep only minimal registered tools because budget is tight"
        else:
            explanation = "use registered tools that match current cognitive state"
        return ToolInvocationPlan(
            plan_id=_stable_id("tool-plan", self._session_id, ",".join(phase_order), escalation.decision_type),
            selected_tools=selected_tools,
            rejected_tools=rejected_tools,
            phase_order=phase_order,
            parallel_groups=parallel_groups,
            serial_groups=serial_groups,
            fallback_plan={
                "on_primary_failure": "switch_to_clarify_or_revisit",
                "escalation_decision_type": escalation.decision_type,
            },
            explanation=explanation,
        )


def _require_dict(value: Any, name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")


def _normalize_tools(tool_registry: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(tool_registry, dict):
        raw_tools = tool_registry.get("tools") or tool_registry.get("registered_tools") or []
    elif isinstance(tool_registry, list):
        raw_tools = tool_registry
    else:
        raise ValueError("tool_registry must be a list or dict")
    tools: list[dict[str, Any]] = []
    for raw in raw_tools:
        if not isinstance(raw, dict):
            raise ValueError("tool_registry entries must be dicts")
        tool_id = raw.get("tool_id") or raw.get("id") or raw.get("name")
        if not tool_id:
            raise ValueError("registered tool is missing tool_id")
        tools.append({**raw, "tool_id": str(tool_id)})
    return tools


def _normalize_agenda(agenda: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(agenda, dict):
        raw_items = agenda.get("items") or agenda.get("agenda_items") or agenda.get("review_now_items") or []
    elif isinstance(agenda, list):
        raw_items = agenda
    else:
        raise ValueError("agenda must be a list or dict")
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("agenda entries must be dicts")
        items.append(raw)
    return items


def _remaining_ratio(budget: dict[str, Any]) -> float:
    if budget.get("remaining_ratio") is not None:
        return _clamp01(float(budget["remaining_ratio"]))
    remaining = float(budget.get("remaining") or budget.get("remaining_tokens") or budget.get("remaining_steps") or 0.0)
    total = float(budget.get("total") or budget.get("total_tokens") or budget.get("max_steps") or 0.0)
    if total <= 0:
        return 1.0
    return _clamp01(remaining / total)


def _max_risk_level(levels: list[str]) -> str:
    order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return max((level.lower() for level in levels), key=lambda item: order.get(item, 1))


def _countermeasure_capabilities(weakness_types: set[str]) -> set[str]:
    capabilities: set[str] = set()
    for weakness in weakness_types:
        normalized = weakness.lower()
        if "premature" in normalized or "conclusion" in normalized:
            capabilities.add("risk_compare")
        if "context" in normalized or "memory" in normalized:
            capabilities.add("working_memory_review")
        if "confidence" in normalized or "overconfidence" in normalized:
            capabilities.add("evidence_check")
        if "failure" in normalized or "repeat" in normalized:
            capabilities.add("failure_review")
    return capabilities


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, set):
        return [str(item) for item in value]
    return [str(value)]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
