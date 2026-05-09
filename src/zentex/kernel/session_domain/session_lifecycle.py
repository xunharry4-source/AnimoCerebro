from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""SessionLifecycleManager — thread-safe CRUD operations over KernelSessions."""

import threading
import uuid
from datetime import datetime, timezone

from zentex.foundation.contracts import SessionStatus
from zentex.kernel.session_domain.session import KernelSession

UTC = timezone.utc


class SessionLifecycleManager:
    """Creates, suspends, terminates, and enumerates KernelSessions.

    All public methods are thread-safe via a single reentrant lock.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, KernelSession] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    def create_session(self, user_id: str = "") -> KernelSession:
        """Create a new active KernelSession with a fresh UUID."""
        session_id = str(uuid.uuid4())
        session = KernelSession(session_id=session_id, user_id=user_id)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[KernelSession]:
        """Return the KernelSession for *session_id*, or None if unknown."""
        with self._lock:
            return self._sessions.get(session_id)

    def suspend_session(self, session_id: str) -> bool:
        """Set session status to *suspended*.  Returns False if not found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.set_status(SessionStatus.suspended)
            return True

    def terminate_session(self, session_id: str) -> bool:
        """Set status to *terminated* and remove from registry.

        Returns False if the session was not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.set_status(SessionStatus.terminated)
            del self._sessions[session_id]
            return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_active_sessions(self) -> list[KernelSession]:
        """Return all sessions whose status is *active* or *idle*."""
        with self._lock:
            return [
                s
                for s in self._sessions.values()
                if s.status in (SessionStatus.active, SessionStatus.idle)
            ]

    def check_timeouts(self, timeout_seconds: int) -> list[str]:
        """Return session_ids whose last_active_at is older than *timeout_seconds*.

        The caller is responsible for actually suspending them via
        :meth:`suspend_session`.
        """
        now = datetime.now(UTC)
        timed_out: list[str] = []
        with self._lock:
            for session in self._sessions.values():
                last_active = session.meta.last_active_at
                # Ensure last_active is timezone-aware
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=UTC)
                elapsed = (now - last_active).total_seconds()
                if elapsed > timeout_seconds:
                    timed_out.append(session.session_id)
        return timed_out

    # ------------------------------------------------------------------
    # Internal helpers (not part of public contract)
    # ------------------------------------------------------------------

    def _all_sessions(self) -> list[KernelSession]:
        """Return all registered sessions regardless of status."""
        with self._lock:
            return list(self._sessions.values())

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"SessionLifecycleManager("
                f"sessions={len(self._sessions)})"
            )
