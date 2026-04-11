from __future__ import annotations

"""
Runtime wrapper for real LLM upgrade execution.

This module requires an explicit optimizer runner. If no optimizer runtime is
provided, execution is blocked instead of silently falling back to rule-based
planning or fake optimization.
"""

from collections.abc import Callable
from typing import Any

from zentex.upgrade.llm.models import LLMUpgradeCandidate


class LLMUpgradeRuntime:
    """Fail-closed runtime for executing an LLM upgrade candidate."""

    def __init__(
        self,
        *,
        optimizer_runner: Callable[[LLMUpgradeCandidate], dict[str, Any]] | None = None,
    ) -> None:
        self._optimizer_runner = optimizer_runner

    def execute_candidate(
        self,
        candidate: LLMUpgradeCandidate,
    ) -> dict[str, Any]:
        if self._optimizer_runner is None:
            raise RuntimeError(
                "LLM upgrade execution requires a real optimizer runner; "
                "rule-based fallback is not allowed."
            )
        return self._optimizer_runner(candidate)
