from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ArchitectureRedlineCategory(str, Enum):
    LLM_BOUNDARY = "llm_boundary"
    PLUGIN_BOUNDARY = "plugin_boundary"
    ARCHITECTURE_BOUNDARY = "architecture_boundary"
    TESTING_INTEGRITY = "testing_integrity"


class ArchitectureRedlineRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    category: ArchitectureRedlineCategory
    title: str
    severity: str
    statement: str
    enforcement: str
    evidence_required: list[str] = Field(default_factory=list)


class ArchitectureRedlineValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_type: str = Field(min_length=1)
    claims: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ArchitectureRedlineViolation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    category: ArchitectureRedlineCategory
    severity: str
    message: str
    evidence_required: list[str] = Field(default_factory=list)


class ArchitectureRedlineValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str
    trace_id: str
    operation_type: str
    allowed: bool
    decision: str
    checked_rule_ids: list[str]
    violations: list[ArchitectureRedlineViolation] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evaluated_at: str


LLM_MANDATORY_OPERATIONS = {
    "role_inference",
    "goal_generation",
    "think_loop_critical_decision",
}

LLM_NOT_REQUIRED_OPERATIONS = {
    "question_body_assembly",
    "reflection_protocol_assembly",
    "safety_gate",
    "memory_retrieval",
    "cloud_audit_policy",
    "cognitive_temporal_math",
}


ARCHITECTURE_REDLINE_RULES: tuple[ArchitectureRedlineRule, ...] = (
    ArchitectureRedlineRule(
        rule_id="llm-live-required",
        category=ArchitectureRedlineCategory.LLM_BOUNDARY,
        title="Live LLM required for cognitive decisions",
        severity="critical",
        statement="Role inference, goal generation, and ThinkLoop critical decisions must use live LLM output.",
        enforcement="fail_closed",
        evidence_required=["provider_name", "model", "raw_response", "trace_id"],
    ),
    ArchitectureRedlineRule(
        rule_id="llm-no-rule-disguise",
        category=ArchitectureRedlineCategory.LLM_BOUNDARY,
        title="Rules must not masquerade as AI decisions",
        severity="critical",
        statement="Rule-generated results cannot be wrapped and returned as AI decision products.",
        enforcement="reject",
        evidence_required=["llm_trace_payload", "question_driver_refs"],
    ),
    ArchitectureRedlineRule(
        rule_id="plugin-defense-triad",
        category=ArchitectureRedlineCategory.PLUGIN_BOUNDARY,
        title="Plugins require rollback, degrade, and audit",
        severity="critical",
        statement="Every plugin must carry rollback, degraded isolation, and audit evidence.",
        enforcement="reject_plugin",
        evidence_required=["rollback_conditions", "degrade_path", "audit_event"],
    ),
    ArchitectureRedlineRule(
        rule_id="cognitive-tool-readonly",
        category=ArchitectureRedlineCategory.PLUGIN_BOUNDARY,
        title="Cognitive tools are read-only and side-effect-free",
        severity="critical",
        statement="Cognitive tools must be read_only=True and side_effect_free=True.",
        enforcement="reject_tool",
        evidence_required=["read_only", "side_effect_free", "mapped_domain"],
    ),
    ArchitectureRedlineRule(
        rule_id="execution-tool-domain-separation",
        category=ArchitectureRedlineCategory.PLUGIN_BOUNDARY,
        title="Execution tools cannot enter cognitive domain",
        severity="critical",
        statement="Mutating execution tools must not be mounted as cognitive tools.",
        enforcement="reject_tool",
        evidence_required=["mapped_domain", "mutates_state", "requires_cloud_audit"],
    ),
    ArchitectureRedlineRule(
        rule_id="zentex-brain-not-executor",
        category=ArchitectureRedlineCategory.ARCHITECTURE_BOUNDARY,
        title="Zentex remains brain layer",
        severity="critical",
        statement="Zentex must not seize host final response or execution authority.",
        enforcement="reject_integration",
        evidence_required=["host_independent", "final_authority_owner"],
    ),
    ArchitectureRedlineRule(
        rule_id="host-independent",
        category=ArchitectureRedlineCategory.ARCHITECTURE_BOUNDARY,
        title="Host remains independently runnable",
        severity="high",
        statement="The host must still run independently when Zentex is not attached.",
        enforcement="reject_integration",
        evidence_required=["host_independent"],
    ),
    ArchitectureRedlineRule(
        rule_id="real-test-evidence",
        category=ArchitectureRedlineCategory.TESTING_INTEGRITY,
        title="REAL completion requires real evidence",
        severity="critical",
        statement="Happy-path-only or render-only validation is not enough for REAL completion.",
        enforcement="reject_completion",
        evidence_required=[
            "failure_path",
            "timeout_path",
            "disconnect_path",
            "degradation_path",
            "real_external_call",
            "real_side_effect_verification",
            "real_audit_chain",
        ],
    ),
)


