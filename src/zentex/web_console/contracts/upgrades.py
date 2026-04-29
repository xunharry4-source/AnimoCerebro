from __future__ import annotations

"""
Web-console contracts for upgrade management views.

This file defines the response models used by the upgrade management endpoints
so the UI can consistently display ongoing, completed, and failed LLM or
plugin evolution jobs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.upgrade.service import LLMUpgradeRequest, PluginEvolutionIntentRequest


class UpgradeRecordItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    target_kind: str
    action: str
    target_id: str
    title: str
    reason: str
    trace_id: str
    request_id: str
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    change_summary: str
    function_summary: str
    previous_version: Optional[str] = None
    current_version: str
    candidate_version: Optional[str] = None
    current_status: str
    lifecycle_view: str
    current_progress: int = Field(ge=0, le=100)
    success_stage: Optional[str] = None
    success_summary: Optional[str] = None
    reusable_insight: Optional[str] = None
    successful_command: Optional[str] = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: Optional[str] = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    failure_summary: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    failed_command: Optional[str] = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: Optional[bool] = None
    prevention_hint: Optional[str] = None
    learning_tags: list[str] = Field(default_factory=list)
    source_path: Optional[str] = None
    candidate_path: Optional[str] = None
    memory_recall_query: Optional[str] = None
    recalled_memory_ids: list[str] = Field(default_factory=list)
    recalled_success_patterns: list[str] = Field(default_factory=list)
    recalled_failure_patterns: list[str] = Field(default_factory=list)
    recalled_suspect_patterns: list[str] = Field(default_factory=list)
    memory_recall_summary: Optional[str] = None
    audit_status: str
    memory_status: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    payload: dict[str, object] = Field(default_factory=dict)
    prompt_target_file: Optional[str] = None
    prompt_upgrade_sections: list[str] = Field(default_factory=list)
    prompt_upgrade_notes: list[str] = Field(default_factory=list)
    prompt_upgrade_summary: Optional[str] = None
    can_cancel: bool = False
    can_promote: bool = False
    can_rollback: bool = False
    can_activate_phase_d: bool = False
    activation_receipts: dict[str, object] = Field(default_factory=dict)
    rollback_receipts: dict[str, object] = Field(default_factory=dict)
    can_cleanup_failed_candidate: bool = False


class UpgradeCountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    all: int = Field(ge=0)
    waiting: int = Field(ge=0)
    ongoing: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class UpgradeRecordCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_kind: str
    lifecycle: str
    action_filter: Optional[str] = None
    counts: UpgradeCountSummary
    items: list[UpgradeRecordItem] = Field(default_factory=list)


class UpgradeOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm: UpgradeCountSummary
    plugins: UpgradeCountSummary
    recent_llm: list[UpgradeRecordItem] = Field(default_factory=list)
    recent_plugins: list[UpgradeRecordItem] = Field(default_factory=list)


class LifecycleGroupedRecords(BaseModel):
    """Records grouped by lifecycle view for tabbed display."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    count: int = Field(ge=0)
    items: list[UpgradeRecordItem] = Field(default_factory=list)


class UpgradesByLifecycleViewPayload(BaseModel):
    """Response payload for upgrades grouped by lifecycle view."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    ongoing: LifecycleGroupedRecords
    waiting: LifecycleGroupedRecords
    failed: LifecycleGroupedRecords
    cancelled: LifecycleGroupedRecords
    completed: LifecycleGroupedRecords


class UpgradeActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1)
    operator_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)


class UpgradeRecordActionRequest(UpgradeActionRequest):
    record_id: str = Field(min_length=1)


class ExecuteLLMUpgradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1)
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    change_signals: list[str] = Field(default_factory=list)
    upgrade_required: Optional[bool] = None
    upgrade_request: LLMUpgradeRequest


class ExecutePluginEvolutionRequest(PluginEvolutionIntentRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UpgradeAuditEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    record_id: str
    trace_id: str
    request_id: str
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    target_kind: str
    action: str
    target_id: str
    title: str
    event_type: str
    reason: str
    summary: str
    current_status: str
    current_progress: int = Field(ge=0, le=100)
    previous_version: Optional[str] = None
    current_version: str
    candidate_version: Optional[str] = None
    success_stage: Optional[str] = None
    success_summary: Optional[str] = None
    reusable_insight: Optional[str] = None
    successful_command: Optional[str] = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: Optional[str] = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    failure_summary: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    failed_command: Optional[str] = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: Optional[bool] = None
    prevention_hint: Optional[str] = None
    learning_tags: list[str] = Field(default_factory=list)
    source_path: Optional[str] = None
    candidate_path: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class UpgradeMemoryRecordItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    record_id: str
    trace_id: str
    request_id: str
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    target_kind: str
    action: str
    target_id: str
    title: str
    memory_kind: str
    event_type: str
    summary: str
    current_status: str
    current_progress: int = Field(ge=0, le=100)
    previous_version: Optional[str] = None
    current_version: str
    candidate_version: Optional[str] = None
    success_stage: Optional[str] = None
    success_summary: Optional[str] = None
    reusable_insight: Optional[str] = None
    successful_command: Optional[str] = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: Optional[str] = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    failure_summary: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    failed_command: Optional[str] = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: Optional[bool] = None
    prevention_hint: Optional[str] = None
    learning_tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    
    
UpgradeRecordItem.model_rebuild()
UpgradeOverviewPayload.model_rebuild()
UpgradesByLifecycleViewPayload.model_rebuild()
UpgradeAuditEventItem.model_rebuild()
UpgradeMemoryRecordItem.model_rebuild()
ExecuteLLMUpgradeRequest.model_rebuild()
