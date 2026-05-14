from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ExecutionFailure:
    failure_type: str
    failure_code: str
    message: str
    retryable: bool = False
    details: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "failure_code": self.failure_code,
            "message": self.message,
            "retryable": self.retryable,
            "details": dict(self.details or {}),
        }


class ReactExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_code: str = "REACT_EXECUTION_ERROR",
        failure_type: str = "execution_error",
        retryable: bool = False,
        details: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure = ExecutionFailure(
            failure_type=failure_type,
            failure_code=failure_code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
