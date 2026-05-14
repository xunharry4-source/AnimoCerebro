from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ExecutorProfile:
    executor_type: str
    execution_profile_id: str
    required_dispatch_fields: List[str]
    parameter_field: str
    observation_sources: List[str]
    default_verification_strategy: str
    result_required_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executor_type": self.executor_type,
            "execution_profile_id": self.execution_profile_id,
            "required_dispatch_fields": list(self.required_dispatch_fields),
            "parameter_field": self.parameter_field,
            "observation_sources": list(self.observation_sources),
            "default_verification_strategy": self.default_verification_strategy,
            "result_required_fields": list(self.result_required_fields),
        }


EXECUTOR_PROFILES: Dict[str, ExecutorProfile] = {
    "cli": ExecutorProfile(
        executor_type="cli",
        execution_profile_id="cli_registered_tool_execution_v1",
        required_dispatch_fields=["tool_name"],
        parameter_field="arguments",
        observation_sources=["executor_result", "task_outcome", "file_readback", "audit_log"],
        default_verification_strategy="rule",
        result_required_fields=["succeeded"],
    ),
    "agent": ExecutorProfile(
        executor_type="agent",
        execution_profile_id="agent_dispatch_execution_v1",
        required_dispatch_fields=["agent_id", "task_payload"],
        parameter_field="task_payload",
        observation_sources=["executor_result", "task_outcome", "agent_artifact_readback", "audit_log"],
        default_verification_strategy="hybrid",
        result_required_fields=["succeeded"],
    ),
    "mcp": ExecutorProfile(
        executor_type="mcp",
        execution_profile_id="mcp_tool_execution_v1",
        required_dispatch_fields=["server_id", "tool_name"],
        parameter_field="arguments",
        observation_sources=["executor_result", "task_outcome", "mcp_resource_readback", "audit_log"],
        default_verification_strategy="rule",
        result_required_fields=["succeeded"],
    ),
    "external_connector": ExecutorProfile(
        executor_type="external_connector",
        execution_profile_id="external_connector_capability_execution_v1",
        required_dispatch_fields=["connector_id", "capability"],
        parameter_field="arguments",
        observation_sources=["executor_result", "task_outcome", "audit_log"],
        default_verification_strategy="rule",
        result_required_fields=["succeeded", "result"],
    ),
    "internal_plugin": ExecutorProfile(
        executor_type="internal_plugin",
        execution_profile_id="internal_plugin_service_execution_v1",
        required_dispatch_fields=["plugin_id", "capability"],
        parameter_field="arguments",
        observation_sources=["executor_result", "task_outcome", "plugin_state_readback", "audit_log"],
        default_verification_strategy="rule",
        result_required_fields=["succeeded"],
    ),
}


def resolve_executor_profile(executor_type: str) -> ExecutorProfile:
    normalized = str(executor_type or "").strip().lower()
    if normalized == "connector":
        normalized = "external_connector"
    profile = EXECUTOR_PROFILES.get(normalized)
    if profile is None:
        raise ValueError(f"Unsupported executor type for ReAct execution: {executor_type}")
    return profile


def validate_dispatch_against_profile(dispatch: Dict[str, Any], profile: ExecutorProfile) -> List[str]:
    missing: List[str] = []
    for field_name in profile.required_dispatch_fields:
        value = dispatch.get(field_name)
        if value in (None, "", [], {}):
            missing.append(field_name)
    return missing
