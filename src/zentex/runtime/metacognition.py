from __future__ import annotations

"""
Metacognitive scheduling layer for Zentex.

This module is responsible for deciding how the brain should think during the
current turn. It does not solve the task directly and it does not authorize or
trigger host-side execution. Its role is organizational:

- select the current reasoning mode
- constrain reasoning depth under pressure
- choose an interaction posture
- decide whether to continue, clarify, revisit, defer, or request help
- prioritize internal cognitive tools based on weaknesses and risk signals

Inputs are intentionally abstract for now. The controller consumes snapshots or
lightweight dict-like objects representing:

- working memory
- living self model
- reasoning budget
- temporal agenda
- available tool registry

Outputs are strictly internal decisions:

- `ReasoningModeDecision`: how the current turn should think
- `ToolInvocationPlan`: which internal tools should be preferred and in what order
- `EscalationDecision`: whether the turn should continue, clarify, revisit, defer,
  or request help

This layer must never:

- produce host execution commands
- request external permissions
- send messages to outside systems
- encode file writes, network calls, or side-effect actions into its outputs

MetaCognitionController / 元认知调度器

EN:
MetaCognitionController is a hard-rule engine in Zentex. Even though it is
called metacognition, it does not require an LLM. It uses explicit if-else
logic such as "if cognitive load is high, reduce reasoning depth" and "if risk
is high but evidence is low, prefer clarification".

Its subjective value preferences are pluginized through SubjectiveWeightProfile
Plugins. The controller itself remains deterministic, but the weight profile
used to trade off risk, cost, creativity, continuity, and similar values may
be swapped dynamically for different operating contexts such as risk-control
mode or creative mode. Any such profile upgrade must also support rollback to a
previous trusted weight set.

ZH:
MetaCognitionController（元认知调度器）：虽然它叫“元认知”，但在 Zentex 设计中，
它是一个硬性规则引擎。它通过 if-else 逻辑判断“如果认知负荷高 -> 降低推理
深度”、“如果高风险低证据 -> 优先澄清”等。它本身不需要大模型。

它所依赖的主观价值偏好已插件化为 SubjectiveWeightProfile Plugins（主观权重
偏好插件家族）。调度器本身仍然是确定性规则层，但它在风险、成本、创意、连
续性等维度上的取舍权重，可以按场景动态切换和独立升级。所有这类权重升级都必
须支持回退到先前可信版本。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from uuid import uuid4


@dataclass(frozen=True)
class ReasoningModeDecision:
    """High-level decision describing the turn's thinking posture."""

    decision_id: str
    thought_mode: str
    reasoning_depth: str
    interaction_posture: str
    exploration_policy: str
    selection_reason: str


@dataclass(frozen=True)
class ToolInvocationPlan:
    """Internal plan describing which cognitive tools should be preferred next."""

    plan_id: str
    selected_tools: List[str]
    rejected_tools: List[str]
    phase_order: List[str]
    fallback_plan: List[str]
    explanation: str
    parallel_groups: List[List[str]] = field(default_factory=list)
    serial_groups: List[List[str]] = field(default_factory=list)


@dataclass(frozen=True)
class EscalationDecision:
    """Decision describing whether the turn should continue or escalate internally."""

    decision_id: str
    decision_type: str
    reason: str
    required_context: List[str]
    blocking_risks: List[str]


