from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional, Protocol

from zentex.web_console.contracts.transcript import TranscriptEventPayload


class _TranscriptEntryLike(Protocol):
    entry_id: str
    session_id: str
    turn_id: str
    entry_type: Any
    timestamp: Any
    source: str
    trace_id: str
    payload: Any


def _entry_type_value(entry: _TranscriptEntryLike) -> str:
    entry_type = getattr(entry, "entry_type", None)
    return str(getattr(entry_type, "value", entry_type) or "")


def extract_context_info(entry: _TranscriptEntryLike) -> Dict[str, Any]:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    caller_context = (
        payload.get("caller_context") if isinstance(payload.get("caller_context"), dict) else {}
    )
    trace_chain = payload.get("trace_chain") if isinstance(payload.get("trace_chain"), dict) else {}

    def read_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    context_info: Dict[str, Any] = {}
    request_id = read_str(payload.get("request_id")) or read_str(trace_chain.get("request_id"))
    decision_id = (
        read_str(payload.get("decision_id"))
        or read_str(caller_context.get("decision_id"))
        or read_str(trace_chain.get("decision_id"))
    )
    phase_name = read_str(payload.get("phase_name")) or read_str(trace_chain.get("raw_phase_name"))
    source_module = read_str(caller_context.get("source_module")) or read_str(trace_chain.get("source_module"))
    invocation_phase = read_str(caller_context.get("invocation_phase")) or read_str(trace_chain.get("phase_name"))

    if request_id is not None:
        context_info["request_id"] = request_id
    if decision_id is not None:
        context_info["decision_id"] = decision_id
    if phase_name is not None:
        context_info["phase_name"] = phase_name
    if source_module is not None:
        context_info["source_module"] = source_module
    if invocation_phase is not None:
        context_info["invocation_phase"] = invocation_phase

    provider_plugin_id = read_str(payload.get("provider_plugin_id"))
    if provider_plugin_id is not None:
        context_info["provider_plugin_id"] = provider_plugin_id

    tool_id = read_str(payload.get("tool_id"))
    if tool_id is not None:
        context_info["tool_id"] = tool_id
    behavior_key = read_str(payload.get("behavior_key"))
    if behavior_key is not None:
        context_info["behavior_key"] = behavior_key
    phase = read_str(payload.get("phase"))
    if phase is not None:
        context_info["phase"] = phase

    plugin_id = read_str(payload.get("plugin_id"))
    if plugin_id is not None:
        context_info["plugin_id"] = plugin_id
    action = read_str(payload.get("action"))
    if action is not None:
        context_info["action"] = action
    audit_reason = read_str(payload.get("audit_reason"))
    if audit_reason is not None:
        context_info["audit_reason"] = audit_reason

    parent_trace_id = read_str(trace_chain.get("parent_trace_id"))
    if parent_trace_id is not None:
        context_info["parent_trace_id"] = parent_trace_id
    parent_turn_trace_id = read_str(trace_chain.get("parent_turn_trace_id"))
    if parent_turn_trace_id is not None:
        context_info["parent_turn_trace_id"] = parent_turn_trace_id
    trace_chain_version = trace_chain.get("version")
    if isinstance(trace_chain_version, int):
        context_info["trace_chain_version"] = trace_chain_version

    invocation_id = read_str(payload.get("invocation_id"))
    if invocation_id is not None:
        context_info["invocation_id"] = invocation_id

    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else None
    if provenance and isinstance(provenance.get("version"), int):
        context_info["provenance_version"] = int(provenance["version"])

    http_context = payload.get("http") if isinstance(payload.get("http"), dict) else None
    if http_context:
        context_info["http"] = http_context

    return context_info


def serialize_transcript_entry(
    entry: _TranscriptEntryLike,
    *,
    include_payload: bool = True,
) -> TranscriptEventPayload:
    return TranscriptEventPayload(
        entry_id=entry.entry_id,
        session_id=entry.session_id,
        turn_id=entry.turn_id,
        entry_type=_entry_type_value(entry),
        timestamp=entry.timestamp.astimezone(timezone.utc).isoformat(),
        source=entry.source,
        trace_id=entry.trace_id,
        context_info=extract_context_info(entry),
        payload=(
            entry.payload if include_payload else {"omitted": True, "reason": "include_payload=false"}
        ),
    )
