"""ThinkLoop — orchestrates the 9-phase cognitive cycle for a single turn.

Also defines KernelServiceBridge, the Protocol that decouples flow_domain
from concrete external service implementations.
"""

from typing import Protocol, runtime_checkable

from zentex.foundation.contracts import PhaseResult, TurnRequest
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
        registry: PhaseRegistry | None = None,
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
            elif phase_name == "frame":
                _ctx = dict(context)
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
                _ctx = dict(context)
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
        # Write current context summary into working memory
        working_memory.write(
            key="last_context_snapshot",
            value={k: v for k, v in context.items() if isinstance(v, (str, int, float, bool))},
            priority=5,
        )
        return {"slots": working_memory.snapshot()}
