"""TurnResultBuilder — assembles a TurnResult from accumulated PhaseResults."""

from datetime import datetime, timezone

from zentex.foundation.contracts import PhaseResult, TurnResult, TurnStatus

UTC = timezone.utc


class TurnResultBuilder:
    """Accumulates PhaseResults and builds the final TurnResult for a turn."""

    def __init__(self, turn_id: str, session_id: str) -> None:
        self._turn_id = turn_id
        self._session_id = session_id
        self._phase_results: list[PhaseResult] = []
        self._started_at: datetime = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def add_phase(self, result: PhaseResult) -> None:
        """Append a PhaseResult to the accumulator."""
        self._phase_results.append(result)

    # ------------------------------------------------------------------
    # Response extraction
    # ------------------------------------------------------------------

    def extract_response(self) -> str:
        """Return the response string from the decision_synthesis phase output.

        Falls back to "" if the phase is absent or did not produce a response.
        """
        for pr in self._phase_results:
            if pr.phase_name == "decision_synthesis" and not pr.skipped:
                return pr.output.get("response", "")
        return ""

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        status: TurnStatus,
        response: str = "",
        audit_trail_id: str = "",
    ) -> TurnResult:
        """Construct and return the TurnResult.

        Args:
            status:         Final turn status.
            response:       Response string; if empty, extract_response() is used.
            audit_trail_id: Optional reference to the audit trail record.
        """
        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - self._started_at).total_seconds() * 1000.0

        resolved_response = response if response else self.extract_response()

        return TurnResult(
            turn_id=self._turn_id,
            session_id=self._session_id,
            status=status,
            response=resolved_response,
            phase_results=list(self._phase_results),
            audit_trail_id=audit_trail_id,
            duration_ms=duration_ms,
            completed_at=completed_at,
        )
