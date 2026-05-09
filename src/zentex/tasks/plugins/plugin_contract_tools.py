from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union


_TASK_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _task_get_path(payload: Any, field: str) -> Any:
    current = payload
    for part in str(field or "").split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def task_plugin_normalize_result(
    result: Any,
    *,
    source_kind: str = "generic",
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"output": result}
    return {
        "normalized": True,
        "status": str(payload.get("status") or "done"),
        "source_kind": source_kind,
        "output": payload.get("output") if "output" in payload else payload,
        "structured_output": payload.get("structured_output") or payload.get("output"),
        "artifacts": list(payload.get("artifacts") or []),
        "warnings": list(payload.get("warnings") or []),
        "stdout": payload.get("stdout"),
        "stderr": payload.get("stderr"),
        "metrics": dict(payload.get("metrics") or {}),
        "execution_metadata": dict(payload.get("execution_metadata") or {}),
        "metadata": dict(metadata or {}),
        "error": payload.get("error"),
    }


def task_plugin_extract_evidence(
    result: Any,
    *,
    source_kind: str = "generic",
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"summary": str(result)}
    summary = str(payload.get("summary") or payload.get("output") or "").strip()
    warnings = list(payload.get("warnings") or [])
    artifacts = list(payload.get("artifacts") or [])
    evidence: List[Dict[str, Any]] = []
    signals: List[str] = []

    if summary:
        evidence.append(
            {
                "evidence_type": "summary",
                "content": summary,
                "source": source_kind,
                "confidence": 0.9,
                "related_field": "summary",
            }
        )
    if warnings:
        signals.append("warnings_present")
        for warning in warnings:
            evidence.append(
                {
                    "evidence_type": "warning",
                    "content": str(warning),
                    "source": source_kind,
                    "confidence": 0.8,
                    "related_field": "warnings",
                }
            )
    if artifacts:
        signals.append("artifacts_present")
        for artifact in artifacts:
            evidence.append(
                {
                    "evidence_type": "artifact",
                    "content": str(artifact.get("path") if isinstance(artifact, dict) else artifact),
                    "source": source_kind,
                    "confidence": 0.95,
                    "related_field": "artifacts",
                }
            )
    if payload.get("stderr"):
        signals.append("stderr_present")
        evidence.append(
            {
                "evidence_type": "stderr",
                "content": str(payload.get("stderr")),
                "source": source_kind,
                "confidence": 0.85,
                "related_field": "stderr",
            }
        )
    if payload.get("error"):
        signals.append("error_present")
        evidence.append(
            {
                "evidence_type": "error",
                "content": str(payload.get("error")),
                "source": source_kind,
                "confidence": 0.95,
                "related_field": "error",
            }
        )

    return {
        "summary": summary,
        "signals": signals,
        "evidence": evidence,
        "evidence_items": {
            "artifact_count": len(artifacts),
            "warning_count": len(warnings),
            "evidence_count": len(evidence),
        },
        "failure_symptoms": [signal for signal in signals if signal in {"error_present", "stderr_present"}],
    }


def task_plugin_rule_based_verification(
    result: Any,
    *,
    rules: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"value": result}
    failures: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    for rule in list(rules or []):
        rule_type = str(rule.get("type") or "").strip()
        field = str(rule.get("field") or "").strip()
        actual = _task_get_path(payload, field) if field else payload
        passed = True
        if rule_type == "required_field":
            passed = actual is not None
        elif rule_type == "equals":
            passed = actual == rule.get("expected")
        elif rule_type == "min_length":
            passed = len(str(actual or "")) >= int(rule.get("min_length") or 0)
        elif rule_type == "regex":
            import re

            passed = re.search(str(rule.get("pattern") or ""), str(actual or "")) is not None
        else:
            passed = False

        evidence.append({"rule_type": rule_type, "field": field, "passed": passed, "actual": actual})
        if not passed:
            failures.append({"rule_type": rule_type, "field": field, "actual": actual})

    failure_type = "incorrect_output"
    if any(item["rule_type"] == "required_field" for item in failures):
        failure_type = "missing_requirement"
    elif any(item["rule_type"] == "min_length" for item in failures):
        failure_type = "partial_output"

    passed = not failures
    failure_count = len(failures)
    confidence_score = 1.0 if not rules else max(0.0, 1.0 - (failure_count / max(len(rules), 1)))
    return {
        "passed": passed,
        "overall_status": "passed" if passed else "failed",
        "failure_count": failure_count,
        "confidence_score": round(confidence_score, 3),
        "retryable": False,
        "recommendation": "accept" if passed else "review_failed_rules",
        "output_quality_score": round(confidence_score, 3),
        "completeness_score": 1.0 if passed else max(0.0, 1.0 - failure_count / max(len(rules or []), 1)),
        "evidence": evidence,
        "failure_classification": {
            "failure_type": failure_type if failures else None,
            "severity": "medium" if failures else "none",
            "failures": failures,
        },
    }


