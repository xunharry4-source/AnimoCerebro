from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc


async def run_preference_judgment(
    kernel: Any,
    *,
    session_id: str,
    detected_state: dict[str, Any],
    detection_source: str,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not detected_state:
        raise ValueError("detected_state is required")
    if not detection_source:
        raise ValueError("detection_source is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    environment_service = _require_environment_service(kernel)

    result = await environment_service.execute_preference_judgment(
        detected_state=detected_state,
        detection_source=detection_source,
        context=context or {},
    )
    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "preference_judgment",
        "detected_state": detected_state,
        "detection_source": detection_source,
        "context": context or {},
        "judgment": _dump(result),
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, payload, target_id=_judgment_target_id(payload))
    payload["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _append_transcript(state, payload, "g16_preference_judgment_completed")
    return payload


async def confirm_preference_case(
    kernel: Any,
    *,
    session_id: str,
    ambiguity_case_id: str,
    user_decision: str,
    user_id: str,
    confirmation_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id or not ambiguity_case_id or not user_decision or not user_id:
        raise ValueError("session_id, ambiguity_case_id, user_decision and user_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    environment_service = _require_environment_service(kernel)

    preference = await environment_service.confirm_user_preference(
        ambiguity_case_id=ambiguity_case_id,
        user_decision=user_decision,
        user_id=user_id,
        confirmation_context=confirmation_context or {},
    )
    preference_payload = _dump(preference) if preference is not None else None
    query_check = None
    if preference_payload is not None:
        queried = await _get_preference_from_store(environment_service, preference_payload["preference_id"])
        if queried is None:
            raise RuntimeError(f"G16 preference writeback query verification failed: {preference_payload['preference_id']}")
        query_check = _dump(queried)

    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "confirm_preference_case",
        "ambiguity_case_id": ambiguity_case_id,
        "user_decision": user_decision,
        "preference": preference_payload,
        "query_check": query_check,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, payload, target_id=preference_payload["preference_id"] if preference_payload else ambiguity_case_id)
    payload["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _append_transcript(state, payload, "g16_preference_case_confirmed")
    return payload


async def query_preference_record(
    kernel: Any,
    *,
    session_id: str,
    preference_id: str,
) -> dict[str, Any]:
    if not session_id or not preference_id:
        raise ValueError("session_id and preference_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    preference = await _get_preference_from_store(_require_environment_service(kernel), preference_id)
    if preference is None:
        raise KeyError(f"G16 preference not found: {preference_id}")
    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "query_preference_record",
        "preference": _dump(preference),
        "query_visible": True,
    }
    _append_transcript(state, payload, "g16_preference_record_queried")
    return payload


async def revoke_preference_record(
    kernel: Any,
    *,
    session_id: str,
    preference_id: str,
    reason: str,
    user_id: str,
) -> dict[str, Any]:
    if not session_id or not preference_id or not reason or not user_id:
        raise ValueError("session_id, preference_id, reason and user_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    environment_service = _require_environment_service(kernel)
    await environment_service.revoke_preference(preference_id=preference_id, reason=reason, user_id=user_id)
    queried = await _get_preference_from_store(environment_service, preference_id)
    if queried is None:
        raise RuntimeError(f"G16 preference revoke query verification failed: {preference_id}")
    preference_payload = _dump(queried)
    if preference_payload["status"] != "revoked":
        raise RuntimeError(f"G16 preference revoke did not persist revoked status: {preference_id}")

    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "revoke_preference_record",
        "preference_id": preference_id,
        "reason": reason,
        "preference": preference_payload,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, payload, target_id=preference_id)
    payload["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _append_transcript(state, payload, "g16_preference_record_revoked")
    return payload


async def intercept_extreme_signal(
    kernel: Any,
    *,
    session_id: str,
    signal_content: str,
    signal_source: str,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id or not signal_content or not signal_source:
        raise ValueError("session_id, signal_content and signal_source are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    environment_service = _require_environment_service(kernel)

    signal_record, confirmation_request = await environment_service.intercept_extreme_signal(
        signal_content=signal_content,
        signal_source=signal_source,
        context=context or {},
    )
    signal_payload = _dump(signal_record)
    confirmation_payload = _dump(confirmation_request) if confirmation_request is not None else None
    _cache_record(kernel, "_extreme_signal_records", signal_payload["record_id"], signal_record)
    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "intercept_extreme_signal",
        "signal_record": signal_payload,
        "confirmation_request": confirmation_payload,
        "decision_blocked": bool(signal_payload["confirmation_required"]),
        "reason": "extreme_signal_requires_secondary_confirmation" if signal_payload["confirmation_required"] else "signal_below_confirmation_threshold",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, payload, target_id=signal_payload["record_id"])
    payload["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _append_transcript(state, payload, "g16_extreme_signal_intercepted")
    return payload


async def mark_attack_sample(
    kernel: Any,
    *,
    session_id: str,
    signal_record_id: str,
    attack_type: str,
    confidence: float,
    analyst_id: Optional[str] = None,
) -> dict[str, Any]:
    if not session_id or not signal_record_id or not attack_type:
        raise ValueError("session_id, signal_record_id and attack_type are required")
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be within [0, 1]")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    environment_service = _require_environment_service(kernel)
    signal_record = getattr(kernel, "_extreme_signal_records", {}).get(signal_record_id)
    if signal_record is None:
        raise KeyError(f"G16 signal record not found: {signal_record_id}")
    marker = getattr(environment_service, "_attack_sample_marker", None)
    if marker is None or not callable(getattr(marker, "mark_malicious_signal", None)):
        raise RuntimeError("G16 requires attack sample marker")

    sample = await marker.mark_malicious_signal(
        signal_record=signal_record,
        attack_type=attack_type,
        confidence=confidence,
        analyst_id=analyst_id,
    )
    sample_payload = _dump(sample)
    detected = await environment_service.detect_similar_attack(
        new_signal=signal_record.signal_content,
        similarity_threshold=min(confidence, 0.85),
    )
    if detected is None or detected.matched_sample_id != sample.sample_id:
        raise RuntimeError(f"G16 attack sample query verification failed: {sample.sample_id}")
    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "mark_attack_sample",
        "attack_sample": sample_payload,
        "query_check": _dump(detected),
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, payload, target_id=sample.sample_id)
    payload["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _append_transcript(state, payload, "g16_attack_sample_marked")
    return payload


async def detect_similar_attack(
    kernel: Any,
    *,
    session_id: str,
    signal_content: str,
    similarity_threshold: float = 0.85,
) -> dict[str, Any]:
    if not session_id or not signal_content:
        raise ValueError("session_id and signal_content are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    match = await _require_environment_service(kernel).detect_similar_attack(
        new_signal=signal_content,
        similarity_threshold=similarity_threshold,
    )
    payload = {
        "feature_code": "G16",
        "session_id": session_id,
        "operation": "detect_similar_attack",
        "matched": match is not None,
        "attack_match": _dump(match) if match is not None else None,
        "query_visible": True,
    }
    _append_transcript(state, payload, "g16_similar_attack_detected")
    return payload


def _require_environment_service(kernel: Any) -> Any:
    service = getattr(kernel, "_environment_service", None)
    if service is None:
        raise RuntimeError("G16 requires EnvironmentAwarenessService")
    return service


async def _get_preference_from_store(environment_service: Any, preference_id: str) -> Any:
    store = getattr(environment_service, "_preference_store", None)
    if store is None or not callable(getattr(store, "get_preference", None)):
        raise RuntimeError("G16 requires PreferenceStore.get_preference")
    return await store.get_preference(preference_id)


def _judgment_target_id(payload: dict[str, Any]) -> str:
    judgment = payload.get("judgment") if isinstance(payload.get("judgment"), dict) else {}
    preference = judgment.get("preference") if isinstance(judgment.get("preference"), dict) else None
    ambiguity_case = judgment.get("ambiguity_case") if isinstance(judgment.get("ambiguity_case"), dict) else None
    if preference:
        return str(preference["preference_id"])
    if ambiguity_case:
        return str(ambiguity_case["case_id"])
    return f"g16-judgment:{payload['session_id']}:{payload['created_at']}"


def _persist_memory(kernel: Any, record: dict[str, Any], *, target_id: str) -> str:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        raise RuntimeError("G16 requires MemoryService evidence persistence")
    memory = memory_service.remember(
        title=f"G16 preference alignment {record['operation']}",
        summary=f"G16 {record['operation']} target {target_id}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g16_preference_alignment",
        trace_id=f"g16:{record['operation']}:{target_id}",
        target_id=target_id,
        tags=["G16", "preference_alignment", record["operation"]],
        preference_alignment_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if not memory_id or getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G16 memory writeback query verification failed: {memory_id}")
    return memory_id


def _cache_record(kernel: Any, attr: str, key: str, record: Any) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G16", "entry_type": entry_type, **record},
        )
    )


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value
