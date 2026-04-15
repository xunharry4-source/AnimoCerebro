"""TurnProtocol — end-to-end execution of a single cognitive turn."""

from zentex.foundation.contracts import PhaseResult, TurnRequest, TurnResult, TurnStatus
from zentex.kernel.flow_domain.think_loop import KernelServiceBridge, ThinkLoop
from zentex.kernel.flow_domain.turn_result import TurnResultBuilder
from zentex.kernel.session_domain import KernelSession
from zentex.kernel.state_domain import (
    CognitiveTemporalEngine,
    SelfModelEngine,
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
    WorkingMemoryController,
)


class TurnProtocol:
    """Coordinates the full lifecycle of a single user turn.

    Responsibilities:
    1. Open and close transcript entries around the turn.
    2. Drive the ThinkLoop through all 9 phases.
    3. Record each PhaseResult in the transcript.
    4. Determine final TurnStatus and assemble TurnResult.
    5. Update temporal engine and self-model with turn metrics.
    6. Touch the session to record activity.
    """

    # Required phases — failure in these makes the whole turn fail.
    _REQUIRED_PHASES: frozenset[str] = frozenset({"observe", "frame", "decision_synthesis"})

    def __init__(
        self,
        bridge: KernelServiceBridge,
        think_loop: ThinkLoop,
    ) -> None:
        self._bridge = bridge
        self._think_loop = think_loop

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        request: TurnRequest,
        session: KernelSession,
        transcript: TranscriptStore,
        working_memory: WorkingMemoryController,
        self_model: SelfModelEngine,
        temporal: CognitiveTemporalEngine,
    ) -> TurnResult:
        """Execute one complete cognitive turn and return its TurnResult.

        Args:
            request:        The incoming TurnRequest.
            session:        The active KernelSession.
            transcript:     Transcript store for this session.
            working_memory: Working memory controller for this session.
            self_model:     Self-model engine for this session.
            temporal:       Temporal engine for this session.

        Returns:
            A fully populated TurnResult.
        """
        turn_id = request.turn_id
        session_id = request.session_id

        # 1. Record turn start in temporal engine
        temporal.record_turn_start(turn_id)

        # 2. Write turn_start transcript entry
        transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.turn_start,
                session_id=session_id,
                turn_id=turn_id,
                payload={"user_input": request.user_input},
            )
        )

        # 3. Create result builder
        builder = TurnResultBuilder(turn_id=turn_id, session_id=session_id)

        # 4. Run the think loop
        phase_results: list[PhaseResult] = self._think_loop.run(
            request=request,
            working_memory=working_memory,
            self_model=self_model,
            temporal=temporal,
        )

        # 5. Record each phase result and add to builder
        for pr in phase_results:
            builder.add_phase(pr)
            transcript.append(
                TranscriptEntry(
                    entry_type=TranscriptEntryType.phase_result,
                    session_id=session_id,
                    turn_id=turn_id,
                    payload={
                        "phase_name": pr.phase_name,
                        "skipped": pr.skipped,
                        "error": pr.error,
                        "duration_ms": pr.duration_ms,
                        "has_output": bool(pr.output),
                    },
                )
            )

        # 6. Determine final status
        status = self._resolve_status(phase_results)

        # 7. Extract response (builder handles fallback to "")
        response = builder.extract_response()

        # 8. Build TurnResult
        turn_result = builder.build(status=status, response=response)

        # 9. Write turn_end transcript entry
        transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.turn_end,
                session_id=session_id,
                turn_id=turn_id,
                payload={
                    "status": str(status),
                    "duration_ms": turn_result.duration_ms,
                    "phase_count": len(phase_results),
                },
            )
        )

        # 10. Record turn end in temporal; update self-model
        temporal.record_turn_end(turn_id)

        phase_error_count = sum(1 for pr in phase_results if pr.error and not pr.skipped)
        self_model.record_turn(
            duration_ms=turn_result.duration_ms,
            phase_error_count=phase_error_count,
        )

        # 11. Touch session
        session.touch()

        return turn_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_status(self, phase_results: list[PhaseResult]) -> TurnStatus:
        """Return completed unless a required phase failed (not skipped)."""
        for pr in phase_results:
            if pr.phase_name in self._REQUIRED_PHASES and pr.error and not pr.skipped:
                return TurnStatus.failed
        return TurnStatus.completed
