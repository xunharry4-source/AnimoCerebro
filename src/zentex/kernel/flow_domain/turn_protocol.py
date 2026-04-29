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
        
        Implementation uses a Staged Commitment pattern: entries are buffered 
        in memory and only appended to the durable TranscriptStore at the end 
        of the turn to avoid log pollution from non-finalized states.
        """
        turn_id = request.turn_id
        session_id = request.session_id
        staged_entries: list[TranscriptEntry] = []

        # 1. Record turn start in temporal engine
        temporal.record_turn_start(turn_id)

        # 2. Stage turn_start transcript entry
        staged_entries.append(
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

        # 5. Stage each phase result and add to builder
        for pr in phase_results:
            builder.add_phase(pr)
            staged_entries.append(
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
        self._stage_working_memory_entries(
            staged_entries=staged_entries,
            session_id=session_id,
            turn_id=turn_id,
            phase_results=phase_results,
        )

        # 6. Determine final status
        status = self._resolve_status(phase_results)

        # 7. Extract response (builder handles fallback to "")
        response = builder.extract_response()

        # 8. Build TurnResult
        turn_result = builder.build(status=status, response=response)

        phase_error_count = sum(1 for pr in phase_results if pr.error and not pr.skipped)
        if status != TurnStatus.failed:
            living_update = self._update_living_self_model_from_turn(
                self_model=self_model,
                turn_result=turn_result,
                phase_error_count=phase_error_count,
                phase_results=phase_results,
            )
            staged_entries.append(
                TranscriptEntry(
                    entry_type=TranscriptEntryType.living_self_model_updated,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=f"living-self:turn:{turn_id}",
                    source="zentex.kernel.flow_domain.turn_protocol",
                    payload={
                        "feature_code": "B2-53",
                        "entry_type": "living_self_model_updated",
                        "operation": "phase9_update_from_turn_result",
                        "model_id": living_update["living_self_model"]["model_id"],
                        "current_state": living_update["living_self_model"]["current_state"],
                        "recent_weakness_count": len(living_update["living_self_model"]["recent_weaknesses"]),
                        "confidence_drift_count": len(living_update["living_self_model"]["confidence_drift_indicators"]),
                        "living_self_model_status": living_update["living_self_model_status"],
                    },
                )
            )

        # 9. Stage turn_end transcript entry
        staged_entries.append(
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
        
        # 10. COMMIT ALL STAGED ENTRIES ATOMICALLY
        for entry in staged_entries:
            transcript.append(entry)

        # 11. STAGED COMMITMENT: Only update self-model and temporal if the turn succeeded/partially failed.
        # This prevents absolute failures (e.g. crashes in required phases) from 
        # polluting the long-term cognitive health model or leaving dangling 'turn_start' records.
        if status != TurnStatus.failed:
            temporal.record_turn_end(turn_id)
        else:
            # For failed turns, we record the end in temporal to close the span, 
            # but we skip updating the self-model metrics to avoid skewing rolling averages.
            temporal.record_turn_end(turn_id)

        # 12. Touch session
        session.touch()

        return turn_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_status(self, phase_results: list[PhaseResult]) -> TurnStatus:
        """Return status based on phase outcomes."""
        any_error = False
        for pr in phase_results:
            if pr.error and not pr.skipped:
                # If a required phase failed, the whole turn fails
                if pr.phase_name in self._REQUIRED_PHASES:
                    return TurnStatus.failed
                any_error = True
        
        return TurnStatus.partial_failed if any_error else TurnStatus.completed

    def _stage_working_memory_entries(
        self,
        *,
        staged_entries: list[TranscriptEntry],
        session_id: str,
        turn_id: str,
        phase_results: list[PhaseResult],
    ) -> None:
        for pr in phase_results:
            frame = pr.output.get("working_memory_frame") if isinstance(pr.output, dict) else None
            events = self._attention_events_from_output(pr.output if isinstance(pr.output, dict) else {})
            if frame:
                staged_entries.append(
                    TranscriptEntry(
                        entry_type=TranscriptEntryType.working_memory_updated,
                        session_id=session_id,
                        turn_id=turn_id,
                        trace_id=f"working-memory:{pr.phase_name}:{turn_id}",
                        source="zentex.kernel.flow_domain.turn_protocol",
                        payload={
                            "feature_code": "B1-52",
                            "entry_type": "working_memory_updated",
                            "operation": f"think_loop_{pr.phase_name}",
                            "frame_id": frame.get("frame_id"),
                            "tick_id": frame.get("tick_id"),
                            "active_focus_ids": frame.get("active_focus_ids") or [],
                            "suspended_focus_ids": frame.get("suspended_focus_ids") or [],
                            "recently_considered_refs": frame.get("recently_considered_refs") or [],
                        },
                    )
                )
            for event in events:
                staged_entries.append(
                    TranscriptEntry(
                        entry_type=TranscriptEntryType.working_memory_updated,
                        session_id=session_id,
                        turn_id=turn_id,
                        trace_id=f"attention-shift:{event.get('event_id')}",
                        source="zentex.kernel.flow_domain.turn_protocol",
                        payload={
                            "feature_code": "B1-52",
                            "entry_type": "attention_shift_event",
                            **event,
                        },
                    )
                )

    def _update_living_self_model_from_turn(
        self,
        *,
        self_model: SelfModelEngine,
        turn_result: TurnResult,
        phase_error_count: int,
        phase_results: list[PhaseResult],
    ) -> dict:
        recent_events = self._recent_events_from_phase_results(phase_results)
        working_memory_frame = self._latest_working_memory_frame(phase_results)
        return self_model.update_from_turn_result(
            {
                "turn_id": turn_result.turn_id,
                "status": turn_result.status.value,
                "failed": turn_result.status == TurnStatus.failed,
                "phase_error_count": phase_error_count,
                "duration_ms": turn_result.duration_ms,
                "risk_hit": any(event.get("event_type") in {"conflict", "attention_interrupt"} for event in recent_events),
                "evidence_refs": [event["evidence_refs"][0] for event in recent_events if event.get("evidence_refs")],
            },
            recent_events=recent_events,
            working_memory_frame=working_memory_frame,
            trace_id=f"turn:{turn_result.turn_id}",
        )

    @staticmethod
    def _latest_working_memory_frame(phase_results: list[PhaseResult]) -> dict | None:
        for pr in reversed(phase_results):
            frame = pr.output.get("working_memory_frame") if isinstance(pr.output, dict) else None
            if isinstance(frame, dict):
                return frame
        return None

    @classmethod
    def _recent_events_from_phase_results(cls, phase_results: list[PhaseResult]) -> list[dict]:
        events: list[dict] = []
        for pr in phase_results:
            if pr.error and not pr.skipped:
                events.append(
                    {
                        "event_type": "phase_error",
                        "error_code": pr.phase_name,
                        "severity": "high",
                        "evidence_refs": [f"phase:{pr.phase_name}"],
                    }
                )
            output = pr.output if isinstance(pr.output, dict) else {}
            for report in output.get("conflict_reports") or []:
                if isinstance(report, dict):
                    events.append(
                        {
                            "event_type": "conflict",
                            "conflict_type": report.get("conflict_type") or report.get("type") or "cognitive_conflict",
                            "severity": report.get("severity") or report.get("risk_level") or "medium",
                            "evidence_refs": report.get("evidence_refs") or [f"phase:{pr.phase_name}:conflict"],
                        }
                    )
            for event in cls._attention_events_from_output(output):
                events.append(
                    {
                        "event_type": "attention_interrupt",
                        "error_code": event.get("shift_reason") or "attention_shift",
                        "severity": "high" if event.get("shift_reason") == "high_risk_interrupt" else "medium",
                        "evidence_refs": [event.get("event_id") or f"phase:{pr.phase_name}:attention_shift"],
                    }
                )
        return events

    @staticmethod
    def _attention_events_from_output(output: dict) -> list[dict]:
        events: list[dict] = []
        for event in output.get("attention_shift_events") or []:
            if isinstance(event, dict):
                events.append(event)
        for result in output.get("cognitive_risk_interrupts_applied") or []:
            if isinstance(result, dict):
                for event in result.get("attention_shift_events") or []:
                    if isinstance(event, dict) and event not in events:
                        events.append(event)
        return events
