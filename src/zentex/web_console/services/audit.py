from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Protocol, Tuple
from zentex.web_console.contracts.audit import (
    AuditPagePayload,
    AuditRecordItem,
    TurnAuditItem,
    TurnAuditPagePayload,
    TurnToolSummaryItem,
)
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.contracts.transcript import TranscriptEventPayload


class _TranscriptEntryLike(Protocol):
    entry_id: str
    trace_id: str
    session_id: str
    turn_id: str
    entry_type: Any
    timestamp: Any
    source: str
    payload: Any


class _TranscriptStoreLike(Protocol):
    def get_entries_snapshot(self) -> list[_TranscriptEntryLike]: ...


def _entry_type_value(entry: _TranscriptEntryLike) -> str:
    entry_type = getattr(entry, "entry_type", None)
    return str(getattr(entry_type, "value", entry_type) or "")


def _resolve_transcript_entries(source: Any) -> List[_TranscriptEntryLike]:
    if hasattr(source, "get_entries_snapshot"):
        return list(source.get_entries_snapshot())
    if hasattr(source, "get_transcript_store") and callable(source.get_transcript_store):
        store = source.get_transcript_store()
        if hasattr(store, "get_entries_snapshot"):
            return list(store.get_entries_snapshot())
    if hasattr(source, "transcript_store") and hasattr(source.transcript_store, "get_entries_snapshot"):
        return list(source.transcript_store.get_entries_snapshot())
    raise TypeError("Expected transcript store, runtime, or facade with transcript store access")


def build_model_provider_traces(runtime: Any) -> List[ModelProviderTraceItem]:
    entries = _resolve_transcript_entries(runtime)
    entries_by_trace_id: Dict[str, List[_TranscriptEntryLike]] = {}
    for entry in entries:
        entries_by_trace_id.setdefault(entry.trace_id, []).append(entry)

    traces: Dict[str, ModelProviderTraceItem] = {}
    for entry in entries:
        if _entry_type_value(entry) not in {
            "model_provider_invoked",
            "model_provider_completed",
            "model_provider_failed",
        }:
            continue
        payload: Dict[str, Any] = entry.payload if isinstance(entry.payload, dict) else {}
        request_id = str(payload.get("request_id") or entry.trace_id)
        current = traces.get(
            request_id,
            ModelProviderTraceItem(
                trace_id=entry.trace_id,
                request_id=request_id,
                decision_id=str(payload.get("decision_id") or ""),
                phase_name=str(
                    payload.get("phase_name")
                    or (
                        payload.get("caller_context", {}).get("invocation_phase")
                        if isinstance(payload.get("caller_context"), dict)
                        else ""
                    )
                    or "unknown"
                ),
                session_id=entry.session_id,
                turn_id=entry.turn_id,
                provider_plugin_id=str(payload.get("provider_plugin_id") or "unknown"),
                provider_name=str(payload["provider_name"]) if payload.get("provider_name") is not None else None,
                model=str(payload["model"]) if payload.get("model") is not None else None,
                source_module=str(payload["caller_context"]["source_module"])
                if isinstance(payload.get("caller_context"), dict)
                and payload["caller_context"].get("source_module") is not None
                else None,
                invocation_phase=str(payload["caller_context"]["invocation_phase"])
                if isinstance(payload.get("caller_context"), dict)
                and payload["caller_context"].get("invocation_phase") is not None
                else None,
                question_driver_refs=[
                    str(item)
                    for item in (
                        payload.get("caller_context", {}).get("question_driver_refs", [])
                        if isinstance(payload.get("caller_context"), dict)
                        else []
                    )
                    if item is not None
                ],
                prompt=str(payload.get("prompt") or payload.get("system_prompt") or "") or None,
                context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
                request_driver=payload.get("request_driver") if isinstance(payload.get("request_driver"), dict) else {},
                result=payload.get("result") if isinstance(payload.get("result"), dict) else None,
                related_events=[],
            ),
        )
        invoked_at = current.invoked_at
        completed_at = current.completed_at
        failed_at = current.failed_at
        result_payload = current.result
        error_type = current.error_type
        error_message = current.error_message
        model = current.model
        if _entry_type_value(entry) == "model_provider_invoked":
            invoked_at = entry.timestamp.astimezone(timezone.utc).isoformat()
        elif _entry_type_value(entry) == "model_provider_completed":
            completed_at = entry.timestamp.astimezone(timezone.utc).isoformat()
            result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else None
            model = str(payload["model"]) if payload.get("model") is not None else current.model
        elif _entry_type_value(entry) == "model_provider_failed":
            failed_at = entry.timestamp.astimezone(timezone.utc).isoformat()
            error_type = str(payload.get("error_type") or "") or None
            error_message = str(payload.get("error_message") or "") or None

        traces[request_id] = current.model_copy(
            update={
                "invoked_at": invoked_at,
                "completed_at": completed_at,
                "failed_at": failed_at,
                "result": result_payload,
                "error_type": error_type,
                "error_message": error_message,
                "model": model,
                "related_events": [
                    TranscriptEventPayload(
                        entry_id=phase_entry.entry_id,
                        session_id=phase_entry.session_id,
                        turn_id=phase_entry.turn_id,
                        entry_type=phase_entry.entry_type.value,
                        timestamp=phase_entry.timestamp.astimezone(timezone.utc).isoformat(),
                        source=phase_entry.source,
                        trace_id=phase_entry.trace_id,
                        context_info={},
                        payload=phase_entry.payload if isinstance(phase_entry.payload, dict) else {},
                    )
                    for phase_entry in entries_by_trace_id.get(entry.trace_id, [])
                ],
            }
        )

    result = list(traces.values())
    result.sort(key=lambda item: item.invoked_at or "")
    return result


