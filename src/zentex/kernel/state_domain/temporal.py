"""CognitiveTemporalEngine — session and turn timing bookkeeping."""

import threading
from datetime import datetime, timezone

UTC = timezone.utc


class CognitiveTemporalEngine:
    """Tracks wall-clock timing for sessions and individual turns.

    Each turn is stored as a tuple of (turn_id, start_datetime, end_datetime | None).
    Methods are thread-safe.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._session_start: datetime = datetime.now(UTC)
        # list of (turn_id, start, end | None)
        self._turn_timestamps: list[tuple[str, datetime, datetime | None]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Turn events
    # ------------------------------------------------------------------

    def record_turn_start(self, turn_id: str) -> None:
        """Record the start of a new turn."""
        with self._lock:
            self._turn_timestamps.append((turn_id, datetime.now(UTC), None))

    def record_turn_end(self, turn_id: str) -> None:
        """Set the end timestamp for the turn identified by *turn_id*.

        If the turn_id is not found this is a no-op.
        """
        now = datetime.now(UTC)
        with self._lock:
            for i, (tid, start, _end) in enumerate(self._turn_timestamps):
                if tid == turn_id:
                    self._turn_timestamps[i] = (tid, start, now)
                    break

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------

    def session_elapsed_seconds(self) -> float:
        """Return total seconds since the session started."""
        return (datetime.now(UTC) - self._session_start).total_seconds()

    def average_turn_duration_ms(self) -> float:
        """Return the mean duration in milliseconds of all *completed* turns.

        Returns 0.0 if there are no completed turns.
        """
        with self._lock:
            completed = [
                (end - start).total_seconds() * 1000.0
                for _tid, start, end in self._turn_timestamps
                if end is not None
            ]
        if not completed:
            return 0.0
        return sum(completed) / len(completed)

    def last_turn_gap_seconds(self) -> float | None:
        """Return seconds between the last two turn starts.

        Returns None if fewer than two turns have been recorded.
        """
        with self._lock:
            starts = [start for _tid, start, _end in self._turn_timestamps]
        if len(starts) < 2:
            return None
        return (starts[-1] - starts[-2]).total_seconds()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a summary dict of temporal state."""
        with self._lock:
            total_turns = len(self._turn_timestamps)
            completed_turns = sum(
                1 for _tid, _start, end in self._turn_timestamps if end is not None
            )

        return {
            "session_id": self._session_id,
            "session_start": self._session_start.isoformat(),
            "session_elapsed_seconds": self.session_elapsed_seconds(),
            "total_turns": total_turns,
            "completed_turns": completed_turns,
            "average_turn_duration_ms": self.average_turn_duration_ms(),
            "last_turn_gap_seconds": self.last_turn_gap_seconds(),
        }

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"CognitiveTemporalEngine("
            f"session_id={snap['session_id']!r}, "
            f"elapsed={snap['session_elapsed_seconds']:.1f}s, "
            f"turns={snap['total_turns']})"
        )
