from __future__ import annotations

"""Promotion and rollback operations for upgrade management records."""

from typing import Any

from zentex.upgrade.evidence import UpgradeEvidenceService
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.management import (
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    utc_now,
)
from zentex.upgrade.base_models import UpgradeTargetKind


class UpgradePublicationService:
    """Applies explicit operator release decisions to persisted upgrade records."""

    def __init__(
        self,
        *,
        store: UpgradeManagementStore,
        evidence_service: UpgradeEvidenceService,
        execution_service: UpgradeExecutionService | None = None,
    ) -> None:
        self._store = store
        self._evidence_service = evidence_service
        self._execution_service = execution_service

    def promote(
        self,
        *,
        record_id: str,
        target_kind: UpgradeTargetKind,
        reviewer_id: str,
        reason: str,
        evidence_refs: list[str],
    ) -> UpgradeManagementRecord:
        record = self._store.get(record_id)
        self._assert_target_kind(record, target_kind)
        if record.current_status not in {
            UpgradeLifecycleStatus.COMPLETED,
            UpgradeLifecycleStatus.REGISTERED,
        }:
            raise ValueError("Only completed or registered upgrade records can be promoted")
        if not reviewer_id.strip():
            raise ValueError("reviewer_id is required for promotion")

        record.current_status = UpgradeLifecycleStatus.ACTIVE
        record.current_progress = 100
        record.audit_status = "promoted"
        record.memory_status = "persisted"
        record.current_version = record.candidate_version or record.current_version
        record.finished_at = utc_now()
        record.evidence_refs = [*record.evidence_refs, *evidence_refs]
        payload = dict(record.payload)
        payload["promotion_decision"] = {
            "reviewer_id": reviewer_id,
            "reason": reason,
            "evidence_refs": list(evidence_refs),
        }
        record.payload = payload
        persisted = self._store.upsert(record)
        self._evidence_service.record_event(
            persisted,
            event_type=f"{target_kind.value}_upgrade_promoted",
            summary="Upgrade candidate was promoted by an explicit reviewer decision.",
            payload=payload["promotion_decision"],
        )
        return persisted

    def rollback(
        self,
        *,
        record_id: str,
        target_kind: UpgradeTargetKind,
        operator_id: str,
        reason: str,
        evidence_refs: list[str],
    ) -> UpgradeManagementRecord:
        record = self._store.get(record_id)
        self._assert_target_kind(record, target_kind)
        if not operator_id.strip():
            raise ValueError("operator_id is required for rollback")

        rollback_ok = False
        if self._execution_service is not None:
            rollback_ok = self._execution_service.execute_rollback(record_id)
        record = self._store.get(record_id)
        if not rollback_ok:
            if record.current_status is not UpgradeLifecycleStatus.ROLLBACK_FAILED:
                record.current_status = UpgradeLifecycleStatus.ROLLBACK_FAILED
                record.failure_stage = "rollback"
                record.failure_reason = "Rollback execution did not complete."
            persisted = self._store.upsert(record)
            self._evidence_service.record_event(
                persisted,
                event_type=f"{target_kind.value}_upgrade_rollback_failed",
                summary="Upgrade rollback failed and was recorded without hiding the error.",
                payload={
                    "operator_id": operator_id,
                    "reason": reason,
                    "evidence_refs": list(evidence_refs),
                },
            )
            raise RuntimeError(record.failure_reason or "Rollback execution failed")

        record = self._store.get(record_id)
        record.current_status = UpgradeLifecycleStatus.ROLLED_BACK
        record.audit_status = "rolled_back"
        record.memory_status = "persisted"
        record.evolution_rollback_triggered = True
        record.finished_at = utc_now()
        record.evidence_refs = [*record.evidence_refs, *evidence_refs]
        payload = dict(record.payload)
        payload["rollback_decision"] = {
            "operator_id": operator_id,
            "reason": reason,
            "evidence_refs": list(evidence_refs),
        }
        record.payload = payload
        persisted = self._store.upsert(record)
        self._evidence_service.record_event(
            persisted,
            event_type=f"{target_kind.value}_upgrade_rolled_back",
            summary="Upgrade candidate rollback completed with a physical restore.",
            payload=payload["rollback_decision"],
        )
        return persisted

    @staticmethod
    def _assert_target_kind(record: UpgradeManagementRecord, target_kind: UpgradeTargetKind) -> None:
        if record.target_kind is not target_kind:
            raise ValueError(
                f"Upgrade record target kind mismatch: expected {target_kind.value}, got {record.target_kind.value}"
            )
