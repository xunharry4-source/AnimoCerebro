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

    def get_state(self, key: str) -> object | None:
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
