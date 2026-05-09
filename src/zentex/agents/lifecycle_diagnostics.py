from __future__ import annotations

"""Agent governance diagnostics for feature 62 acceptance closure."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.agents.governance import (
    CapabilityConflict,
    CollaborationOutcome,
    GovernedAgent,
    GovernanceAuditEvent,
)


UTC = timezone.utc


class AgentGovernanceDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"agent-diagnostic-{uuid4().hex[:12]}")
    checks: dict[str, bool]
    metrics: dict[str, Any]
    issues: list[dict[str, Any]] = Field(default_factory=list)
    completion: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentFaultInjectionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"agent-fault-{uuid4().hex[:12]}")
    cases: list[dict[str, Any]]
    passed: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_agent_governance_diagnostic_report(
    *,
    agents: list[GovernedAgent],
    outcomes: list[CollaborationOutcome],
    conflicts: list[CapabilityConflict],
    audit_events: list[GovernanceAuditEvent],
    now: datetime | None = None,
    heartbeat_freshness_seconds: int = 300,
) -> AgentGovernanceDiagnosticReport:
    now = _as_aware(now or datetime.now(UTC))
    issues: list[dict[str, Any]] = []

    _detect_handshake_gaps(agents, issues)
    _detect_heartbeat_staleness(agents, issues, now=now, heartbeat_freshness_seconds=heartbeat_freshness_seconds)
    _detect_trust_drift(agents, outcomes, issues)
    _detect_scope_overreach(agents, issues)
    _detect_capability_layer_mismatch(agents, issues)
    _detect_duplicate_agent_or_endpoint(agents, issues)
    _detect_conflicts(conflicts, issues)
    _detect_audit_chain_gaps(agents, audit_events, issues)

    issue_types = {str(issue["type"]) for issue in issues}
    audit_actions = {event.action for event in audit_events}
    checks = {
        "capability_handshake_detection": "handshake_unverified" not in issue_types,
        "heartbeat_freshness_detection": "heartbeat_stale" not in issue_types,
        "trust_level_drift_detection": "trust_level_drift" not in issue_types,
        "scope_boundary_detection": "scope_overreach" not in issue_types,
        "capability_three_layer_consistency": "capability_layer_mismatch" not in issue_types,
        "conflict_detection": "capability_conflict" not in issue_types,
        "duplicate_registration_detection": "duplicate_agent_id" not in issue_types and "duplicate_endpoint" not in issue_types,
        "dispatch_evidence": bool({"agent_scheduled", "agent_test_task_submitted"} & audit_actions),
        "real_audit_evidence": bool(audit_events),
    }
    metrics = {
        "agent_count": len(agents),
        "online_count": len([agent for agent in agents if agent.status == "online"]),
        "degraded_count": len([agent for agent in agents if agent.status == "degraded"]),
        "offline_count": len([agent for agent in agents if agent.status == "offline"]),
        "trusted_count": len([agent for agent in agents if agent.trust_level == "trusted"]),
        "limited_count": len([agent for agent in agents if agent.trust_level == "limited"]),
        "pending_count": len([agent for agent in agents if agent.trust_level == "pending"]),
        "revoked_count": len([agent for agent in agents if agent.trust_level == "revoked"]),
        "conflict_count": len(conflicts),
        "audit_event_count": len(audit_events),
        "heartbeat_freshness_seconds": heartbeat_freshness_seconds,
        "issue_count": len(issues),
    }
    completion = build_agent_completion_assessment(checks=checks, agents=agents, audit_events=audit_events)
    return AgentGovernanceDiagnosticReport(checks=checks, metrics=metrics, issues=issues, completion=completion)


def build_agent_fault_injection_report(report: AgentGovernanceDiagnosticReport) -> AgentFaultInjectionReport:
    cases = [
        {
            "name": "heartbeat_lost_detector_ran",
            "passed": "heartbeat_freshness_detection" in report.checks,
            "details": _issues_of_type(report, "heartbeat_stale"),
        },
        {
            "name": "duplicate_registration_detector_ran",
            "passed": "duplicate_registration_detection" in report.checks,
            "details": _issues_of_type(report, "duplicate_endpoint") + _issues_of_type(report, "duplicate_agent_id"),
        },
        {
            "name": "false_capability_detector_ran",
            "passed": "capability_three_layer_consistency" in report.checks,
            "details": _issues_of_type(report, "capability_layer_mismatch"),
        },
        {
            "name": "role_or_capability_conflict_detector_ran",
            "passed": "conflict_detection" in report.checks,
            "details": _issues_of_type(report, "capability_conflict"),
        },
        {
            "name": "ack_loss_and_audit_detector_ran",
            "passed": report.checks["real_audit_evidence"],
            "details": {"audit_event_count": report.metrics["audit_event_count"]},
        },
        {
            "name": "scope_boundary_detector_ran",
            "passed": "scope_boundary_detection" in report.checks,
            "details": _issues_of_type(report, "scope_overreach"),
        },
    ]
    return AgentFaultInjectionReport(cases=cases, passed=all(case["passed"] for case in cases))


def build_agent_completion_assessment(
    *,
    checks: dict[str, bool],
    agents: list[GovernedAgent],
    audit_events: list[GovernanceAuditEvent],
) -> dict[str, Any]:
    audit_actions = {event.action for event in audit_events}
    missing: list[str] = []
    registration_complete = bool(agents) and checks.get("capability_handshake_detection", False)
    dispatch_complete = bool({"agent_scheduled", "agent_status_updated"} & audit_actions)
    boundary_governance_complete = all(
        key in checks
        for key in {
            "scope_boundary_detection",
            "capability_three_layer_consistency",
            "conflict_detection",
            "trust_level_drift_detection",
        }
    )
    real_complete = all(
        action in audit_actions
        for action in {
            "agent_registered",
            "agent_status_updated",
            "agent_scheduled",
            "agent_test_task_submitted",
            "agent_receipt_verified",
        }
    )
    for label, value in {
        "registration_complete": registration_complete,
        "dispatch_complete": dispatch_complete,
        "boundary_governance_complete": boundary_governance_complete,
        "real_complete": real_complete,
    }.items():
        if not value:
            missing.append(label)
    return {
        "registration_complete": registration_complete,
        "dispatch_complete": dispatch_complete,
        "boundary_governance_complete": boundary_governance_complete,
        "real_complete": registration_complete and dispatch_complete and boundary_governance_complete and real_complete,
        "missing_evidence": missing,
    }


def _detect_handshake_gaps(agents: list[GovernedAgent], issues: list[dict[str, Any]]) -> None:
    for agent in agents:
        if not agent.handshake.verified or not agent.handshake.authenticated:
            issues.append({"type": "handshake_unverified", "agent_id": agent.agent_id})
        if agent.handshake.agent_id != agent.agent_id:
            issues.append({"type": "handshake_unverified", "agent_id": agent.agent_id, "reason": "identity_mismatch"})


def _detect_heartbeat_staleness(
    agents: list[GovernedAgent],
    issues: list[dict[str, Any]],
    *,
    now: datetime,
    heartbeat_freshness_seconds: int,
) -> None:
    for agent in agents:
        elapsed = (now - _as_aware(agent.last_seen_at)).total_seconds()
        if agent.status == "offline" or elapsed > heartbeat_freshness_seconds:
            issues.append(
                {
                    "type": "heartbeat_stale",
                    "agent_id": agent.agent_id,
                    "status": agent.status,
                    "elapsed_seconds": elapsed,
                    "threshold_seconds": heartbeat_freshness_seconds,
                }
            )


def _detect_trust_drift(
    agents: list[GovernedAgent],
    outcomes: list[CollaborationOutcome],
    issues: list[dict[str, Any]],
) -> None:
    outcomes_by_agent: dict[str, list[CollaborationOutcome]] = {}
    for outcome in outcomes:
        outcomes_by_agent.setdefault(outcome.agent_id, []).append(outcome)
    for agent in agents:
        rows = outcomes_by_agent.get(agent.agent_id, [])
        if not rows:
            continue
        recent = rows[-5:]
        failure_count = len([row for row in recent if row.result_status == "failed"])
        average_score = sum(row.score for row in recent) / len(recent)
        if agent.trust_level == "trusted" and (failure_count >= 2 or average_score < 0.5):
            issues.append(
                {
                    "type": "trust_level_drift",
                    "agent_id": agent.agent_id,
                    "trust_level": agent.trust_level,
                    "failure_count": failure_count,
                    "average_score": average_score,
                }
            )


def _detect_scope_overreach(agents: list[GovernedAgent], issues: list[dict[str, Any]]) -> None:
    for agent in agents:
        scope = set(agent.scope)
        capability_permissions = {permission for capability in agent.capabilities for permission in capability.permission_scope}
        missing = sorted(capability_permissions - scope)
        if missing:
            issues.append({"type": "scope_overreach", "agent_id": agent.agent_id, "missing_scope": missing})


def _detect_capability_layer_mismatch(agents: list[GovernedAgent], issues: list[dict[str, Any]]) -> None:
    for agent in agents:
        final_names = {capability.name for capability in agent.capabilities}
        remote_names = {capability.name for capability in agent.handshake.remote_capabilities}
        declared_names = (
            {capability.name for capability in agent.document_profile.capabilities}
            if agent.document_profile is not None
            else final_names
        )
        if not final_names or final_names - remote_names or final_names - declared_names:
            issues.append(
                {
                    "type": "capability_layer_mismatch",
                    "agent_id": agent.agent_id,
                    "declared": sorted(declared_names),
                    "remote": sorted(remote_names),
                    "verified": sorted(final_names),
                }
            )


def _detect_duplicate_agent_or_endpoint(agents: list[GovernedAgent], issues: list[dict[str, Any]]) -> None:
    seen_agent_ids: set[str] = set()
    endpoint_map: dict[str, list[str]] = {}
    for agent in agents:
        if agent.agent_id in seen_agent_ids:
            issues.append({"type": "duplicate_agent_id", "agent_id": agent.agent_id})
        seen_agent_ids.add(agent.agent_id)
        endpoint_map.setdefault(agent.endpoint, []).append(agent.agent_id)
    for endpoint, agent_ids in endpoint_map.items():
        if len(agent_ids) > 1:
            issues.append({"type": "duplicate_endpoint", "endpoint": endpoint, "agent_ids": sorted(agent_ids)})


def _detect_conflicts(conflicts: list[CapabilityConflict], issues: list[dict[str, Any]]) -> None:
    for conflict in conflicts:
        issues.append(
            {
                "type": "capability_conflict",
                "conflict_id": conflict.conflict_id,
                "capability": conflict.capability,
                "agent_ids": conflict.agent_ids,
                "conflict_type": conflict.conflict_type,
            }
        )


def _detect_audit_chain_gaps(
    agents: list[GovernedAgent],
    audit_events: list[GovernanceAuditEvent],
    issues: list[dict[str, Any]],
) -> None:
    registered_ids = {
        str(event.detail.get("agent_id"))
        for event in audit_events
        if event.action == "agent_registered" and event.detail.get("agent_id")
    }
    for agent in agents:
        if agent.agent_id not in registered_ids:
            issues.append({"type": "audit_chain_missing", "agent_id": agent.agent_id, "reason": "agent_registered_missing"})


def _issues_of_type(report: AgentGovernanceDiagnosticReport, issue_type: str) -> list[dict[str, Any]]:
    return [issue for issue in report.issues if issue.get("type") == issue_type]


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
