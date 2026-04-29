from __future__ import annotations

"""ThinkLoop — orchestrates the 9-phase cognitive cycle for a single turn.

Also defines KernelServiceBridge, the Protocol that decouples flow_domain
from concrete external service implementations.
"""

from typing import Protocol, runtime_checkable, Any, Dict, List, Optional, Union

from zentex.foundation.contracts import PhaseResult, TurnRequest
from zentex.kernel.flow_domain.objective_context import enrich_context_for_objective_phase
from zentex.kernel.flow_domain.phase_executor import PhaseExecutor
from zentex.kernel.flow_domain.phase_registry import PhaseRegistry
from zentex.kernel.state_domain import (
    CognitiveTemporalEngine,
    SelfModelEngine,
    WorkingMemoryController,
)


@runtime_checkable
class KernelServiceBridge(Protocol):
    """Protocol that abstracts all external service calls needed by the kernel.

    Implementations live in kernel/service.py and wire up to concrete
    cognition, environment, safety, plugin, memory, and LLM services.
    """

    def observe_environment(self, session_id: str, turn_id: str) -> dict:
        """Gather raw environmental observations for the current turn."""
        ...

    def evaluate_drive(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Determine the situational motivation (Phase 1.5) based on observations."""
        ...

    def evaluate_cognition(
        self, session_id: str, turn_id: str, context: dict
    ) -> dict:
        """Run the primary cognition / framing pass over the current context."""
        ...

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        """Identify cognitive or safety conflicts in the accumulated context."""
        ...

    def run_simulation(self, session_id: str, context: dict) -> dict:
        """Execute forward simulations over candidate action branches."""
        ...

    def run_metacognition(self, session_id: str, context: dict) -> dict:
        """Perform metacognitive self-assessment of the current reasoning state."""
        ...

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        """Invoke any registered cognitive-tool plugins relevant to the context."""
        ...

    def synthesize_decision(self, session_id: str, context: dict) -> dict:
        """Produce the final decision and response text from the accumulated context."""
        ...

    def consolidate_memory(
        self, session_id: str, turn_id: str, context: dict
    ) -> dict:
        """Write salient information from this turn into long-term memory."""
        ...


class ThinkLoop:
    """Drives the system through the 9 ordered cognitive phases for one turn.

    Each phase delegates to a specific KernelServiceBridge method.  The
    accumulated *context* dict grows as phase outputs are merged in, so later
    phases always have access to the results of earlier ones.
    """

    def __init__(
        self,
        bridge: KernelServiceBridge,
        registry: Optional[PhaseRegistry] = None,
    ) -> None:
        self._bridge = bridge
        self._registry: PhaseRegistry = registry or PhaseRegistry()

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def run(
        self,
        request: TurnRequest,
        working_memory: WorkingMemoryController,
        self_model: SelfModelEngine,
        temporal: CognitiveTemporalEngine,
    ) -> list[PhaseResult]:
        """Execute all 9 phases in order and return the collected PhaseResults.

        Args:
            request:        The TurnRequest driving this cycle.
            working_memory: The session's WorkingMemoryController.
            self_model:     The session's SelfModelEngine.
            temporal:       The session's CognitiveTemporalEngine.

        Returns:
            Ordered list of PhaseResult, one per phase.
        """
        session_id = request.session_id
        turn_id = request.turn_id

        # Seed context from the turn request
        context: dict = {
            "session_id": session_id,
            "turn_id": turn_id,
            "user_input": request.user_input,
            **request.context,
        }

        results: list[PhaseResult] = []

        for phase_config in self._registry.ordered():
            executor = PhaseExecutor(phase_config)
            phase_name = phase_config.name

            if phase_name == "observe":
                fn = lambda: self._bridge.observe_environment(session_id, turn_id)  # noqa: E731
            elif phase_name == "drive":
                _ctx = dict(context)
                fn = lambda: self._bridge.evaluate_drive(session_id, turn_id, _ctx)  # noqa: E731
            elif phase_name == "frame":
                _ctx = enrich_context_for_objective_phase(context=context, phase_name=phase_name)
                fn = lambda: self._bridge.evaluate_cognition(session_id, turn_id, _ctx)  # noqa: E731
            elif phase_name == "working_state":
                fn = lambda: self._working_state_phase(working_memory, context)  # noqa: E731
            elif phase_name == "cognitive_risks":
                _ctx = dict(context)
                fn = lambda: self._bridge.detect_conflicts(session_id, _ctx)  # noqa: E731
            elif phase_name == "simulate":
                _ctx = dict(context)
                fn = lambda: self._bridge.run_simulation(session_id, _ctx)  # noqa: E731
            elif phase_name == "metacognition":
                _ctx = dict(context)
                fn = lambda: self._bridge.run_metacognition(session_id, _ctx)  # noqa: E731
            elif phase_name == "cognitive_tools":
                _ctx = dict(context)
                fn = lambda: self._bridge.invoke_cognitive_tools(session_id, _ctx)  # noqa: E731
            elif phase_name == "decision_synthesis":
                _ctx = enrich_context_for_objective_phase(context=context, phase_name=phase_name)
                fn = lambda: self._bridge.synthesize_decision(session_id, _ctx)  # noqa: E731
            elif phase_name == "consolidate":
                _ctx = dict(context)
                fn = lambda: self._bridge.consolidate_memory(session_id, turn_id, _ctx)  # noqa: E731
            else:
                # Unknown phase — skip gracefully
                results.append(
                    PhaseResult(
                        phase_name=phase_name,
                        skipped=True,
                        error=f"No handler registered for phase '{phase_name}'",
                    )
                )
                continue

            phase_result = executor.execute(fn)

            if phase_name == "cognitive_risks" and not phase_result.skipped and not phase_result.error:
                interrupt_result = self._apply_cognitive_risk_interrupts(
                    working_memory=working_memory,
                    turn_id=turn_id,
                    output=phase_result.output,
                )
                if interrupt_result:
                    phase_result.output.update(interrupt_result)

            results.append(phase_result)

            # Merge non-skipped, non-error output into the running context
            if not phase_result.skipped and not phase_result.error and phase_result.output:
                context.update(phase_result.output)

        return results

    # ------------------------------------------------------------------
    # Internal phase handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _working_state_phase(
        working_memory: WorkingMemoryController,
        context: dict,
    ) -> dict:
        """Snapshot working memory; optionally refresh from context."""
        temporal_state = context.get("temporal_agenda_state")
        candidates = ThinkLoop._attention_candidates_from_context(context)
        consumed_temporal_ids: list[Any] = []
        if isinstance(temporal_state, dict):
            temporal_candidates = temporal_state.get("resurfaced_attention_candidates") or []
            if temporal_candidates:
                candidates.extend(temporal_candidates)
                consumed_temporal_ids = list(temporal_state.get("review_now_item_ids") or [])
        if not candidates:
            candidates = [ThinkLoop._turn_attention_candidate(context)]
        tick_id = str(
            context.get("turn_id")
            or (temporal_state.get("state_id") if isinstance(temporal_state, dict) else None)
            or "working-state"
        )
        frame_update = working_memory.update_frame(
            tick_id=tick_id,
            new_candidates=candidates,
            attention_budget=context.get("attention_budget"),
        )
        # Write current context summary into working memory
        working_memory.write(
            key="last_context_snapshot",
            value={k: v for k, v in context.items() if isinstance(v, (str, int, float, bool))},
            priority=5,
        )
        return {
            "slots": working_memory.snapshot(),
            "working_memory_frame": frame_update["frame"],
            "attention_shift_events": frame_update["attention_shift_events"],
            "working_memory_rejected_candidates": frame_update["rejected_candidates"],
            "temporal_agenda_candidates_consumed": bool(consumed_temporal_ids),
            "consumed_temporal_review_item_ids": consumed_temporal_ids,
        }

    @staticmethod
    def _attention_candidates_from_context(context: dict) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for key in ("attention_candidates", "new_attention_items", "working_memory_candidates", "resurfaced_attention_candidates"):
            value = context.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
        for index, goal in enumerate(context.get("goals") or context.get("current_goals") or []):
            if not isinstance(goal, dict):
                continue
            source_ref = str(goal.get("goal_id") or goal.get("id") or goal.get("source_ref") or "").strip()
            title = str(goal.get("title") or goal.get("name") or "").strip()
            summary = str(goal.get("summary") or goal.get("description") or title).strip()
            if source_ref and title and summary:
                candidates.append(
                    {
                        "focus_id": str(goal.get("focus_id") or f"goal-focus-{source_ref}"),
                        "focus_type": "goal",
                        "title": title,
                        "summary": summary,
                        "source_ref": source_ref,
                        "priority": float(goal.get("priority", 3)),
                        "urgency": float(goal.get("urgency", 2)),
                        "uncertainty": float(goal.get("uncertainty", 1)),
                        "interruptible": True,
                        "resume_hint": "Resume when higher-priority turn focus is cleared.",
                    }
                )
        return candidates

    @staticmethod
    def _turn_attention_candidate(context: dict) -> dict[str, Any]:
        turn_id = str(context.get("turn_id") or "unknown-turn")
        user_input = str(context.get("user_input") or "").strip()
        summary = user_input[:240] if user_input else "Current turn requires attention refresh."
        return {
            "focus_id": f"turn-focus-{turn_id}",
            "focus_type": "turn",
            "title": "Current turn request",
            "summary": summary,
            "source_ref": f"turn:{turn_id}:user_input",
            "priority": 3.0,
            "urgency": 2.0,
            "uncertainty": 1.0,
            "interruptible": True,
            "resume_hint": "Resume after higher-priority risk or agenda focus is cleared.",
        }

    @staticmethod
    def _apply_cognitive_risk_interrupts(
        *,
        working_memory: WorkingMemoryController,
        turn_id: str,
        output: dict,
    ) -> dict[str, Any]:
        items = ThinkLoop._risk_interrupt_items_from_output(output)
        if not items:
            return {}
        applied: list[dict[str, Any]] = []
        for item in items:
            result = working_memory.interrupt(high_risk_item=item, tick_id=f"{turn_id}:cognitive_risks")
            applied.append(result)
        latest = applied[-1]["frame"]
        return {
            "working_memory_frame": latest,
            "cognitive_risk_interrupts_applied": applied,
            "attention_shift_events": [
                event
                for result in applied
                for event in result.get("attention_shift_events", [])
            ],
        }

    @staticmethod
    def _risk_interrupt_items_from_output(output: dict) -> list[dict[str, Any]]:
        explicit: list[dict[str, Any]] = []
        for key in ("risk_interrupt_items", "high_risk_attention_items", "attention_interrupts"):
            value = output.get(key)
            if isinstance(value, list):
                explicit.extend(item for item in value if isinstance(item, dict))
        if explicit:
            return [ThinkLoop._normalize_risk_interrupt_item(item, index) for index, item in enumerate(explicit)]
        derived: list[dict[str, Any]] = []
        for index, trigger in enumerate(output.get("self_correction_triggers") or []):
            if isinstance(trigger, dict):
                derived.append(ThinkLoop._risk_item_from_event(trigger, index, default_type="self_correction"))
        for index, report in enumerate(output.get("conflict_reports") or []):
            if not isinstance(report, dict):
                continue
            severity = str(report.get("severity") or report.get("risk_level") or "medium").lower()
            if severity in {"high", "critical"}:
                derived.append(ThinkLoop._risk_item_from_event(report, index, default_type="conflict"))
        return derived

    @staticmethod
    def _normalize_risk_interrupt_item(item: dict[str, Any], index: int) -> dict[str, Any]:
        normalized = dict(item)
        normalized.setdefault("focus_id", f"risk-interrupt-{index}")
        normalized.setdefault("focus_type", "risk")
        normalized.setdefault("title", str(item.get("title") or item.get("trigger_type") or item.get("conflict_type") or "High risk interrupt"))
        normalized.setdefault("summary", str(item.get("summary") or item.get("reason") or item.get("description") or normalized["title"]))
        normalized.setdefault("source_ref", str(item.get("source_ref") or item.get("trigger_id") or item.get("report_id") or normalized["focus_id"]))
        normalized.setdefault("priority", 10.0)
        normalized.setdefault("urgency", 10.0)
        normalized.setdefault("uncertainty", 1.0)
        normalized.setdefault("interruptible", False)
        normalized.setdefault("resume_hint", "Resume lower-priority focus after high-risk interrupt is reviewed.")
        normalized["risk_interrupt"] = True
        return normalized

    @staticmethod
    def _risk_item_from_event(event: dict[str, Any], index: int, *, default_type: str) -> dict[str, Any]:
        event_id = str(event.get("trigger_id") or event.get("report_id") or event.get("conflict_id") or f"{default_type}-{index}")
        return ThinkLoop._normalize_risk_interrupt_item(
            {
                "focus_id": f"risk-focus-{event_id}",
                "focus_type": "risk",
                "title": str(event.get("title") or event.get("trigger_type") or event.get("conflict_type") or "Cognitive risk interrupt"),
                "summary": str(event.get("reason") or event.get("summary") or event.get("description") or "Cognitive risk requires attention switch."),
                "source_ref": event_id,
                "priority": 10.0,
                "urgency": 10.0,
                "uncertainty": float(event.get("uncertainty") or 1.0),
            },
            index,
        )
