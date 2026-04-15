from __future__ import annotations


class TaskStateError(Exception):
    """Raised when an illegal task state transition occurs."""

