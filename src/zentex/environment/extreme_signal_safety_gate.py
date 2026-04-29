from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zentex.environment.extreme_signal_interceptor import ExtremeSignalInterceptor
from zentex.environment.preference_models import ConfirmationRequest, ExtremeSignalRecord
from zentex.safety.safety_gate import (
    RiskLevel as SafetyRiskLevel,
    SafetyDecisionStatus,
    SafetyGate,
    SafetyGateDecision,
)


@dataclass(frozen=True)
class ExtremeSignalSafetyGateReport:
    audit_status: str
    signal_record: ExtremeSignalRecord
    confirmation_request: ConfirmationRequest | None
    safety_decision: SafetyGateDecision
    gate_audit_count: int
    linkage_evidence: dict[str, Any]


class ExtremeSignalSafetyGateError(RuntimeError):
    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


async def evaluate_extreme_signal_through_safety_gate(
    *,
    signal_content: str,
    signal_source: str,
    action_type: str,
    action_payload: dict[str, Any],
    context: dict[str, Any] | None = None,
    interceptor: ExtremeSignalInterceptor | None = None,
    safety_gate: SafetyGate | None = None,
) -> ExtremeSignalSafetyGateReport:
    if not action_payload:
        raise ExtremeSignalSafetyGateError(
            "SafetyGate linkage requires concrete execution parameters.",
            ["missing_action_payload"],
        )

    interceptor = interceptor or ExtremeSignalInterceptor()
    safety_gate = safety_gate or SafetyGate()
    context = dict(context or {})

    risk_assessment = await interceptor.assess_signal_risk(
        signal_content=signal_content,
        signal_source=signal_source,
        context=context,
    )
    signal_record = interceptor.create_extreme_signal_record(
        signal_content=signal_content,
        signal_source=signal_source,
        risk_assessment=risk_assessment,
        metadata={
            "linked_action_type": action_type,
            "linked_context_keys": sorted(context.keys()),
        },
    )
    confirmation_request = None
    if risk_assessment.requires_confirmation:
        confirmation_request = await interceptor.force_secondary_confirmation(signal_record)

    gate_payload = {
        **action_payload,
        "extreme_signal_record_id": signal_record.record_id,
        "extreme_signal_source": signal_record.signal_source,
        "extreme_signal_risk_score": signal_record.risk_score,
        "extreme_signal_risk_indicators": list(signal_record.risk_indicators),
        "extreme_signal_confirmation_required": signal_record.confirmation_required,
        "extreme_signal_is_malicious": signal_record.is_malicious,
    }
    safety_decision = safety_gate.validate_action(
        action_type=action_type,
        action_payload=gate_payload,
        risk_level=_map_extreme_signal_risk(signal_record.risk_score),
        context={
            **context,
            "extreme_signal_record_id": signal_record.record_id,
            "extreme_signal_confirmation_required": signal_record.confirmation_required,
        },
    )

    issues: list[str] = []
    if signal_record.confirmation_required and confirmation_request is None:
        issues.append("missing_secondary_confirmation")
    if signal_record.confirmation_required and safety_decision.allowed:
        issues.append("safety_gate_allowed_extreme_signal")
    if signal_record.is_malicious and safety_decision.status == SafetyDecisionStatus.ALLOWED:
        issues.append("safety_gate_allowed_malicious_signal")
    if safety_decision.action_payload.get("extreme_signal_record_id") != signal_record.record_id:
        issues.append("missing_signal_record_id_in_gate_payload")
    if issues:
        raise ExtremeSignalSafetyGateError(
            "Extreme signal SafetyGate linkage failed closed.",
            issues,
        )

    return ExtremeSignalSafetyGateReport(
        audit_status="passed",
        signal_record=signal_record,
        confirmation_request=confirmation_request,
        safety_decision=safety_decision,
        gate_audit_count=len(safety_gate.get_audit_log()),
        linkage_evidence={
            "signal_record_id": signal_record.record_id,
            "risk_score": signal_record.risk_score,
            "risk_indicators": list(signal_record.risk_indicators),
            "safety_status": safety_decision.status.value,
            "safety_allowed": safety_decision.allowed,
            "safety_risk_level": safety_decision.risk_level.value,
            "confirmation_request_id": (
                confirmation_request.request_id if confirmation_request else None
            ),
        },
    )


def _map_extreme_signal_risk(risk_score: float) -> SafetyRiskLevel:
    if risk_score >= 0.9:
        return SafetyRiskLevel.CRITICAL
    if risk_score >= 0.8:
        return SafetyRiskLevel.HIGH
    if risk_score >= 0.7:
        return SafetyRiskLevel.MEDIUM
    return SafetyRiskLevel.LOW
