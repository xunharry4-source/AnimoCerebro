from __future__ import annotations

"""
Builders for upgrade management payloads.

This service converts internal upgrade management records into the web-console
contracts consumed by upgrade management APIs and pages.
"""

from zentex.upgrade.management import (
    FAILED_STATUSES,
    ONGOING_STATUSES,
    UpgradeLifecycleView,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeTargetKind,
    WAITING_STATUSES,
)
from zentex.upgrade.ledger import UpgradeAuditEvent, UpgradeMemoryRecord
from zentex.web_console.contracts.upgrades import (
    UpgradeAuditEventItem,
    UpgradeCountSummary,
    UpgradeMemoryRecordItem,
    UpgradeOverviewPayload,
    UpgradeRecordCollection,
    UpgradeRecordItem,
    LifecycleGroupedRecords,
    UpgradesByLifecycleViewPayload,
)


def build_upgrade_record_item(record: UpgradeManagementRecord) -> UpgradeRecordItem:
    return UpgradeRecordItem(
        record_id=record.record_id,
        target_kind=record.target_kind.value,
        action=record.action,
        target_id=record.target_id,
        title=record.title,
        reason=record.reason,
        trace_id=record.trace_id,
        request_id=record.request_id,
        source_event_id=record.source_event_id,
        parent_record_id=record.parent_record_id,
        evidence_refs=list(record.evidence_refs),
        change_summary=record.change_summary,
        function_summary=record.function_summary,
        previous_version=record.previous_version,
        current_version=record.current_version,
        candidate_version=record.candidate_version,
        current_status=record.current_status.value,
        lifecycle_view=record.lifecycle_view().value,
        current_progress=record.current_progress,
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
        memory_recall_query=record.memory_recall_query,
        recalled_memory_ids=list(record.recalled_memory_ids),
        recalled_success_patterns=list(record.recalled_success_patterns),
        recalled_failure_patterns=list(record.recalled_failure_patterns),
        recalled_suspect_patterns=list(record.recalled_suspect_patterns),
        memory_recall_summary=record.memory_recall_summary,
        audit_status=record.audit_status,
        memory_status=record.memory_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        can_cancel=record.current_status in WAITING_STATUSES | ONGOING_STATUSES,
        can_cleanup_failed_candidate=(
            record.target_kind is UpgradeTargetKind.PLUGIN
            and record.current_status in FAILED_STATUSES
        ),
    )


def build_upgrade_collection(
    store: UpgradeManagementStore,
    *,
    target_kind: UpgradeTargetKind,
    lifecycle: UpgradeLifecycleView,
    action: str | None = None,
) -> UpgradeRecordCollection:
    items = [
        build_upgrade_record_item(record)
        for record in store.list_records(
            target_kind=target_kind,
            lifecycle=lifecycle,
            action=action,
        )
    ]
    counts = UpgradeCountSummary.model_validate(store.build_counts(target_kind=target_kind))
    return UpgradeRecordCollection(
        target_kind=target_kind.value,
        lifecycle=lifecycle.value,
        action_filter=action,
        counts=counts,
        items=items,
    )


def build_upgrade_overview(store: UpgradeManagementStore) -> UpgradeOverviewPayload:
    llm_recent = [
        build_upgrade_record_item(record)
        for record in store.list_records(target_kind=UpgradeTargetKind.LLM)[:5]
    ]
    plugin_recent = [
        build_upgrade_record_item(record)
        for record in store.list_records(target_kind=UpgradeTargetKind.PLUGIN)[:5]
    ]
    return UpgradeOverviewPayload(
        llm=UpgradeCountSummary.model_validate(store.build_counts(target_kind=UpgradeTargetKind.LLM)),
        plugins=UpgradeCountSummary.model_validate(
            store.build_counts(target_kind=UpgradeTargetKind.PLUGIN)
        ),
        recent_llm=llm_recent,
        recent_plugins=plugin_recent,
    )


def build_upgrade_audit_event_item(event: UpgradeAuditEvent) -> UpgradeAuditEventItem:
    return UpgradeAuditEventItem.model_validate(event.model_dump())


def build_upgrade_memory_record_item(record: UpgradeMemoryRecord) -> UpgradeMemoryRecordItem:
    return UpgradeMemoryRecordItem.model_validate(record.model_dump())


def build_upgrades_by_lifecycle_view(
    store: UpgradeManagementStore,
    *,
    target_kind: UpgradeTargetKind | None = None,
    plugin_action: str | None = None,
) -> UpgradesByLifecycleViewPayload:
    """Build upgrades grouped by lifecycle view for tabbed display."""
    all_records = store.list_records(
        target_kind=target_kind,
        lifecycle=UpgradeLifecycleView.ALL,
        action=plugin_action if target_kind == UpgradeTargetKind.PLUGIN else None,
    )
    
    # Group records by lifecycle view
    grouped: dict[str, list[UpgradeManagementRecord]] = {
        "ongoing": [],
        "waiting": [],
        "failed": [],
        "cancelled": [],
        "completed": [],
    }
    
    for record in all_records:
        view = record.lifecycle_view().value
        if view in grouped:
            grouped[view].append(record)
    
    # Build response
    return UpgradesByLifecycleViewPayload(
        ongoing=LifecycleGroupedRecords(
            count=len(grouped["ongoing"]),
            items=[build_upgrade_record_item(r) for r in grouped["ongoing"]],
        ),
        waiting=LifecycleGroupedRecords(
            count=len(grouped["waiting"]),
            items=[build_upgrade_record_item(r) for r in grouped["waiting"]],
        ),
        failed=LifecycleGroupedRecords(
            count=len(grouped["failed"]),
            items=[build_upgrade_record_item(r) for r in grouped["failed"]],
        ),
        cancelled=LifecycleGroupedRecords(
            count=len(grouped["cancelled"]),
            items=[build_upgrade_record_item(r) for r in grouped["cancelled"]],
        ),
        completed=LifecycleGroupedRecords(
            count=len(grouped["completed"]),
            items=[build_upgrade_record_item(r) for r in grouped["completed"]],
        ),
    )
