from __future__ import annotations

"""Business planner for DSPy-backed LLM upgrades."""

from importlib.util import find_spec
from typing import Any

from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.upgrade.base_models import SelfUpgradeProposal
from zentex.upgrade.llm.models import (
    LLMUpgradeCandidate,
    LLMUpgradeExecutionPlan,
    LLMUpgradeRequest,
)
from zentex.upgrade.llm.prompt_builders import (
    build_dspy_primitive_generation_request,
    build_optimization_needs_request,
    build_target_identification_request,
)
from zentex.upgrade.versioning import derive_candidate_version


class DSPyRuntimeGuard:
    """Validates the DSPy runtime dependency."""

    def assert_runtime_ready(self) -> None:
        if find_spec("dspy") is None:
            raise RuntimeError(
                "DSPy is not installed; configure the LLM upgrade runtime before "
                "running optimization jobs."
            )


class LLMUpgradePlanner:
    """Builds versioned LLM upgrade candidates."""

    def __init__(
        self,
        *,
        runtime_guard: DSPyRuntimeGuard | None = None,
        primitive_generator: "DSPyPrimitiveGenerator | None" = None,
    ) -> None:
        self._runtime_guard = runtime_guard or DSPyRuntimeGuard()
        self._primitive_generator = primitive_generator or DSPyPrimitiveGenerator()

    def plan_candidate(self, request: LLMUpgradeRequest) -> LLMUpgradeCandidate:
        self._runtime_guard.assert_runtime_ready()

        candidate_version = derive_candidate_version(
            request.baseline_version,
            request.change_scope,
        )
        metadata = build_prompt_upgrade_metadata(request)
        primitives = self._resolve_primitives(request)
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
            dspy_signature=primitives.get("signature"),
            dspy_metric=primitives.get("metric"),
            metadata=metadata,
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
            dspy_signature=primitives.get("signature"),
            dspy_module=primitives.get("module"),
            metadata=metadata,
        )

    def _resolve_primitives(self, request: LLMUpgradeRequest) -> dict[str, str]:
        if request.upgrade_kind == "prompt_optimization":
            return {}
        if request.dspy_signature or request.dspy_module or request.dspy_metric:
            return {
                "signature": request.dspy_signature or "",
                "module": request.dspy_module or "",
                "metric": request.dspy_metric or "",
            }
        return self._primitive_generator.generate(
            objective_summary=request.objective_summary,
            target_metric=request.target_metric,
        )

    def assert_runtime_ready(self) -> None:
        self._runtime_guard.assert_runtime_ready()

    def generate_primitives(self, *, objective_summary: str, target_metric: str) -> dict[str, str]:
        return self._primitive_generator.generate(
            objective_summary=objective_summary,
            target_metric=target_metric,
        )


def build_prompt_upgrade_metadata(request: LLMUpgradeRequest) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if request.upgrade_kind:
        metadata["upgrade_kind"] = request.upgrade_kind
    if request.prompt_file_path:
        metadata["prompt_file_path"] = request.prompt_file_path
    if request.prompt_builder_symbol:
        metadata["prompt_builder_symbol"] = request.prompt_builder_symbol
    if request.immutable_intent:
        metadata["immutable_intent"] = request.immutable_intent
    if request.forbidden_prompt_changes:
        metadata["forbidden_prompt_changes"] = list(request.forbidden_prompt_changes)
    if request.allowed_prompt_change_scope:
        metadata["allowed_prompt_change_scope"] = list(request.allowed_prompt_change_scope)
    if request.prompt_contract:
        metadata["prompt_contract"] = dict(request.prompt_contract)
    return metadata


class DSPyPrimitiveGenerator:
    """Generates DSPy Signature/Module/Metric code through the live LLM gateway."""

    def generate(self, *, objective_summary: str, target_metric: str) -> dict[str, str]:
        from zentex.llm.gateway import LLMGateway

        gateway = LLMGateway()
        caller_context = ModelProviderCallerContext(
            source_module="llm_upgrade_service",
            invocation_phase="primitive_generation",
            decision_id=f"dspy-gen-{objective_summary[:8]}",
        )
        request = build_dspy_primitive_generation_request(
            objective_summary=objective_summary,
            target_metric=target_metric,
        )
        try:
            response = gateway.invoke_generate_json(
                prompt=request["prompt"],
                context={"target_metric": target_metric},
                caller_context=caller_context,
                system_prompt=str(request["system_prompt"]),
            )
            return response.output
        except Exception as exc:
            raise RuntimeError(
                f"[LLM MANDATORY] Failed to generate DSPy primitives: {exc}"
            ) from exc


class OptimizationNeedsDetector:
    """Detects LLM optimization opportunities through live LLM reasoning."""

    def detect(self, failure_logs: list[dict[str, Any]]) -> list[SelfUpgradeProposal]:
        from zentex.llm.gateway import LLMGateway

        if not failure_logs:
            return []

        gateway = LLMGateway()
        caller_context = ModelProviderCallerContext(
            source_module="llm_upgrade_service",
            invocation_phase="needs_detection",
            decision_id="llm-needs-analysis",
        )
        request = build_optimization_needs_request(failure_logs)
        try:
            response = gateway.invoke_generate_json(
                prompt=str(request["prompt"]),
                context=dict(request["model_context"]),
                caller_context=caller_context,
                system_prompt=str(request["system_prompt"]),
            )
            output = response.output
            if not isinstance(output, dict):
                raise RuntimeError("LLM needs detector returned non-object JSON.")
            return []
        except Exception as exc:
            raise RuntimeError(
                f"[LLM MANDATORY] Optimization needs detection failed: {exc}"
            ) from exc


class LLMEvolutionTargetPlanner:
    """Prioritizes LLM upgrade targets through live LLM reasoning."""

    def identify_optimal_targets(self, failure_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from zentex.llm.gateway import LLMGateway

        if not failure_history:
            return []

        gateway = LLMGateway()
        caller_context = ModelProviderCallerContext(
            source_module="evolution_planner",
            invocation_phase="target_identification",
            decision_id="evolution-targets",
        )
        request = build_target_identification_request(failure_history)
        try:
            response = gateway.invoke_generate_json(
                prompt=str(request["prompt"]),
                context=dict(request["model_context"]),
                caller_context=caller_context,
            )
            return response.output.get("findings", [])
        except Exception as exc:
            raise RuntimeError(f"[LLM MANDATORY] Target identification failed: {exc}") from exc
