from __future__ import annotations

"""
Evidence recorder for upgrade audit and memory history.

This service turns upgrade management records into durable audit events and
memory snapshots so upgrades are traceable beyond the transient management
status view.
"""

from typing import Any, Dict, List, Optional, Union

from zentex.upgrade.ledger import (
    UpgradeAuditEvent,
    UpgradeAuditStore,
    UpgradeMemoryRecord,
    UpgradeMemoryStore,
)
from zentex.upgrade.management import UpgradeManagementRecord
class UpgradeEvidenceService:
    """Persists upgrade lifecycle evidence into audit and memory ledgers."""

    def __init__(
        self,
        *,
        audit_store: Optional[UpgradeAuditStore] = None,
        memory_store: Optional[UpgradeMemoryStore] = None,
        memory_service: Optional[Any] = None,
    ) -> None:
        self._audit_store = audit_store or UpgradeAuditStore()
        self._memory_store = memory_store or UpgradeMemoryStore()
        self._memory_service = memory_service

    @property
    def audit_store(self) -> UpgradeAuditStore:
        return self._audit_store

    @property
    def memory_store(self) -> UpgradeMemoryStore:
        return self._memory_store

    @property
    def memory_service(self) -> Optional[Any]:
        return self._memory_service

    def close(self) -> None:
        for store in (self._audit_store, self._memory_store):
            close = getattr(store, "close", None)
            if callable(close):
                close()

    def record_event(
        self,
        record: UpgradeManagementRecord,
        *,
        event_type: str,
        summary: str,
        payload: dict[str, Any] = None,
    ) -> UpgradeAuditEvent:
        event = UpgradeAuditEvent(
            record_id=record.record_id,
            trace_id=record.trace_id,
            request_id=record.request_id,
            source_event_id=record.source_event_id,
            parent_record_id=record.parent_record_id,
            target_kind=record.target_kind.value,
            action=record.action,
            target_id=record.target_id,
            title=record.title,
            event_type=event_type,
            reason=record.reason,
            summary=summary,
            current_status=record.current_status.value,
            current_progress=record.current_progress,
            previous_version=record.previous_version,
            current_version=record.current_version,
            candidate_version=record.candidate_version,
            success_stage=record.success_stage,
            success_summary=record.success_summary,
            reusable_insight=record.reusable_insight,
            successful_command=record.successful_command,
            success_artifact_refs=list(record.success_artifact_refs),
            promotion_hint=record.promotion_hint,
            success_tags=list(record.success_tags),
            failure_reason=record.failure_reason,
            failure_stage=record.failure_stage,
            failure_code=record.failure_code,
            failure_summary=record.failure_summary,
            root_cause_hypothesis=record.root_cause_hypothesis,
            failed_command=record.failed_command,
            failed_artifact_refs=list(record.failed_artifact_refs),
            retryable=record.retryable,
            prevention_hint=record.prevention_hint,
            learning_tags=list(record.learning_tags),
            source_path=record.source_path,
            candidate_path=record.candidate_path,
            evidence_refs=list(record.evidence_refs),
            payload=payload or {},
        )
        self._audit_store.append_event(event)
        memory_record = UpgradeMemoryRecord(
            record_id=record.record_id,
            trace_id=record.trace_id,
            request_id=record.request_id,
            source_event_id=record.source_event_id,
            parent_record_id=record.parent_record_id,
            target_kind=record.target_kind.value,
            action=record.action,
            target_id=record.target_id,
            title=record.title,
            event_type=event_type,
            summary=summary,
            current_status=record.current_status.value,
            current_progress=record.current_progress,
            previous_version=record.previous_version,
            current_version=record.current_version,
            candidate_version=record.candidate_version,
            success_stage=record.success_stage,
            success_summary=record.success_summary,
            reusable_insight=record.reusable_insight,
            successful_command=record.successful_command,
            success_artifact_refs=list(record.success_artifact_refs),
            promotion_hint=record.promotion_hint,
            success_tags=list(record.success_tags),
            failure_reason=record.failure_reason,
            failure_stage=record.failure_stage,
            failure_code=record.failure_code,
            failure_summary=record.failure_summary,
            root_cause_hypothesis=record.root_cause_hypothesis,
            failed_command=record.failed_command,
            failed_artifact_refs=list(record.failed_artifact_refs),
            retryable=record.retryable,
            prevention_hint=record.prevention_hint,
            learning_tags=list(record.learning_tags),
            evidence_refs=list(record.evidence_refs),
            payload=payload or {},
        )
        self._memory_store.append_record(memory_record)
        if self._memory_service is not None:
            self._memory_service.ingest_upgrade_memory_record(memory_record)
        return event