def task_plugin_match_capabilities(
    *,
    required_capabilities: List[str],
    candidate_capabilities: List[str],
    preferred_capabilities: List[Optional[str]] = None,
    forbidden_capabilities: List[Optional[str]] = None,
    capability_aliases: Dict[str, List[Optional[str]]] = None,
) -> Dict[str, Any]:
    candidate = set(candidate_capabilities or [])
    aliases = capability_aliases or {}

    def _matches(capability: str) -> bool:
        if capability in candidate:
            return True
        return any(alias in candidate for alias in aliases.get(capability, []))

    required = list(required_capabilities or [])
    preferred = list(preferred_capabilities or [])
    forbidden = list(forbidden_capabilities or [])
    matched_required = [cap for cap in required if _matches(cap)]
    matched_preferred = [cap for cap in preferred if _matches(cap)]
    missing_required = [cap for cap in required if cap not in matched_required]
    conflicting = [cap for cap in forbidden if _matches(cap)]
    has_required = not missing_required and not conflicting
    score = len(matched_required) / len(required) if required else 1.0
    confidence = 1.0 if has_required else max(0.0, score - 0.2)
    return {
        "has_required_capabilities": has_required,
        "capability_match_score": round(score, 3),
        "matched_required": matched_required,
        "matched_preferred": matched_preferred,
        "missing_required": missing_required,
        "conflicting_capabilities": conflicting,
        "match_confidence": round(confidence, 3),
        "routing_evidence": {
            "required_count": len(required),
            "candidate_count": len(candidate),
            "preferred_count": len(preferred),
        },
    }


def task_plugin_check_constraints(
    *,
    constraints: Dict[str, Any],
    runtime_context: Dict[str, Any],
) -> Dict[str, Any]:
    hard_blockers: List[str] = []
    soft_warnings: List[str] = []
    missing_prerequisites: List[str] = []
    policy_violations: List[str] = []

    max_allowed_risk = str(constraints.get("max_allowed_risk") or "critical").lower()
    current_risk = str(runtime_context.get("risk_level") or "low").lower()
    if _TASK_RISK_ORDER.get(current_risk, 0) > _TASK_RISK_ORDER.get(max_allowed_risk, 0):
        hard_blockers.append(f"risk level {current_risk} exceeds allowed {max_allowed_risk}")

    if constraints.get("requires_heartbeat") and not runtime_context.get("supports_heartbeat"):
        hard_blockers.append("heartbeat required but unavailable")
    if constraints.get("requires_network") and not runtime_context.get("network_available"):
        hard_blockers.append("network required but unavailable")
    if constraints.get("requires_approval") and not runtime_context.get("approval_granted"):
        policy_violations.append("approval required but not granted")

    required_artifact_types = set(constraints.get("required_artifact_types") or [])
    available_artifact_types = set(runtime_context.get("available_artifact_types") or [])
    missing_types = sorted(required_artifact_types - available_artifact_types)
    if missing_types:
        missing_prerequisites.append(f"missing required artifact types: {', '.join(missing_types)}")

    timeout_budget = constraints.get("timeout_budget_seconds")
    estimated_duration = runtime_context.get("estimated_duration_seconds")
    if timeout_budget is not None and estimated_duration is not None and float(estimated_duration) > float(timeout_budget):
        hard_blockers.append("estimated duration exceeds timeout budget")

    max_retry_budget = constraints.get("max_retry_budget")
    requested_retry_budget = runtime_context.get("requested_retry_budget")
    if max_retry_budget is not None and requested_retry_budget is not None and int(requested_retry_budget) > int(max_retry_budget):
        policy_violations.append("requested retry budget exceeds allowed maximum")

    violations = [*hard_blockers, *policy_violations, *missing_prerequisites]
    return {
        "allowed": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "hard_blockers": hard_blockers,
        "soft_warnings": soft_warnings,
        "missing_prerequisites": missing_prerequisites,
        "policy_violations": policy_violations,
        "budget_assessment": {
            "timeout_budget_seconds": timeout_budget,
            "estimated_duration_seconds": estimated_duration,
            "max_retry_budget": max_retry_budget,
            "requested_retry_budget": requested_retry_budget,
        },
    }


def task_plugin_plan_compensation(
    *,
    workspace: str,
    artifacts: List[Union[Dict[str, Any], Any]],
    failure_type: str,
) -> Dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    cleanup_targets: List[Dict[str, Any]] = []
    for artifact in list(artifacts or []):
        raw_path = artifact.get("path") if isinstance(artifact, dict) else artifact
        if not raw_path:
            continue
        candidate = (workspace_path / str(raw_path)).resolve()
        cleanup_targets.append(
            {
                "path": str(candidate),
                "exists": candidate.exists(),
                "within_workspace": workspace_path == candidate or workspace_path in candidate.parents,
            }
        )

    return {
        "planned": True,
        "compensation_type": "cleanup_and_handoff",
        "cleanup_target_count": len(cleanup_targets),
        "cleanup_targets": cleanup_targets,
        "planned_actions": [
            "collect_failure_evidence",
            "cleanup_generated_artifacts",
            "prepare_handoff_summary",
        ],
        "affected_resources": [item["path"] for item in cleanup_targets],
        "safe_to_auto_execute": all(item["within_workspace"] for item in cleanup_targets),
        "requires_human_confirmation": failure_type in {"incorrect_output", "security_violation"},
    }


__all__ = [
    "task_plugin_normalize_result",
    "task_plugin_extract_evidence",
    "task_plugin_rule_based_verification",
    "task_plugin_match_capabilities",
    "task_plugin_check_constraints",
    "task_plugin_plan_compensation",
]
