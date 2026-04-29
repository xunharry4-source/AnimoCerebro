from __future__ import annotations

"""Explicit dispatch routing failures."""


class DispatchRoutingError(RuntimeError):
    """Raised when router execution fails before a valid dispatch decision exists."""


class NoMatchingExecutorError(DispatchRoutingError):
    """Raised when no internal or external executor satisfies task capabilities."""

    def __init__(self, *, task_id: str, required_capabilities: list[str]) -> None:
        self.task_id = task_id
        self.required_capabilities = list(required_capabilities)
        super().__init__(
            "No matching executor found for task "
            f"{task_id} with required_capabilities={self.required_capabilities}"
        )
