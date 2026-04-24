from __future__ import annotations

"""KernelSession — the primary session object managed by the kernel."""

from datetime import datetime, timezone

from zentex.foundation.contracts import SessionMeta, SessionStatus

UTC = timezone.utc


class KernelSession:
    """Represents a single user session within the kernel.

    Wraps SessionMeta and carries a _state_refs dict so other kernel
    domains (working memory, transcript, etc.) can attach themselves
    to the session without circular imports.
    """

    def __init__(self, session_id: str, user_id: str = "") -> None:
        self.session_id: str = session_id
        self.meta: SessionMeta = SessionMeta(
            session_id=session_id,
            user_id=user_id,
            status=SessionStatus.active,
        )
        self.status: SessionStatus = SessionStatus.active
        self._state_refs: dict = {}
        
        # Stability metrics (Resilience Phase 5)
        self.stability_score: float = 1.0 # 1.0 = perfect, 0.0 = collapsed
        self.error_count: int = 0
        self.critical_failures: list[str] = []

    # ------------------------------------------------------------------
    # Resilience API
    # ------------------------------------------------------------------

    def record_error(self, error_msg: str, is_critical: bool = False) -> None:
        """Record an error and update stability score."""
        self.error_count += 1
        if is_critical:
            self.critical_failures.append(f"{datetime.now(UTC).isoformat()}: {error_msg}")
            self.stability_score = max(0.0, self.stability_score - 0.2)
        else:
            self.stability_score = max(0.0, self.stability_score - 0.05)

        # Auto-degradation
        if self.stability_score < 0.5 and self.status != SessionStatus.terminated:
            self.set_status(SessionStatus.suspended)
            self.critical_failures.append(f"SYSTEM: Session auto-suspended due to low stability ({self.stability_score:.2f})")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_meta(self) -> SessionMeta:
        """Return the current SessionMeta for this session."""
        return self.meta

    def set_status(self, status: SessionStatus) -> None:
        """Update session status and rebuild meta with new status and last_active_at."""
        self.status = status
        self.meta = SessionMeta(
            session_id=self.meta.session_id,
            user_id=self.meta.user_id,
            created_at=self.meta.created_at,
            last_active_at=datetime.now(UTC),
            status=status,
        )

    def touch(self) -> None:
        """Update last_active_at to now without changing status."""
        self.meta = SessionMeta(
            session_id=self.meta.session_id,
            user_id=self.meta.user_id,
            created_at=self.meta.created_at,
            last_active_at=datetime.now(UTC),
            status=self.meta.status,
        )

    def to_snapshot(self) -> dict:
        """Return a plain dict snapshot of this session."""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "meta": self.meta.model_dump(),
        }

    def attach_state(self, key: str, ref: object) -> None:
        """Store a kernel-internal state reference under *key*."""
        self._state_refs[key] = ref

    def get_state(self, key: str) -> Optional[object]:
        """Retrieve a previously attached state reference, or None."""
        return self._state_refs.get(key)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"KernelSession(session_id={self.session_id!r}, "
            f"status={self.status!r})"
        )
