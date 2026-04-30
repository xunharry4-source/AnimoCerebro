from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from zentex.common.flow_audit import FlowAudit
from zentex.common.storage_paths import get_storage_paths
from zentex.web_console.contracts.audit import AuditPagePayload, AuditTraceStartsPagePayload, TurnAuditPagePayload
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.contracts.replay import TraceReplayPayload, TurnReplayPayload
from zentex.audit.trace_store import AuditTraceStore
from zentex.web_console.replay_builder import build_replay_payload, build_turn_replay_payload


class AuditService:
    """Public audit facade for modules that need durable audit writes."""

    def __init__(self, db_path: Union[str, Optional[Path]] = None) -> None:
        self._store = AuditTraceStore(db_path or get_storage_paths().runtime_data_dir / "audit_trace.sqlite3")

    @property
    def store(self) -> AuditTraceStore:
        return self._store

    def close(self) -> None:
        close = getattr(self._store, "close", None)
        if callable(close):
            close()

    def query_audit_entries(
        self,
        *,
        page: int = 1,
        page_size: int = 40,
        request_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> AuditPagePayload:
        return self._store.list_audit_entries(
            page=page,
            page_size=page_size,
            request_id=request_id,
            decision_id=decision_id,
        )

    def query_turn_audit_items(
        self,
        *,
        page: int = 1,
        page_size: int = 40,
    ) -> TurnAuditPagePayload:
        return self._store.list_turn_audit_items(page=page, page_size=page_size)

    def query_model_provider_traces(self) -> list[ModelProviderTraceItem]:
        return self._store.list_model_provider_traces()

    def query_flows(
        self,
        *,
        limit: int = 100,
        flow_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self._store.list_flows(limit=limit, flow_type=flow_type, status=status)

    def query_trace_starts(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._store.list_trace_starts(limit=limit)

    def query_trace_starts_page(
        self,
        *,
        page: int = 1,
        page_size: int = 40,
    ) -> AuditTraceStartsPagePayload:
        return AuditTraceStartsPagePayload(**self._store.list_trace_starts_page(page=page, page_size=page_size))

    def record_flow_start(self, audit: FlowAudit) -> None:
        self._store.record_flow_start(audit)

    def record_flow_end(self, audit: FlowAudit, *, status: str) -> None:
        self._store.record_flow_end(audit, status=status)

    def list_recent_events(self, *, limit: int = 1000) -> list[Any]:
        return self._store.get_entries_snapshot(limit=limit)

    def get_event_stream_revision(self) -> int:
        return self._store.get_revision()

    def wait_for_new_events(self, current_revision: int, timeout: float = 3.0) -> bool:
        return self._store.wait_for_revision_after(current_revision, timeout=timeout)

    def list_trace_events(self, trace_id: str) -> list[Any]:
        return self._store.read_by_trace_id(trace_id)

    def list_turn_events(self, turn_id: str, *, session_id: Optional[str] = None) -> list[Any]:
        return self._store.read_by_turn_id(turn_id, session_id=session_id)

    def find_intervention_entry(self, idempotency_key: str) -> Optional[Any]:
        return self._store.find_intervention_entry(idempotency_key)

    def list_agent_audit_records(self, agent_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._store.list_agent_audit_records(agent_id, limit=limit)

    def build_trace_replay(self, event_id: str, *, include_payload: bool = True) -> TraceReplayPayload:
        return build_replay_payload(self, event_id, include_payload=include_payload)

    def build_turn_replay(
        self,
        *,
        turn_id: str,
        session_id: Optional[str] = None,
        include_payload: bool = True,
    ) -> TurnReplayPayload:
        return build_turn_replay_payload(
            self,
            turn_id=turn_id,
            session_id=session_id,
            include_payload=include_payload,
        )

    def record_nine_question_audit(
        self,
        *,
        question_id: str,
        module_id: str,
        summary: str,
        payload: dict[str, Any],
        trace_id: str,
        session_id: str,
        turn_id: str,
        source: str,
        audit: Optional[FlowAudit] = None,
        status: str = "completed",
    ) -> dict[str, Any]:
        flow_audit = audit or FlowAudit.new(
            "nine_questions",
            source_module=source,
            question_driver_refs=[question_id],
        )
        self.record_flow_start(flow_audit)
        self._store.record_audit_entry(
            trace_id=trace_id,
            session_id=session_id,
            turn_id=turn_id,
            entry_type="flow_audit",
            source=source,
            summary=summary,
            question_driver_refs=[question_id],
            context_info={
                **flow_audit.as_payload(),
                "question_id": question_id,
                "module_id": module_id,
                "module_kind": "audit",
                "status": status,
            },
            payload={
                "question_id": question_id,
                "module_id": module_id,
                "summary": summary,
                "payload": json.loads(json.dumps(payload, ensure_ascii=False)),
                **flow_audit.as_payload(),
            },
        )
        self.record_flow_end(flow_audit, status=status)
        return {
            "audit_id": flow_audit.audit_id,
            "status": status,
        }


_default_service: Optional[AuditService] = None


def get_service() -> AuditService:
    global _default_service
    if _default_service is None:
        import os
        env_root = os.environ.get("ZENTEX_AUDIT_ROOT")
        db_path = (
            Path(env_root) / "audit_trace.sqlite3"
            if env_root
            else get_storage_paths().runtime_data_dir / "audit_trace.sqlite3"
        )
            
        _default_service = AuditService(db_path=db_path)
    return _default_service
