from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""
Builders for upgrade management payloads.

This service converts internal upgrade management records into the web-console
contracts consumed by upgrade management APIs and pages.
"""

from zentex.upgrade.service import (
    FAILED_STATUSES,
    ONGOING_STATUSES,
    UpgradeAuditEvent,
    UpgradeLifecycleView,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeMemoryRecord,
    UpgradeTargetKind,
    WAITING_STATUSES,
)
from zentex.upgrade.service import (
    UpgradeAuditStore,
    UpgradeMemoryStore,
)
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


def _extract_prompt_upgrade_view(payload: dict[str, object]) -> tuple[Optional[str], list[str], list[str], Optional[str]]:
    modified_files = payload.get("modified_files")
    prompt_target_file = (
        str(modified_files[0]).strip()
        if isinstance(modified_files, list) and modified_files and str(modified_files[0]).strip()
        else None
    )

    bundle = payload.get("candidate_prompt_bundle")
    bundle = bundle if isinstance(bundle, dict) else {}

    edited_sections = [
        str(item).strip()
        for item in bundle.get("edited_section_keys", [])
        if str(item).strip()
    ] if isinstance(bundle.get("edited_section_keys"), list) else []
    notes = [
        str(item).strip()
        for item in bundle.get("notes", [])
        if str(item).strip()
    ] if isinstance(bundle.get("notes"), list) else []

    summary_parts: list[str] = []
    if edited_sections:
        summary_parts.append(f"已优化段落: {', '.join(edited_sections)}")
    if prompt_target_file:
        summary_parts.append(f"目标文件: {prompt_target_file}")
    summary = " | ".join(summary_parts) if summary_parts else None
    return prompt_target_file, edited_sections, notes, summary


def build_upgrade_record_item(record: UpgradeManagementRecord) -> UpgradeRecordItem:
    payload = dict(record.payload)
    (
        prompt_target_file,
        prompt_upgrade_sections,
        prompt_upgrade_notes,
        prompt_upgrade_summary,
    ) = _extract_prompt_upgrade_view(payload)
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
        payload=payload,
        prompt_target_file=prompt_target_file,
        prompt_upgrade_sections=prompt_upgrade_sections,
        prompt_upgrade_notes=prompt_upgrade_notes,
        prompt_upgrade_summary=prompt_upgrade_summary,
        can_cancel=record.current_status in (WAITING_STATUSES | ONGOING_STATUSES),
        can_promote=record.current_status.value in {"canary_running", "validating", "registered"},
        can_rollback=record.current_status.value in {"active", "canary_running", "degraded", "completed"},
        can_activate_phase_d=(
            record.action == "phase_d_self_evolution"
            and record.current_status.value == "queued"
        ),
        activation_receipts=dict(payload.get("activation_receipts") or payload.get("phase_d_activation") or {}),
        rollback_receipts=dict(payload.get("rollback_receipts") or payload.get("phase_d_rollback") or {}),
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
    action: Optional[str] = None,
    limit: Optional[int] = None,
) -> UpgradeRecordCollection:
    items = [
        build_upgrade_record_item(record)
        for record in store.list_records(
            target_kind=target_kind,
            lifecycle=lifecycle,
            action=action,
            limit=limit,
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
    snapshot = store.build_overview_snapshot(recent_limit=5)
    llm_recent = [
        build_upgrade_record_item(record)
        for record in snapshot["recent_llm"]
    ]
    plugin_recent = [
        build_upgrade_record_item(record)
        for record in snapshot["recent_plugins"]
    ]
    return UpgradeOverviewPayload(
        llm=UpgradeCountSummary.model_validate(snapshot["llm"]),
        plugins=UpgradeCountSummary.model_validate(snapshot["plugins"]),
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
    target_kind: Optional[UpgradeTargetKind] = None,
    plugin_action: Optional[str] = None,
    per_group_limit: int = 50,
) -> UpgradesByLifecycleViewPayload:
    """Build upgrades grouped by lifecycle view for tabbed display."""
    action = plugin_action if target_kind == UpgradeTargetKind.PLUGIN else None
    counts = store.build_counts(target_kind=target_kind, action=action)
    capped_limit = max(1, min(int(per_group_limit), 200))

    def items_for(lifecycle: UpgradeLifecycleView) -> list[UpgradeRecordItem]:
        return [
            build_upgrade_record_item(record)
            for record in store.list_records(
                target_kind=target_kind,
                lifecycle=lifecycle,
                action=action,
                limit=capped_limit,
            )
        ]

    return UpgradesByLifecycleViewPayload(
        ongoing=LifecycleGroupedRecords(
            count=counts["ongoing"],
            items=items_for(UpgradeLifecycleView.ONGOING),
        ),
        waiting=LifecycleGroupedRecords(
            count=counts["waiting"],
            items=items_for(UpgradeLifecycleView.WAITING),
        ),
        failed=LifecycleGroupedRecords(
            count=counts["failed"],
            items=items_for(UpgradeLifecycleView.FAILED),
        ),
        cancelled=LifecycleGroupedRecords(
            count=counts["cancelled"],
            items=items_for(UpgradeLifecycleView.CANCELLED),
        ),
        completed=LifecycleGroupedRecords(
            count=counts["completed"],
            items=items_for(UpgradeLifecycleView.COMPLETED),
        ),
    )