def architecture_redline_matrix() -> dict[str, Any]:
    rules = [rule.model_dump(mode="json") for rule in ARCHITECTURE_REDLINE_RULES]
    by_category: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        by_category.setdefault(str(rule["category"]), []).append(rule)
    return {
        "status": "ready",
        "llm_mandatory_operations": sorted(LLM_MANDATORY_OPERATIONS),
        "llm_not_required_operations": sorted(LLM_NOT_REQUIRED_OPERATIONS),
        "rules": rules,
        "by_category": by_category,
        "rule_count": len(rules),
    }


def evaluate_architecture_redlines(
    request: ArchitectureRedlineValidationRequest,
) -> ArchitectureRedlineValidationReport:
    claims = dict(request.claims or {})
    trace_id = str(request.trace_id or claims.get("trace_id") or f"architecture-redline:{uuid4().hex}")
    violations: list[ArchitectureRedlineViolation] = []
    checked: list[str] = []

    def add(rule_id: str, message: str) -> None:
        rule = _rule(rule_id)
        checked.append(rule.rule_id)
        violations.append(
            ArchitectureRedlineViolation(
                rule_id=rule.rule_id,
                category=rule.category,
                severity=rule.severity,
                message=message,
                evidence_required=rule.evidence_required,
            )
        )

    operation_type = request.operation_type.strip()
    if operation_type in LLM_MANDATORY_OPERATIONS:
        checked.append("llm-live-required")
        if claims.get("used_live_llm") is not True:
            add("llm-live-required", f"{operation_type} requires live LLM evidence.")
        if claims.get("llm_provider_configured") is False or claims.get("provider_error") is True:
            add("llm-live-required", "Provider failure must be surfaced; rule fallback is forbidden.")
        if claims.get("used_rule_fallback") is True:
            add("llm-no-rule-disguise", "Rule fallback cannot replace live LLM for mandatory operations.")

    if claims.get("wrapped_rule_as_ai") is True:
        add("llm-no-rule-disguise", "Rule-generated output was wrapped as an AI decision product.")

    if operation_type in {"plugin_runtime", "cognitive_tool", "execution_tool"}:
        checked.append("plugin-defense-triad")
        if not (claims.get("has_rollback") and claims.get("has_degrade") and claims.get("has_audit")):
            add("plugin-defense-triad", "Plugin boundary lacks rollback/degrade/audit triad.")

    if operation_type == "cognitive_tool" or claims.get("mapped_domain") == "cognitive":
        checked.append("cognitive-tool-readonly")
        if claims.get("read_only") is not True or claims.get("side_effect_free") is not True:
            add("cognitive-tool-readonly", "Cognitive tools must be read-only and side-effect-free.")
        if claims.get("mutates_state") is True:
            add("execution-tool-domain-separation", "Mutating tool cannot be mounted in cognitive domain.")

    if operation_type == "host_integration":
        checked.extend(["zentex-brain-not-executor", "host-independent"])
        if claims.get("takes_final_execution_authority") is True or claims.get("takes_final_reply_authority") is True:
            add("zentex-brain-not-executor", "Zentex cannot seize host final reply or execution authority.")
        if claims.get("host_independent") is not True:
            add("host-independent", "Host must remain independently runnable without Zentex attached.")

    if operation_type == "test_evidence" or claims.get("completion_type") == "REAL":
        checked.append("real-test-evidence")
        if claims.get("happy_path_only") is True or claims.get("renders_without_crashing_only") is True:
            add("real-test-evidence", "Happy-path-only or render-only evidence is not accepted.")
        required = (
            "has_failure_path",
            "has_timeout_path",
            "has_disconnect_path",
            "has_degradation_path",
            "real_external_call",
            "real_side_effect_verification",
            "real_audit_chain",
        )
        missing = [key for key in required if claims.get(key) is not True]
        if missing:
            add("real-test-evidence", f"REAL completion evidence is missing: {', '.join(missing)}.")

    checked_ids = sorted(dict.fromkeys(checked or [rule.rule_id for rule in ARCHITECTURE_REDLINE_RULES]))
    return ArchitectureRedlineValidationReport(
        validation_id=f"redline-validation:{uuid4().hex}",
        trace_id=trace_id,
        operation_type=operation_type,
        allowed=not violations,
        decision="allow" if not violations else "block",
        checked_rule_ids=checked_ids,
        violations=violations,
        evidence_refs=list(request.evidence_refs),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )


def _rule(rule_id: str) -> ArchitectureRedlineRule:
    for rule in ARCHITECTURE_REDLINE_RULES:
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(rule_id)


def report_to_audit_payload(report: ArchitectureRedlineValidationReport) -> dict[str, Any]:
    return {
        "event_type": "architecture_redline_validation",
        "validation_id": report.validation_id,
        "trace_id": report.trace_id,
        "operation_type": report.operation_type,
        "allowed": report.allowed,
        "decision": report.decision,
        "violation_rule_ids": [item.rule_id for item in report.violations],
        "violation_messages": [item.message for item in report.violations],
        "evidence_refs": report.evidence_refs,
        "evaluated_at": report.evaluated_at,
    }

