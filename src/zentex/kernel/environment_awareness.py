from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
ENVIRONMENT_SNAPSHOT_TAG = "G4"
ENVIRONMENT_AWARENESS_ENTRY_TYPE = "g4_environment_awareness_observed"


def observe_environment_awareness(
    kernel_service: Any,
    *,
    session_id: str,
    turn_id: str | None = None,
    raw_signals: list[str] | None = None,
    source_conflict_field: str = "memory_used_ratio",
    source_conflict_samples: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the G4 environment-awareness chain through the injected environment service."""
    state = _require_session_state(kernel_service, session_id)
    environment_service = _require_environment_service(kernel_service)
    resolved_turn_id = turn_id or f"g4-environment-{uuid4().hex}"
    trace_id = f"g4-environment-awareness:{uuid4().hex}"
    identity = kernel_service.get_system_identity()
    nine_question_state = kernel_service.get_nine_question_state()

    host_state = kernel_service._svc_call(environment_service, "sample_host_state")
    impact = kernel_service._svc_call(
        environment_service,
        "interpret_environment",
        host_state,
        current_role=identity.get("role_name"),
        identity=identity,
        nine_question_state=nine_question_state,
    )
    sanitized_signals = [
        _model_dump(
            kernel_service._svc_call(
                environment_service,
                "sanitize_signal",
                signal,
                source_plugin_id="g4-api",
                source_kind="runtime_environment_observation",
            )
        )
        for signal in (raw_signals or [])
    ]
    conflicts = [
        _model_dump(conflict)
        for conflict in kernel_service._svc_call(
            environment_service,
            "compare_multiple_sources",
            field_name=source_conflict_field,
            sources=source_conflict_samples or {},
        )
    ]
    snapshot = kernel_service._svc_call(
        environment_service,
        "create_context_snapshot",
        host_state=host_state,
        session_id=session_id,
        turn_id=resolved_turn_id,
        current_role=identity.get("role_name"),
        identity_anchor_ref=identity.get("role_name"),
        tags=[ENVIRONMENT_SNAPSHOT_TAG, "environment_awareness"],
        metadata={
            "feature_code": "G4",
            "trace_id": trace_id,
            "source_conflict_field": source_conflict_field,
            "sanitized_signal_count": len(sanitized_signals),
            "source_conflict_count": len(conflicts),
        },
    )

    physical_state = _model_dump(host_state)
    situation_impact = _model_dump(impact)
    context_snapshot = _model_dump(snapshot)
    payload = {
        "feature_code": "G4",
        "status": _status_from_host_state(physical_state),
        "session_id": session_id,
        "turn_id": resolved_turn_id,
        "trace_id": trace_id,
        "observed_at": datetime.now(UTC).isoformat(),
        "physical_state": physical_state,
        "situation_impact": situation_impact,
        "context_snapshot": context_snapshot,
        "sanitized_signals": sanitized_signals,
        "source_conflicts": conflicts,
        "degraded_or_unknown_fields": _degraded_or_unknown_fields(physical_state),
        "sampling_semantics": {
            "physical_host_sampled": True,
            "context_snapshot_persisted": True,
            "unknown_or_degraded_not_reported_as_healthy": True,
            "network_health_requires_active_interface": True,
            "prompt_injection_filtering_applied": True,
            "multi_source_conflict_scoring_applied": True,
        },
    }
    _write_transcript(state, session_id=session_id, turn_id=resolved_turn_id, payload=payload)
    return payload


def query_environment_awareness_snapshots(
    kernel_service: Any,
    *,
    session_id: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Query persisted G4 context snapshots for a session."""
    _require_session_state(kernel_service, session_id)
    environment_service = _require_environment_service(kernel_service)
    if limit <= 0:
        raise ValueError("limit must be > 0")
    snapshots = kernel_service._svc_call(
        environment_service,
        "query_snapshots",
        session_id=session_id,
        tag=ENVIRONMENT_SNAPSHOT_TAG,
    )
    ordered = sorted(snapshots, key=lambda item: item.timestamp, reverse=True)[:limit]
    return {
        "feature_code": "G4",
        "session_id": session_id,
        "snapshot_count": len(ordered),
        "snapshots": [_model_dump(snapshot) for snapshot in ordered],
    }


def _require_session_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for G4 environment awareness: {session_id}")
    return state


def _require_environment_service(kernel_service: Any) -> Any:
    service = getattr(kernel_service, "_environment_service", None)
    if service is None:
        raise RuntimeError("G4 environment awareness requires an attached environment service")
    return service


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _status_from_host_state(physical_state: dict[str, Any]) -> str:
    health = str(physical_state.get("overall_health") or "").lower()
    if health in {"critical", "offline"}:
        return "critical"
    if health in {"degraded", "unknown"}:
        return "degraded"
    if health == "healthy":
        return "healthy"
    return "unknown"


def _degraded_or_unknown_fields(physical_state: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for field in ("memory_pressure", "network_health", "overall_health"):
        value = str(physical_state.get(field) or "").lower()
        if value in {"unknown", "degraded", "critical", "offline"}:
            fields.append(field)
    for field in ("memory_used_ratio", "cpu_load_percent", "disk_usage_percent"):
        if physical_state.get(field) is None:
            fields.append(field)
    return fields


def _write_transcript(
    state: Any,
    *,
    session_id: str,
    turn_id: str,
    payload: dict[str, Any],
) -> None:
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("G4 environment awareness requires a session transcript store")
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.context_snapshot_written,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=str(payload["trace_id"]),
            source="kernel.environment_awareness",
            payload={
                "feature_code": "G4",
                "entry_type": ENVIRONMENT_AWARENESS_ENTRY_TYPE,
                "trace_id": payload["trace_id"],
                "snapshot_id": payload["context_snapshot"]["snapshot_id"],
                "status": payload["status"],
                "physical_state": payload["physical_state"],
                "situation_impact": payload["situation_impact"],
                "sanitized_signal_count": len(payload["sanitized_signals"]),
                "source_conflict_count": len(payload["source_conflicts"]),
            },
        )
    )
