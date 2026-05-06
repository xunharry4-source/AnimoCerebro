from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType
from zentex.safety.cloud_auditor import CloudAuditorClient, CloudAuditorConfig, CloudDecisionStatus
from zentex.safety.safety_gate import RiskLevel, SafetyDecisionStatus


UTC = timezone.utc
SAFETY_ENTRY_ACTION_VALIDATED = "g8_safety_gate_action_validated"
SAFETY_ENTRY_ACTION_CONFIRMED = "g8_safety_gate_action_confirmed"
_FINAL_SAFETY_GATE_DECISIONS: dict[str, dict[str, Any]] = {}


def validate_safety_gate_action(
    kernel_service: Any,
    *,
    session_id: str,
    action_type: str,
    action_payload: dict[str, Any],
    risk_level: str | None = None,
    context: dict[str, Any] | None = None,
    execution_mode: str = "real",
    cloud_audit_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate concrete execution parameters through the G8 SafetyGate."""
    state = _require_session_state(kernel_service, session_id)
    manager = _require_safety_manager(kernel_service)
    _validate_concrete_action(action_type=action_type, action_payload=action_payload)
    normalized_risk = _normalize_risk(risk_level)
    normalized_context = _json_safe(context or {})
    normalized_mode = str(execution_mode or "real").strip().lower()

    decision = manager.validate_through_gate(
        action_type=action_type,
        action_payload=_json_safe(action_payload),
        risk_level=normalized_risk,
        context=normalized_context,
    )
    gate_payload = _decision_payload(decision)
    identity_block_reason = _identity_kernel_absolute_block_reason(action_type=action_type, action_payload=action_payload)
    if identity_block_reason:
        gate_payload["status"] = SafetyDecisionStatus.BLOCKED.value
        gate_payload["allowed"] = False
        gate_payload["reason"] = identity_block_reason
        gate_payload["redline_category"] = "identity_write"
        constraints = dict(gate_payload.get("constraints") or {})
        constraints["identity_kernel_absolute_prohibition"] = True
        constraints["non_bypassable_constraints"] = [
            "reject_identity_kernel_overreach",
            "preserve_identity_kernel_integrity",
        ]
        gate_payload["constraints"] = constraints
    cloud_decision = None
    cloud_required = _requires_cloud_audit(
        gate_payload,
        requested_risk=normalized_risk,
        execution_mode=normalized_mode,
    )
    if cloud_required and cloud_audit_config:
        cloud_decision = _run_cloud_audit(
            action_type=gate_payload["action_type"],
            action_payload=_json_safe(action_payload),
            risk_level=gate_payload["risk_level"],
            context=normalized_context,
            cloud_audit_config=cloud_audit_config,
        )

    final_payload = _finalize_decision(
        gate_payload,
        session_id=session_id,
        execution_mode=normalized_mode,
        cloud_required=cloud_required,
        cloud_decision=cloud_decision,
        reviewed_execution_parameters=_concrete_execution_parameters(action_payload),
    )
    _write_transcript(
        state,
        session_id=session_id,
        event=SAFETY_ENTRY_ACTION_VALIDATED,
        payload={
            "decision_id": final_payload["decision_id"],
            "action_type": final_payload["action_type"],
            "status": final_payload["status"],
            "execution_allowed": final_payload["execution_allowed"],
            "cloud_audit_required": final_payload["cloud_audit_required"],
        },
    )
    _FINAL_SAFETY_GATE_DECISIONS[final_payload["decision_id"]] = dict(final_payload)
    return final_payload


def query_safety_gate_decision(
    kernel_service: Any,
    *,
    session_id: str,
    decision_id: str,
) -> dict[str, Any]:
    """Query the real in-memory SafetyGate audit log for a G8 decision."""
    _require_session_state(kernel_service, session_id)
    final_decision = _FINAL_SAFETY_GATE_DECISIONS.get(decision_id)
    if final_decision is not None:
        return {
            **dict(final_decision),
            "session_id": session_id,
            "query_visible": True,
        }
    manager = _require_safety_manager(kernel_service)
    for decision in manager.safety_gate.get_audit_log():
        if decision.decision_id == decision_id:
            return {
                "feature_code": "G8",
                "session_id": session_id,
                **_decision_payload(decision),
                "query_visible": True,
            }
    raise KeyError(f"G8 SafetyGate decision not found: {decision_id}")


def confirm_safety_gate_decision(
    kernel_service: Any,
    *,
    session_id: str,
    decision_id: str,
    confirmed_by: str,
    confirmation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confirm a pending dual-confirmation G8 decision."""
    state = _require_session_state(kernel_service, session_id)
    manager = _require_safety_manager(kernel_service)
    if not confirmed_by:
        raise ValueError("confirmed_by is required")
    confirmed = manager.safety_gate.confirm_action(
        decision_id=decision_id,
        confirmed_by=confirmed_by,
        confirmation_context=_json_safe(confirmation_context or {}),
    )
    payload = {
        "feature_code": "G8",
        "session_id": session_id,
        **_decision_payload(confirmed),
        "confirmed_from_decision_id": decision_id,
        "execution_allowed": bool(confirmed.allowed),
    }
    _write_transcript(
        state,
        session_id=session_id,
        event=SAFETY_ENTRY_ACTION_CONFIRMED,
        payload={
            "decision_id": payload["decision_id"],
            "confirmed_from_decision_id": decision_id,
            "status": payload["status"],
            "execution_allowed": payload["execution_allowed"],
        },
    )
    return payload


def _validate_concrete_action(*, action_type: str, action_payload: dict[str, Any]) -> None:
    if not str(action_type or "").strip():
        raise ValueError("action_type is required")
    if not isinstance(action_payload, dict) or not action_payload:
        raise ValueError("action_payload must contain concrete execution parameters")
    concrete_keys = {"target", "path", "parameters", "command", "operations", "execution_domain", "resource"}
    if not any(key in action_payload for key in concrete_keys):
        raise ValueError(
            "SafetyGate requires concrete execution parameters such as target, path, parameters, command, or operations"
        )


def _concrete_execution_parameters(action_payload: dict[str, Any]) -> dict[str, Any]:
    concrete_keys = ("target", "path", "parameters", "command", "operations", "execution_domain", "resource")
    return {key: _json_safe(action_payload[key]) for key in concrete_keys if key in action_payload}


def _identity_kernel_absolute_block_reason(*, action_type: str, action_payload: dict[str, Any]) -> str | None:
    if action_type in {"update_identity_kernel", "modify_core_constraints", "tamper_continuity_lock", "violate_self_binding"}:
        return None
    target = str(action_payload.get("target") or action_payload.get("path") or "").lower()
    protected_paths = (
        ".zentex/identity/",
        "config/identity",
        "src/zentex/kernel/",
        "src/zentex/foundation/meta.py",
        ".zentex/continuity_lock",
    )
    if any(path in target for path in protected_paths):
        return f"Unauthorized write attempt to protected identity asset: {target}"
    return None


def _requires_cloud_audit(gate_payload: dict[str, Any], *, requested_risk: str | None, execution_mode: str) -> bool:
    if execution_mode != "real":
        return False
    if gate_payload["status"] == SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT.value:
        return True
    risk = requested_risk or gate_payload["risk_level"]
    return risk in {"high", "critical"}


def _run_cloud_audit(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    risk_level: str,
    context: dict[str, Any],
    cloud_audit_config: dict[str, Any],
) -> dict[str, Any]:
    endpoint = str(cloud_audit_config.get("endpoint") or "").strip()
    api_key = str(cloud_audit_config.get("api_key") or "").strip()
    api_secret = str(cloud_audit_config.get("api_secret") or "").strip()
    timeout_seconds = float(cloud_audit_config.get("timeout_seconds") or 5.0)
    client = CloudAuditorClient(
        CloudAuditorConfig(
            endpoint=endpoint,
            api_key=api_key,
            api_secret=api_secret,
            timeout_seconds=timeout_seconds,
        ),
        brain_scope="zentex.g8.safety_gate",
    )
    decision = client.audit_action(
        action_type,
        action_payload,
        risk_level=risk_level if risk_level in {"low", "medium", "high", "critical"} else "high",
        context=context,
        use_cache=False,
    )
    return _model_dump(decision)


def _finalize_decision(
    gate_payload: dict[str, Any],
    *,
    session_id: str,
    execution_mode: str,
    cloud_required: bool,
    cloud_decision: dict[str, Any] | None,
    reviewed_execution_parameters: dict[str, Any],
) -> dict[str, Any]:
    cloud_status = str((cloud_decision or {}).get("status") or "")
    cloud_approved = cloud_status == CloudDecisionStatus.APPROVED.value
    execution_allowed = bool(gate_payload["allowed"])
    status = gate_payload["status"]
    reason = gate_payload["reason"]

    if cloud_required:
        local_terminal_block = gate_payload["status"] in {
            SafetyDecisionStatus.BLOCKED.value,
            SafetyDecisionStatus.REQUIRES_CONFIRMATION.value,
            SafetyDecisionStatus.REQUIRES_HUMAN_REVIEW.value,
        }
        if local_terminal_block:
            execution_allowed = False
        elif not cloud_decision:
            execution_allowed = False
            status = SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT.value
            reason = "High-risk real execution requires cloud audit approval"
        elif not cloud_approved:
            execution_allowed = False
            status = SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT.value
            reason = f"Cloud audit did not approve action: {cloud_decision.get('reason')}"
        elif gate_payload["status"] == SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT.value:
            execution_allowed = True
            status = SafetyDecisionStatus.ALLOWED.value
            reason = "Cloud audit approved high-risk action"

    if not execution_allowed and not gate_payload.get("replanning_feedback"):
        gate_payload["replanning_feedback"] = {
            "blocked_action": gate_payload["action_type"],
            "block_reason": reason,
            "suggested_alternatives": [
                "submit cloud audit approval",
                "choose a lower-risk action",
                "request human review",
            ],
            "required_modifications": ["provide required approval evidence or reduce risk"],
            "escalation_path": "operator_review",
        }

    return {
        "feature_code": "G8",
        "safety_gate_feature_code": "G12",
        "cloud_audit_feature_code": "G30" if cloud_required else None,
        "session_id": session_id,
        **gate_payload,
        "status": status,
        "reason": reason,
        "execution_mode": execution_mode,
        "reviewed_execution_parameters": reviewed_execution_parameters,
        "cloud_audit_required": cloud_required,
        "cloud_decision": cloud_decision,
        "cloud_audit_acceptance_status": "accepted" if cloud_approved else None,
        "execution_allowed": execution_allowed,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _decision_payload(decision: Any) -> dict[str, Any]:
    payload = _model_dump(decision)
    return {
        "decision_id": str(payload["decision_id"]),
        "action_type": str(payload["action_type"]),
        "action_payload": _json_safe(payload.get("action_payload") or {}),
        "status": str(payload["status"]),
        "allowed": bool(payload["allowed"]),
        "reason": str(payload.get("reason") or ""),
        "risk_level": str(payload["risk_level"]),
        "redline_category": payload.get("redline_category"),
        "bypass_attempts": list(payload.get("bypass_attempts") or []),
        "constraints": _json_safe(payload.get("constraints") or {}),
        "requires_confirmation_from": payload.get("requires_confirmation_from"),
        "audit_trail": list(payload.get("audit_trail") or []),
        "replanning_feedback": payload.get("replanning_feedback"),
        "gate_created_at": str(payload.get("created_at") or ""),
    }


def _require_session_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for G8 SafetyGate: {session_id}")
    return state


def _require_safety_manager(kernel_service: Any) -> Any:
    safety_service = getattr(kernel_service, "_safety_service", None)
    if safety_service is None:
        raise RuntimeError("G8 SafetyGate requires an attached safety service")
    manager = getattr(safety_service, "_manager", None)
    if manager is None or not callable(getattr(manager, "validate_through_gate", None)):
        raise RuntimeError("G8 SafetyGate requires SafetyService backed by SafetyManager")
    return manager


def _write_transcript(state: Any, *, session_id: str, event: str, payload: dict[str, Any]) -> None:
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("G8 SafetyGate requires a session transcript store")
    trace_id = f"g8-safety-gate:{uuid4().hex}"
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=session_id,
            turn_id=f"g8-{uuid4().hex}",
            trace_id=trace_id,
            source="kernel.safety_gate",
            payload={
                "feature_code": "G8",
                "entry_type": event,
                "trace_id": trace_id,
                **_json_safe(payload),
            },
        )
    )


def _normalize_risk(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    RiskLevel(text)
    return text


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
