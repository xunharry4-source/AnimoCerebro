from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""SessionRegistry — lightweight read-only view over SessionLifecycleManager."""

from zentex.foundation.contracts import SessionStatus
from zentex.kernel.session_domain.session import KernelSession
from zentex.kernel.session_domain.session_lifecycle import SessionLifecycleManager


class SessionRegistry:
    """Provides a read-only window into active sessions.

    This class deliberately exposes no mutating operations; all lifecycle
    changes go through :class:`SessionLifecycleManager`.
    """

    def __init__(self, lifecycle: SessionLifecycleManager) -> None:
        self._lifecycle = lifecycle

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Optional[KernelSession]:
        """Return the KernelSession for *session_id*, or None."""
        return self._lifecycle.get_session(session_id)

    def count_active(self) -> int:
        """Return the number of sessions with status *active* or *idle*."""
        return len(self._lifecycle.list_active_sessions())

    def all_sessions(self) -> list[KernelSession]:
        """Return every session currently known to the lifecycle manager."""
        return self._lifecycle._all_sessions()

    def health_summary(self) -> dict:
        """Return a dict with counts: active, suspended, and total."""
        sessions = self.all_sessions()
        active_statuses = {SessionStatus.active, SessionStatus.idle}
        active = sum(1 for s in sessions if s.status in active_statuses)
        suspended = sum(1 for s in sessions if s.status == SessionStatus.suspended)
        return {
            "active": active,
            "suspended": suspended,
            "total": len(sessions),
        }

    def __repr__(self) -> str:
        return (
            f"SessionRegistry("
            f"active={self.count_active()}, "
            f"total={len(self.all_sessions())})"
        )