class MetaCognitionController:
    """
    Decide how the brain should think, not what the host should execute.

    This controller may influence:
    - attention priority
    - reasoning depth
    - interaction posture
    - tool selection order

    It must never:
    - issue host execution commands
    - acquire execution permissions
    - send external messages

    Priority model:
    1. Detect evidence sufficiency and risk pressure.
    2. Detect budget pressure and degradation.
    3. Detect repeated failure loops.
    4. Choose reasoning mode with safety-biased overrides.
    5. Build a tool plan that offsets stable weaknesses.
    6. Produce an escalation decision for the next layer to honor.

    Pluginization boundary:
    - this controller stays deterministic
    - subjective preference weights may be supplied by SubjectiveWeightProfile
      Plugins
    - swapping the weight profile changes tradeoff preference, not the
      controller's no-execution boundary
    - every pluginized weight profile must support rollback to a prior trusted
      version
    - health probes, timeout control, and failure isolation are mandatory
    - rejected, degraded, revoked, and rolled-back profiles must preserve
      auditable reasons for transcript projection
    """

    def apply_subjective_weight_profile(self, profile: Any) -> None:
        """Integration boundary for SubjectiveWeightProfile Plugins."""
        pass

    def retrieve_think_loop_context(self) -> Any:
        """Integration boundary for ThinkLoop Phase 6 context."""
        return None
        
    def generate_decisions(
        self,
        working_memory: Any, # Allows WorkingMemoryFrame or dict dict coercion
        living_self_model: Any, # Allows LivingSelfModel or dict coercion
        budget: Any,
        agenda: Any,
        tool_registry: Any,
        nine_q_state: Any = None,
    ) -> Tuple[ReasoningModeDecision, ToolInvocationPlan, EscalationDecision]:
        """
        Generate the three internal control decisions for the current turn.

        The method intentionally works in three passes:
        - assess the current cognitive pressure surface
        - choose a reasoning posture
        - choose tool priorities and escalation posture

        The returned objects are safe to hand to later runtime layers because
        they only describe internal cognition organization. They do not encode
        direct execution actions.
        """
        working_memory_dict = self._coerce_dict(working_memory)
        living_self_model_dict = self._coerce_dict(living_self_model)
        budget_dict = self._coerce_dict(budget)
        agenda_dict = self._coerce_dict(agenda)

        evidence_level = self._score_evidence(working_memory_dict)
        risk_level = self._score_risk(working_memory_dict, agenda_dict)
        budget_pressure = self._score_budget_pressure(budget_dict, living_self_model_dict)
        consecutive_failures = self._count_consecutive_failures(
            working_memory_dict,
            living_self_model_dict,
        )

        reasoning_mode = self._build_reasoning_mode_decision(
            risk_level=risk_level,
            evidence_level=evidence_level,
            budget_pressure=budget_pressure,
            consecutive_failures=consecutive_failures,
        )
        tool_plan = self._build_tool_plan(
            working_memory=working_memory_dict,
            living_self_model=living_self_model_dict,
            agenda=agenda_dict,
            tool_registry=tool_registry,
            reasoning_mode=reasoning_mode,
        )
        escalation = self._build_escalation_decision(
            risk_level=risk_level,
            evidence_level=evidence_level,
            budget_pressure=budget_pressure,
            consecutive_failures=consecutive_failures,
            agenda=agenda_dict,
        )
        return reasoning_mode, tool_plan, escalation

    def _build_reasoning_mode_decision(
        self,
        *,
        risk_level: str,
        evidence_level: str,
        budget_pressure: str,
        consecutive_failures: int,
    ) -> ReasoningModeDecision:
        """
        Choose the turn's top-level reasoning posture.

        Rule order matters:
        - start from a bounded default posture
        - if risk is high and evidence is low, bias toward clarification
        - if budget pressure is high, cap reasoning depth
        - if repeated failures are present, bias toward review and revisit
        """
        thought_mode = "fast"
        reasoning_depth = "standard"
        interaction_posture = "answer"
        exploration_policy = "limited"
        selection_reason = "Default bounded reasoning posture."

        # High risk with weak evidence must bias toward clarify or review rather
        # than confident answer generation.
        if risk_level == "high" and evidence_level == "low":
            thought_mode = "deep"
            reasoning_depth = "deep"
            interaction_posture = "clarify"
            exploration_policy = "enabled"
            selection_reason = (
                "High-risk low-evidence state detected; prioritize clarification "
                "and evidence gathering."
            )

        # High load or insufficient budget must prevent unlimited digging.
        if budget_pressure in {"high", "critical"}:
            thought_mode = "fast" if budget_pressure == "high" else "urgent"
            reasoning_depth = "shallow"
            exploration_policy = "off"
            if interaction_posture == "answer":
                interaction_posture = "defer"
            selection_reason = (
                "Budget pressure detected; downgrade reasoning depth to preserve "
                "runtime stability."
            )

        # Repeated failures should trigger revisit rather than more acceleration.
        if consecutive_failures >= 2:
            interaction_posture = "review"
            thought_mode = "deep"
            reasoning_depth = "standard" if budget_pressure == "critical" else "deep"
            exploration_policy = "limited"
            selection_reason = (
                "Repeated failures detected; revisit prior assumptions before "
                "continuing execution."
            )

        return ReasoningModeDecision(
            decision_id=str(uuid4()),
            thought_mode=thought_mode,
            reasoning_depth=reasoning_depth,
            interaction_posture=interaction_posture,
            exploration_policy=exploration_policy,
            selection_reason=selection_reason,
        )

    def _build_tool_plan(
        self,
        *,
        working_memory: Dict[str, Any],
        living_self_model: Dict[str, Any],
        agenda: Dict[str, Any],
        tool_registry: Any,
        reasoning_mode: ReasoningModeDecision,
    ) -> ToolInvocationPlan:
        """
        Build an internal tool preference order from current weaknesses.

        This plan is not an execution command. It is only an internal hint for
        the later cognitive tool orchestration layer.

        Current preference heuristics:
        - unresolved assumptions prefer conflict or contradiction tools
        - confidence drift prefers review or audit tools
        - overdue agenda pressure prefers planning tools
        """
        weakness_flags = set(working_memory.get("weakness_flags", []))
        weakness_flags.update(living_self_model.get("degraded_flags", []))
        unresolved_assumptions = bool(working_memory.get("unresolved_assumptions"))
        blocked_items = agenda.get("overdue_items", [])

        registry_tools = []
        if tool_registry is not None and hasattr(tool_registry, "list"):
            registry_tools = tool_registry.list()

        selected_tools: List[str] = []
        rejected_tools: List[str] = []

        for registered in registry_tools:
            spec = getattr(registered, "spec", registered)
            tool_id = getattr(spec, "tool_id", None)
            purpose = str(getattr(spec, "purpose", ""))
            if not tool_id:
                continue

            # Tool preference rule: when stable weaknesses are present, prefer
            # tools that offset that weakness. Example: unresolved assumptions
            # should prioritize a conflict checker or contradiction detector.
            if unresolved_assumptions and self._looks_like_conflict_tool(tool_id, purpose):
                selected_tools.append(tool_id)
                continue
            if "confidence_drift" in weakness_flags and self._looks_like_review_tool(tool_id, purpose):
                selected_tools.append(tool_id)
                continue
            if blocked_items and self._looks_like_planning_tool(tool_id, purpose):
                selected_tools.append(tool_id)
                continue
            rejected_tools.append(tool_id)

        if not selected_tools:
            fallback_tool = rejected_tools[:1]
            selected_tools.extend(fallback_tool)
            rejected_tools = rejected_tools[1:] if fallback_tool else rejected_tools

        phase_order = [
            "risk_scan",
            "evidence_review",
            "hypothesis_challenge",
        ]
        if reasoning_mode.exploration_policy == "enabled":
            phase_order.append("branch_exploration")

        fallback_plan = [
            "downgrade_reasoning_depth",
            "request_clarification",
        ]
        explanation = (
            "Tool order selected from current weaknesses, agenda pressure, and "
            "reasoning posture. This plan only affects internal thinking order."
        )
        return ToolInvocationPlan(
            plan_id=str(uuid4()),
            selected_tools=selected_tools,
            rejected_tools=rejected_tools,
            phase_order=phase_order,
            fallback_plan=fallback_plan,
            explanation=explanation,
            parallel_groups=[[t] for t in selected_tools[:2]] if len(selected_tools) >= 2 else [],
            serial_groups=[[t for t in selected_tools]],
        )

    def _build_escalation_decision(
        self,
        *,
        risk_level: str,
        evidence_level: str,
        budget_pressure: str,
        consecutive_failures: int,
        agenda: Dict[str, Any],
    ) -> EscalationDecision:
        """
        Decide whether the turn should continue or shift posture.

        This decision is still internal. Even `request_help` here only means the
        next layer should prepare for a human-facing clarification path; it does
        not directly send a message or trigger any host action.
        """
        decision_type = "continue"
        reason = "No blocking condition detected."
        required_context: List[str] = []
        blocking_risks: List[str] = []

        if risk_level == "high" and evidence_level == "low":
            decision_type = "clarify"
            reason = "High-risk decision path lacks supporting evidence."
            required_context = ["missing_evidence", "operator_intent"]
            blocking_risks = ["unsafe_assumption"]
        elif consecutive_failures >= 2:
            decision_type = "revisit"
            reason = "Repeated failure pattern detected; revisit earlier assumptions."
            required_context = ["previous_attempts", "failed_hypotheses"]
            blocking_risks = ["looping_strategy"]
        elif budget_pressure == "critical":
            decision_type = "defer"
            reason = "Budget exhausted; defer deeper analysis."
            required_context = ["additional_budget", "narrowed_scope"]
            blocking_risks = ["budget_exhaustion"]
        elif agenda.get("needs_human_help"):
            decision_type = "request_help"
            reason = "Agenda explicitly requests human help."
            required_context = ["human_context"]
            blocking_risks = ["human_gate_pending"]

        return EscalationDecision(
            decision_id=str(uuid4()),
            decision_type=decision_type,
            reason=reason,
            required_context=required_context,
            blocking_risks=blocking_risks,
        )

    def _score_evidence(self, working_memory: Dict[str, Any]) -> str:
        """Approximate evidence sufficiency from currently available traces."""
        evidence = working_memory.get("evidence") or working_memory.get("recent_evidence") or []
        if not isinstance(evidence, list) or len(evidence) == 0:
            return "low"
        if len(evidence) < 3:
            return "medium"
        return "high"

    def _score_risk(self, working_memory: Dict[str, Any], agenda: Dict[str, Any]) -> str:
        """Approximate risk pressure from working memory and temporal agenda."""
        if working_memory.get("high_risk") is True:
            return "high"
        if agenda.get("critical_items"):
            return "high"
        if working_memory.get("risk_level"):
            return str(working_memory["risk_level"])
        return "medium"

    def _score_budget_pressure(
        self,
        budget: Dict[str, Any],
        living_self_model: Dict[str, Any],
    ) -> str:
        """Approximate whether the current turn can afford deeper reasoning."""
        remaining = budget.get("remaining")
        degraded_flags = set(living_self_model.get("degraded_flags", []))
        if remaining is not None:
            try:
                remaining_value = float(remaining)
            except (TypeError, ValueError):
                remaining_value = 1.0
            if remaining_value <= 0:
                return "critical"
            if remaining_value < 0.25:
                return "high"
        if "budget_pressure" in degraded_flags:
            return "high"
        return "normal"

    def _count_consecutive_failures(
        self,
        working_memory: Dict[str, Any],
        living_self_model: Dict[str, Any],
    ) -> int:
        """Read recent failure streak information from available state snapshots."""
        if isinstance(working_memory.get("consecutive_failures"), int):
            return int(working_memory["consecutive_failures"])
        if isinstance(living_self_model.get("consecutive_failures"), int):
            return int(living_self_model["consecutive_failures"])
        return 0

    def _looks_like_conflict_tool(self, tool_id: str, purpose: str) -> bool:
        """Heuristic matcher for tools that challenge or reconcile assumptions."""
        probe = f"{tool_id} {purpose}".lower()
        return "conflict" in probe or "contradiction" in probe or "consistency" in probe

    def _looks_like_review_tool(self, tool_id: str, purpose: str) -> bool:
        """Heuristic matcher for review or audit style cognitive tools."""
        probe = f"{tool_id} {purpose}".lower()
        return "review" in probe or "audit" in probe or "verify" in probe

    def _looks_like_planning_tool(self, tool_id: str, purpose: str) -> bool:
        """Heuristic matcher for planning and temporal coordination tools."""
        probe = f"{tool_id} {purpose}".lower()
        return "plan" in probe or "agenda" in probe or "schedule" in probe

    def _coerce_dict(self, value: Any) -> Dict[str, Any]:
        """Accept dict-like snapshots while keeping the controller loosely coupled."""
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        if hasattr(value, "__dict__"):
            return dict(vars(value))
        return {}
