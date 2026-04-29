from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from plugins.sensory.environment_interpreter.environment_interpreter_plugin import (
    build_default_environment_interpreter_plugin,
)
from plugins.sensory.prompt_injection_sanitizer.prompt_injection_sanitizer_plugin import (
    build_default_prompt_injection_sanitizer_plugin,
)
from plugins.sensory.webhook_ingest.webhook_ingest_plugin import build_default_webhook_ingest_plugin
from zentex.environment.sensory_chain_audit import execute_sensory_chain
from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc


def ingest_sensory_signal(
    kernel: Any,
    *,
    session_id: str,
    source: str,
    payload: str,
    domain: str = "environment",
    source_observations: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not source:
        raise ValueError("source is required")
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("payload must be a non-empty string")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    ingest_plugin = build_default_webhook_ingest_plugin()
    ingest_plugin.payload = payload
    report = execute_sensory_chain(
        ingest_plugin=ingest_plugin,
        sanitizer_plugin=build_default_prompt_injection_sanitizer_plugin(),
        interpreter_plugin=build_default_environment_interpreter_plugin(),
    )
    event_id = f"g10-event-{uuid4().hex}"
    sanitized = report.sanitized_signal
    event = report.environment_event
    conflict = _score_conflicts(source_observations or [], event.structured_payload)
    record = {
        "feature_code": "G10",
        "event_id": event_id,
        "session_id": session_id,
        "source": source,
        "domain": domain,
        "raw_fingerprint": report.raw_fingerprint,
        "chain_order": list(report.chain_order),
        "stage_plugin_ids": dict(report.stage_plugin_ids),
        "sanitized": {
            "sanitized_text": sanitized.sanitized_text,
            "injection_risk": bool(sanitized.injection_risk),
            "redaction_evidence": list(sanitized.redaction_evidence),
            "raw_fingerprint": sanitized.raw_fingerprint,
        },
        "structured_event": {
            "event_type": event.event_type,
            "source_plugin_id": event.source_plugin_id,
            "summary": event.summary,
            "structured_payload": dict(event.structured_payload),
            "risk_flags": list(event.risk_flags),
            "audit_evidence": list(event.audit_evidence),
        },
        "conflict_score": conflict["conflict_score"],
        "conflict_evidence": conflict["conflict_evidence"],
        "audit_status": report.audit_status,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, record)
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_sensory_events", event_id, record)
    _append_transcript(state, record, "g10_sensory_signal_ingested")
    return record


def query_sensory_event(kernel: Any, *, session_id: str, event_id: str) -> dict[str, Any]:
    if not session_id or not event_id:
        raise ValueError("session_id and event_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    record = getattr(kernel, "_sensory_events", {}).get(event_id)
    if not record or record["session_id"] != session_id:
        raise KeyError(f"G10 sensory event not found: {event_id}")
    _append_transcript(state, record, "g10_sensory_event_queried")
    return {**record, "query_visible": True}


def _score_conflicts(observations: list[dict[str, Any]], structured_payload: dict[str, Any]) -> dict[str, Any]:
    if not observations:
        return {"conflict_score": 0.0, "conflict_evidence": []}
    evidence: list[dict[str, Any]] = []
    extracted = set(str(item) for item in structured_payload.get("extracted_metrics", []) or [])
    risk_level = str(structured_payload.get("detected_risk_level") or "low")
    for item in observations:
        observed_value = str(item.get("value") or item.get("risk_level") or "")
        if observed_value and (observed_value in extracted or observed_value == risk_level):
            continue
        evidence.append(
            {
                "source": str(item.get("source") or "unknown"),
                "value": observed_value,
                "reason": "source_disagrees_with_sanitized_interpretation",
            }
        )
    score = min(1.0, len(evidence) / max(1, len(observations)))
    return {"conflict_score": round(score, 4), "conflict_evidence": evidence}


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    memory = memory_service.remember(
        title=f"G10 sensory event {record['event_id']}",
        summary=f"G10 {record['structured_event']['event_type']} risk={record['sanitized']['injection_risk']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="episodic",
        source="g10_sensory_adapter",
        trace_id=record["event_id"],
        target_id=record["raw_fingerprint"],
        tags=["G10", "sensory", "sanitized", record["structured_event"]["event_type"]],
        sensory_event=record,
    )
    return str(getattr(memory, "memory_id", "") or "") or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G10", "entry_type": entry_type, **record},
        )
    )