def summarize_audit_entry(entry: _TranscriptEntryLike) -> Tuple[str, List[str]]:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    summary = str(
        payload.get("summary") or payload.get("message") or payload.get("event_type") or _entry_type_value(entry)
    )
    refs = payload.get("question_driver_refs")
    question_driver_refs = [str(item) for item in refs if item is not None] if isinstance(refs, list) else []
    return summary, question_driver_refs


def build_audit_page(
    entries: List[_TranscriptEntryLike],
    *,
    page: int,
    page_size: int,
    request_id: str | None = None,
    decision_id: str | None = None,
) -> AuditPagePayload:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    filtered_entries = list(entries)
    if request_id or decision_id:
        filtered_entries = []
        for entry in entries:
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            payload_request_id = str(payload.get("request_id") or "").strip()
            payload_decision_id = str(payload.get("decision_id") or "").strip() or str(
                payload.get("caller_context", {}).get("decision_id")
                if isinstance(payload.get("caller_context"), dict)
                else ""
            ).strip()
            if request_id and payload_request_id != request_id:
                continue
            if decision_id and payload_decision_id != decision_id:
                continue
            filtered_entries.append(entry)
    ordered = list(reversed(filtered_entries))
    total_items = len(ordered)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size

    items: List[AuditRecordItem] = []
    for entry in ordered[start:end]:
        summary, refs = summarize_audit_entry(entry)
        items.append(
            AuditRecordItem(
                entry_id=entry.entry_id,
                trace_id=entry.trace_id,
                session_id=entry.session_id,
                turn_id=entry.turn_id,
                entry_type=_entry_type_value(entry),
                timestamp=entry.timestamp.astimezone(timezone.utc).isoformat(),
                source=entry.source,
                summary=summary,
                question_driver_refs=refs,
                context_info={},
            )
        )

    return AuditPagePayload(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


def build_turn_audit_page(
    entries: List[_TranscriptEntryLike],
    *,
    page: int,
    page_size: int,
) -> TurnAuditPagePayload:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    turns: Dict[Tuple[str, str], TurnAuditItem] = {}
    for entry in entries:
        key = (entry.session_id, entry.turn_id)
        current = turns.get(
            key,
            TurnAuditItem(
                turn_id=entry.turn_id,
                session_id=entry.session_id,
                status="unknown",
                goal_titles=[],
                tool_summaries=[],
            ),
        )
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        if _entry_type_value(entry) == "turn_started":
            current = current.model_copy(
                update={
                    "started_at": entry.timestamp.astimezone(timezone.utc).isoformat(),
                    "status": "in_progress",
                    "goal_titles": list(payload.get("goal_titles") or []),
                }
            )
        elif _entry_type_value(entry) == "turn_finished":
            current = current.model_copy(
                update={
                    "completed_at": entry.timestamp.astimezone(timezone.utc).isoformat(),
                    "status": str(payload.get("status") or "completed"),
                }
            )
        elif _entry_type_value(entry) in {
            "cognitive_tool_invoked",
            "cognitive_tool_completed",
            "cognitive_tool_failed",
        }:
            tool_id = str(payload.get("tool_id") or payload.get("plugin_id") or "")
            behavior_key = str(payload.get("behavior_key") or payload.get("feature_code") or "")
            summary = str(payload.get("summary") or _entry_type_value(entry))
            invocation_id = str(payload.get("invocation_id") or "") or None
            current.tool_summaries.append(
                TurnToolSummaryItem(
                    tool_id=tool_id,
                    behavior_key=behavior_key,
                    invocation_id=invocation_id,
                    trace_id=entry.trace_id,
                    summary=summary,
                )
            )
        turns[key] = current

    ordered = list(reversed(sorted(turns.values(), key=lambda item: item.started_at or "")))
    total_items = len(ordered)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size
    return TurnAuditPagePayload(
        items=ordered[start:end],
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )
