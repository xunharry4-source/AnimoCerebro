"""
Posting workflow structured exceptions.

Purpose:
    Provide fail-closed error objects for node orchestration.

Main responsibilities:
    - Preserve node name, machine-readable code, and details for RCA.
    - Prevent workflow nodes from returning empty success-like values on failure.

Not responsible for:
    - Retrying failed nodes.
    - Rendering user-facing error messages.
    - Swallowing provider, browser, or network failures.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class PostingWorkflowError(RuntimeError):
    """Structured fail-closed workflow error."""

    def __init__(
        self,
        message: str,
        *,
        node: str,
        code: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.node = node
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "code": self.code,
            "message": str(self),
            "details": self.details,
        }
