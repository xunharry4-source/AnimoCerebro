from __future__ import annotations

"""
DSPy-backed LLM upgrade planner.

This service is the core entrypoint for LLM optimization upgrades. It does not
pretend to optimize models when DSPy is missing; instead it validates the
request, checks runtime readiness, and returns a candidate plan that can later
be executed by a real optimization worker.
"""

from importlib.util import find_spec

from zentex.upgrade.llm.models import (
    LLMUpgradeCandidate,
    LLMUpgradeExecutionPlan,
    LLMUpgradeRequest,
)
from zentex.upgrade.versioning import derive_candidate_version


class DSPyLLMUpgradeService:
    """Fail-closed planner for DSPy-driven LLM optimization candidates."""

    def assert_runtime_ready(self) -> None:
        if find_spec("dspy") is None:
            raise RuntimeError(
                "DSPy is not installed; configure the LLM upgrade runtime before "
                "running optimization jobs."
            )

    def plan_candidate(self, request: LLMUpgradeRequest) -> LLMUpgradeCandidate:
        self.assert_runtime_ready()

        candidate_version = derive_candidate_version(
            request.baseline_version,
            request.change_scope,
        )
        execution_plan = LLMUpgradeExecutionPlan(
            optimizer_name=request.optimizer_name,
            target_metric=request.target_metric,
            dataset_refs=request.dataset_refs,
            validation_commands=request.validation_commands,
            required_artifacts=[
                "optimizer_report.json",
                "evaluation_summary.json",
                "candidate_prompt_bundle.json",
            ],
        )
        return LLMUpgradeCandidate(
            program_id=request.program_id,
            target_component=request.target_component,
            baseline_version=request.baseline_version,
            candidate_version=candidate_version,
            objective_summary=request.objective_summary,
            execution_plan=execution_plan,
            release_gate=[
                "Optimization metrics must beat or match the active baseline.",
                "Validation commands must pass before candidate promotion.",
                "Candidate artifacts must be persisted for audit and rollback.",
            ],
        )
