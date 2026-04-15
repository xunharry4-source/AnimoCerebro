"""NineQuestionStartupCoordinator — drives the bootstrap sequence."""

from zentex.kernel.cognition_flow.executor import NineQuestionExecutor
from zentex.kernel.cognition_flow.models import BootstrapStatus, NineQuestionResponse
from zentex.kernel.cognition_flow.router import NineQuestionRouter
from zentex.kernel.cognition_flow.snapshot_builder import StartupSnapshotBuilder
from zentex.kernel.cognition_flow.state import NineQuestionStateManager
from zentex.kernel.state_domain import (
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
)


class NineQuestionStartupCoordinator:
    """Coordinates the full nine-question bootstrap sequence for a session.

    Sequence:
    1. Write bootstrap_start transcript entry.
    2. Set bootstrap status to in_progress.
    3. Build startup snapshot context via snapshot_builder.
    4. Plan which questions need answering via router.
    5. Execute planned questions via executor.
    6. Determine final status based on success/failure counts.
    7. Write bootstrap_end transcript entry.
    8. Return final BootstrapStatus.
    """

    def __init__(
        self,
        router: NineQuestionRouter,
        executor: NineQuestionExecutor,
        snapshot_builder: StartupSnapshotBuilder,
    ) -> None:
        self._router = router
        self._executor = executor
        self._snapshot_builder = snapshot_builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def coordinate(
        self,
        session_id: str,
        state_manager: NineQuestionStateManager,
        transcript: TranscriptStore,
    ) -> BootstrapStatus:
        """Run the full bootstrap sequence and return the resulting status.

        Args:
            session_id:    The active session identifier.
            state_manager: Mutable nine-question state for this session.
            transcript:    Transcript store for this session.

        Returns:
            The final BootstrapStatus after the run.
        """
        # Step 1 — write bootstrap_start
        transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.bootstrap_start,
                session_id=session_id,
                payload={"session_id": session_id},
            )
        )

        # Step 2 — mark in-progress
        state_manager.set_bootstrap_status(BootstrapStatus.in_progress)

        # Step 3 — build startup snapshot context
        context: dict = self._snapshot_builder.build(session_id)

        # Step 4 — plan questions
        current_state = state_manager.get_state()
        planned = self._router.plan(current_state)
        ordered = self._router.get_execution_order(planned)

        # Step 5 — execute questions
        responses: list[NineQuestionResponse] = self._executor.execute(
            questions=ordered,
            context=context,
            state_manager=state_manager,
            transcript=transcript,
        )

        # Step 6 — determine final status
        failure_count = sum(1 for r in responses if r.error)
        if responses and failure_count == len(responses):
            final_status = BootstrapStatus.failed
        else:
            final_status = BootstrapStatus.completed

        state_manager.set_bootstrap_status(final_status)

        # Step 7 — write bootstrap_end
        answered_count = sum(1 for r in responses if r.answer and not r.error)
        transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.bootstrap_end,
                session_id=session_id,
                payload={
                    "status": str(final_status),
                    "answered": answered_count,
                    "failed": failure_count,
                    "total": len(responses),
                },
            )
        )

        return final_status
