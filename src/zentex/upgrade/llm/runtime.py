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
from zentex.upgrade.llm.prompt_optimizer import SectionAwarePromptOptimizerRunner


class LLMUpgradeRuntime:
    """Fail-closed runtime for executing an LLM upgrade candidate."""

    def __init__(
        self,
        *,
        optimizer_runner: Callable[[LLMUpgradeCandidate], dict[str, Optional[Any]]] = None,
        prompt_optimizer_runner: Callable[[LLMUpgradeCandidate], dict[str, Optional[Any]]] = None,
    ) -> None:
        self._optimizer_runner = optimizer_runner
        self._prompt_optimizer_runner = prompt_optimizer_runner

    def execute_candidate(
        self,
        candidate: LLMUpgradeCandidate,
    ) -> dict[str, Any]:
        if self._is_prompt_optimization(candidate):
            return self._execute_prompt_candidate(candidate)
        if self._optimizer_runner is None:
            raise RuntimeError(
                "LLM upgrade execution requires a real optimizer runner; "
                "rule-based fallback is not allowed."
            )
        return self._optimizer_runner(candidate)

    def _is_prompt_optimization(self, candidate: LLMUpgradeCandidate) -> bool:
        metadata = self._candidate_metadata(candidate)
        return str(metadata.get("upgrade_kind") or "") == "prompt_optimization"

    def _execute_prompt_candidate(
        self,
        candidate: LLMUpgradeCandidate,
    ) -> dict[str, Any]:
        if self._prompt_optimizer_runner is None:
            raise RuntimeError(
                "Prompt optimization execution requires a dedicated prompt optimizer runner; "
                "generic optimizer fallback is not allowed."
            )

        result = self._prompt_optimizer_runner(candidate)
        self._validate_prompt_result(candidate, result)
        return result

    def _validate_prompt_result(
        self,
        candidate: LLMUpgradeCandidate,
        result: dict[str, Any],
    ) -> None:
        metadata = self._candidate_metadata(candidate)
        target_prompt_file = str(metadata.get("prompt_file_path") or "").strip()
        if not target_prompt_file:
            raise RuntimeError("Prompt optimization candidate is missing prompt_file_path metadata.")

        modified_files = result.get("modified_files")
        if not isinstance(modified_files, list) or modified_files != [target_prompt_file]:
            raise RuntimeError(
                "Prompt optimization must modify exactly the target prompt file and nothing else."
            )

        guardrails = result.get("prompt_guardrails")
        if not isinstance(guardrails, dict):
            raise RuntimeError("Prompt optimization result must include prompt_guardrails.")

        preserved_intent = bool(guardrails.get("preserved_intent"))
        violations = guardrails.get("forbidden_change_violations")
        if not isinstance(violations, list):
            raise RuntimeError(
                "Prompt optimization result must report forbidden_change_violations as a list."
            )
        if (not preserved_intent) or violations:
            raise RuntimeError(
                f"Prompt guardrails violated for {target_prompt_file}: "
                f"preserved_intent={preserved_intent}, violations={violations}"
            )

    def _candidate_metadata(self, candidate: LLMUpgradeCandidate) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if isinstance(candidate.execution_plan.metadata, dict):
            metadata.update(candidate.execution_plan.metadata)
        if isinstance(candidate.metadata, dict):
            metadata.update(candidate.metadata)
        return metadata


def build_section_aware_prompt_optimizer_runner(
    *,
    section_mutator: Callable[[dict[str, Any]], dict[str, Optional[Any]]],
    write_back: bool = True,
) -> Callable[[LLMUpgradeCandidate], dict[str, Any]]:
    runner = SectionAwarePromptOptimizerRunner(
        section_mutator=section_mutator,
        write_back=write_back,
    )
    return runner
