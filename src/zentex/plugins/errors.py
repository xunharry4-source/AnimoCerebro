from typing import Optional

class PluginError(Exception):
    """Base category for all plugin-related errors."""
    pass

class PluginExecutionError(PluginError):
    """Raised when a plugin execution fails due to logic errors, timeouts, or contract violations."""
    def __init__(self, message: str, original_exc: Optional[Exception] = None, trace_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.original_exc = original_exc
        self.trace_id = trace_id
