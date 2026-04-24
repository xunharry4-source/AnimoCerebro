"""NineQuestionStartupCoordinator — drives the bootstrap sequence."""

from typing import Optional
from collections.abc import Callable

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
        max_retries: int = 1,
        rollback_on_failure: bool = False,
        merge_on_partial: bool = False,
        response_updated_callback: Optional[Callable[[NineQuestionResponse], None]] = None,
    ) -> BootstrapStatus:
        """Run the full bootstrap sequence and return the resulting status.
        
        Args:
            session_id:    The active session identifier.
            state_manager: Mutable nine-question state for this session.
            transcript:    Transcript store for this session.
            max_retries:   Max retries for each question.
            rollback_on_failure: Restore previous state if run fails.
            merge_on_partial: Merge partial results into existing state.

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

        def _commit_response(response: NineQuestionResponse) -> None:
            is_failed = bool(response.error)
            current_state = state_manager.get_state()
            existing_resp = current_state.responses.get(response.question_id)

            should_update_state = True
            # Original rollback_on_failure guard: explicit opt-in rollback.
            if is_failed and rollback_on_failure and existing_resp and not existing_resp.error:
                should_update_state = False

            if should_update_state:
                # Nine-questions partial-success contract: a failed re-run must
                # NOT overwrite a previously successful answer.  Use merge_partial
                # so only diagnostic/error metadata is written; the existing answer
                # and confidence are preserved.
                existing_has_good_answer = (
                    existing_resp is not None
                    and bool(existing_resp.answer)
                    and not existing_resp.error
                )
                if is_failed and existing_has_good_answer:
                    use_merge = True   # protect existing answer; only merge diagnostics
                else:
                    use_merge = merge_on_partial and response.is_partial
                state_manager.update_response(response, merge_partial=use_merge)

                transcript.append(
                    TranscriptEntry(
                        entry_type=TranscriptEntryType.nine_q_update,
                        session_id=session_id,
                        payload={
                            "question_id": response.question_id,
                            "status": "failed" if is_failed else "partial_failed" if response.is_partial else "success",
                        },
                    )
                )
                if response_updated_callback is not None:
                    response_updated_callback(response)

        # Step 5 — execute questions (sequential; each response can now be committed immediately)
        responses: list[NineQuestionResponse] = self._executor.execute(
            questions=ordered,
            context=context,
            state_manager=state_manager,
            transcript=transcript,
            max_retries=max_retries,
            response_callback=_commit_response,
        )

        # Step 6c — determine final sequence status
        failure_count = sum(1 for r in responses if r.error)
        partial_count = sum(1 for r in responses if r.is_partial and not r.error)
        if not responses:
            final_status = BootstrapStatus.failed
        elif failure_count == len(responses):
            final_status = BootstrapStatus.failed
        elif failure_count > 0 or partial_count > 0:
            final_status = BootstrapStatus.partial_failed
        else:
            final_status = BootstrapStatus.completed

        state_manager.set_bootstrap_status(final_status)

        # Step 7 — write bootstrap_end with Forensic Digest (G38 Compliance)
        answered_count = sum(1 for r in responses if r.answer and not r.error)
        
        # Build Forensic Digest from pollution metrics
        pollution_metrics = state_manager.get_pollution_metrics()
        
        transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.bootstrap_end,
                session_id=session_id,
                payload={
                    "status": str(final_status),
                    "answered": answered_count,
                    "failed": failure_count,
                    "partial": partial_count,
                    "total": len(responses),
                    "forensic_digest": {
                        "pollution_metrics": pollution_metrics,
                        "governance_actions": [
                            # Note: In a real system, this would be cross-referenced with 
                            # audit logs for archiving/promotion.
                            "governance_state_synced"
                        ],
                        "session_stability_score": max(0.0, 1.0 - (pollution_metrics["total_violations"] * 0.1))
                    }
                },
            )
        )

        return final_status
