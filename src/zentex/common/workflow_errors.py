from __future__ import annotations

from typing import Any


class WorkflowError(RuntimeError):
    """Base class for full-workflow runtime support failures."""

    default_error_code = "WORKFLOW_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        failures: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code or self.default_error_code
        self.failures = list(failures or [])
        self.context = dict(context or {})
        super().__init__(message)

    def to_failure(self) -> dict[str, Any]:
        failure: dict[str, Any] = {
            "error_code": self.error_code,
            "error_type": type(self).__name__,
            "message": str(self),
        }
        if self.failures:
            failure["failures"] = self.failures
        if self.context:
            failure["context"] = self.context
        return failure


class WorkflowExecutionError(WorkflowError):
    default_error_code = "WORKFLOW_EXECUTION_ERROR"


class WorkflowEvidenceError(WorkflowError):
    default_error_code = "WORKFLOW_EVIDENCE_ERROR"


class WorkflowAuditChainError(WorkflowError):
    default_error_code = "WORKFLOW_AUDIT_CHAIN_ERROR"


class WorkflowWritebackError(WorkflowError):
    default_error_code = "WORKFLOW_WRITEBACK_ERROR"


class WorkflowEvolutionError(WorkflowError):
    default_error_code = "WORKFLOW_EVOLUTION_ERROR"

