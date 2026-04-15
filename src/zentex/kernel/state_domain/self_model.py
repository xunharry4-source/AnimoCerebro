"""SelfModelEngine — tracks cognitive load, stability, and confidence drift."""

import threading

from zentex.foundation.meta import TURN_MAX_DURATION_SECONDS

# Convert the constant (seconds) to milliseconds for comparison against
# the duration_ms values supplied by callers.
_TURN_MAX_DURATION_MS: float = float(TURN_MAX_DURATION_SECONDS * 1000)

_STABILITY_DEGRADATION_PER_ERROR: float = 0.05
_STABILITY_MIN: float = 0.0
_STABILITY_MAX: float = 1.0
_CONFIDENCE_MIN: float = -1.0
_CONFIDENCE_MAX: float = 1.0
_LOAD_WINDOW: int = 5  # number of recent turns used for avg


class SelfModelEngine:
    """Maintains a lightweight self-model of the kernel's cognitive state.

    All metrics are derived from the stream of completed turns:

    - *cognitive_load*: rolling average turn duration normalised to
      TURN_MAX_DURATION_SECONDS, capped at 1.0.
    - *stability_score*: starts at 1.0 and degrades slightly on every turn
      that produced phase errors.
    - *confidence_drift*: accumulates signed deltas from callers; clamped
      to [-1.0, 1.0].
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._cognitive_load: float = 0.0
        self._stability_score: float = 1.0
        self._confidence_drift: float = 0.0
        self._turn_durations: list[float] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Turn recording
    # ------------------------------------------------------------------

    def record_turn(self, duration_ms: float, phase_error_count: int) -> None:
        """Update the self-model after a completed turn.

        Args:
            duration_ms:        Wall-clock duration of the turn in milliseconds.
            phase_error_count:  Number of phases that raised errors during this turn.
        """
        with self._lock:
            self._turn_durations.append(duration_ms)

            # Cognitive load — rolling average of last N durations
            window = self._turn_durations[-_LOAD_WINDOW:]
            avg_ms = sum(window) / len(window)
            raw_load = avg_ms / _TURN_MAX_DURATION_MS
            self._cognitive_load = min(raw_load, 1.0)

            # Stability — degrade for each phase error
            if phase_error_count > 0:
                degradation = _STABILITY_DEGRADATION_PER_ERROR * phase_error_count
                self._stability_score = max(
                    _STABILITY_MIN,
                    self._stability_score - degradation,
                )

    # ------------------------------------------------------------------
    # Confidence drift
    # ------------------------------------------------------------------

    def update_confidence(self, delta: float) -> None:
        """Add *delta* to confidence_drift, clamped to [-1.0, 1.0]."""
        with self._lock:
            new_val = self._confidence_drift + delta
            self._confidence_drift = max(
                _CONFIDENCE_MIN, min(_CONFIDENCE_MAX, new_val)
            )

    def reset_drift(self) -> None:
        """Reset confidence_drift to 0.0."""
        with self._lock:
            self._confidence_drift = 0.0

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a plain-dict snapshot of the current self-model state."""
        with self._lock:
            return {
                "session_id": self._session_id,
                "cognitive_load": self._cognitive_load,
                "stability_score": self._stability_score,
                "confidence_drift": self._confidence_drift,
                "turn_count": len(self._turn_durations),
            }

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"SelfModelEngine("
            f"session_id={snap['session_id']!r}, "
            f"load={snap['cognitive_load']:.2f}, "
            f"stability={snap['stability_score']:.2f})"
        )
