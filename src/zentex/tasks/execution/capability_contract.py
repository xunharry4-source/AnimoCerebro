from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from zentex.tasks.execution.executor_profiles import ExecutorProfile


@dataclass(frozen=True)
class CapabilityExecutionContract:
    owner_ref: str
    executor_type: str
    capability: str
    execution_profile_id: str
    parameter_schema: Dict[str, Any]
    required_parameters: List[str]
    output_schema: Dict[str, Any]
    observation_sources: List[str]
    evidence_requirements: List[Dict[str, Any]]
    verification_rules: List[Dict[str, Any]]
    verification_strategy: str
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    llm_validation_policy: Dict[str, Any] | None = None
    hybrid_validation_policy: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_ref": self.owner_ref,
            "executor_type": self.executor_type,
            "capability": self.capability,
            "execution_profile_id": self.execution_profile_id,
            "parameter_schema": dict(self.parameter_schema),
            "required_parameters": list(self.required_parameters),
            "output_schema": dict(self.output_schema),
            "observation_sources": list(self.observation_sources),
            "evidence_requirements": [dict(item) for item in self.evidence_requirements],
            "verification_rules": [dict(item) for item in self.verification_rules],
            "verification_strategy": self.verification_strategy,
            "retry_policy": dict(self.retry_policy),
            "llm_validation_policy": dict(self.llm_validation_policy or {}),
            "hybrid_validation_policy": dict(self.hybrid_validation_policy or {}),
        }


def _contract_section(task_contract: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    for source in (metadata.get("react_execution_contract"), metadata.get("capability_execution_contract"), task_contract):
        if isinstance(source, dict):
            return dict(source)
    return {}


def resolve_capability_contract(
    *,
    task: Dict[str, Any],
    metadata: Dict[str, Any],
    dispatch: Dict[str, Any],
    profile: ExecutorProfile,
    owner_ref: str,
) -> CapabilityExecutionContract:
    section = _contract_section(task.get("contract"), metadata)
    parameter_schema = section.get("parameter_schema") if isinstance(section.get("parameter_schema"), dict) else {}
    output_schema = section.get("output_schema") if isinstance(section.get("output_schema"), dict) else {}
    required_parameters = section.get("required_parameters")
    if not isinstance(required_parameters, list):
        required_parameters = []
    verification_rules = section.get("verification_rules")
    if not isinstance(verification_rules, list):
        verification_rules = []
    evidence_requirements = section.get("evidence_requirements")
    if not isinstance(evidence_requirements, list):
        evidence_requirements = []
    strategy = str(section.get("verification_strategy") or profile.default_verification_strategy or "rule").strip().lower()
    if strategy not in {"rule", "llm", "hybrid"}:
        strategy = "rule"
    retry_policy = section.get("retry_policy") if isinstance(section.get("retry_policy"), dict) else {}
    retry_policy.setdefault("max_attempts", int(metadata.get("react_max_attempts") or task.get("maximum_attempts") or 1))
    retry_policy.setdefault(
        "retryable_failures",
        ["executor_timeout", "transient_connector_error", "observation_readback_not_ready"],
    )
    return CapabilityExecutionContract(
        owner_ref=owner_ref,
        executor_type=profile.executor_type,
        capability=str(dispatch.get("capability") or "").strip(),
        execution_profile_id=profile.execution_profile_id,
        parameter_schema=parameter_schema,
        required_parameters=[str(item) for item in required_parameters if str(item).strip()],
        output_schema=output_schema,
        observation_sources=list(profile.observation_sources),
        evidence_requirements=[dict(item) for item in evidence_requirements if isinstance(item, dict)],
        verification_rules=[dict(item) for item in verification_rules if isinstance(item, dict)],
        verification_strategy=strategy,
        retry_policy=retry_policy,
        llm_validation_policy=section.get("llm_validation_policy") if isinstance(section.get("llm_validation_policy"), dict) else None,
        hybrid_validation_policy=section.get("hybrid_validation_policy") if isinstance(section.get("hybrid_validation_policy"), dict) else None,
    )
