from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from zentex.external_connectors.models import (
    ConnectorError,
    ConnectorInvocationRecord,
    ConnectorRiskLevel,
    ConnectorTestCallRequest,
    ConnectorVerificationMode,
)


def execute_connector_capability(service: Any, connector_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = str(payload.get("trace_id") or f"connector-execution-{uuid4().hex}")
    capability = str(payload.get("capability") or "").strip()
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    request = ConnectorTestCallRequest(capability=capability, arguments=arguments, trace_id=trace_id)
    record = service.get_connector(connector_id)
    service._assert_active(record)
    service._assert_capability(record, request.capability)
    before: dict[str, Any] = {}
    try:
        result = service._execute(record, request, before)
        capability_record = service._get_capability(record, request.capability)
        evidence_status = service._validate_evidence_for_capability(record, capability_record, result)
        invocation = ConnectorInvocationRecord(
            connector_id=record.connector_id,
            target_app=record.target_app,
            capability=request.capability,
            trace_id=trace_id,
            status="success",
            input_summary=service._summarize_input(request.arguments),
            output_summary=result.get("output_summary", result),
            before_evidence=result.get("before_evidence", before),
            after_evidence=result.get("after_evidence", {}),
            evidence_refs=result.get("evidence_refs", []),
            profile_level=service._effective_profile_level(record, capability_record),
            risk_level=capability_record.risk_level,
            verification_mode=capability_record.verification_mode,
            evidence_validation_status=evidence_status,
        )
    except Exception as exc:
        if not isinstance(exc, ConnectorError):
            raise
        capability_record = service._get_capability_or_none(record, request.capability)
        invocation = ConnectorInvocationRecord(
            connector_id=record.connector_id,
            target_app=record.target_app,
            capability=request.capability,
            trace_id=trace_id,
            status="failed",
            input_summary=service._summarize_input(request.arguments),
            before_evidence=before,
            error_code=exc.error_code,
            error_stage=exc.error_stage,
            operator_message=exc.operator_message,
            recovery_hint=exc.recovery_hint,
            profile_level=service._effective_profile_level(record, capability_record),
            risk_level=capability_record.risk_level if capability_record else ConnectorRiskLevel.READ_ONLY,
            verification_mode=capability_record.verification_mode if capability_record else ConnectorVerificationMode.NONE,
            evidence_validation_status="failed",
        )
        service._record_invocation(invocation, invocation_type="capability_execution")
        raise
    service._record_invocation(invocation, invocation_type="capability_execution")
    invocation_payload = invocation.model_dump(mode="json")
    return {
        "succeeded": invocation.status == "success",
        "status": invocation.status,
        "execution_api": "execute_capability",
        "result": invocation_payload,
        "output_summary": invocation_payload.get("output_summary") or {},
        "before_evidence": invocation_payload.get("before_evidence") or {},
        "after_evidence": invocation_payload.get("after_evidence") or {},
        "evidence_refs": invocation_payload.get("evidence_refs") or [],
        "evidence_validation_status": invocation_payload.get("evidence_validation_status"),
        "task_center_synchronized": False,
    }


__all__ = ["execute_connector_capability"]
