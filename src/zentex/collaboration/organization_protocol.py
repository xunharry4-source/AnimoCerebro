"""G36 multi-Zentex delegated command and organization protocol."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


UTC = timezone.utc


class OrganizationSessionState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    WAITING = "waiting"
    RETRYING = "retrying"
    PARTIALLY_DONE = "partially_done"
    ESCALATED = "escalated"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrganizationTaskItemStatus(str, Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    WAITING_CONFIRMATION = "waiting_confirmation"
    IN_PROGRESS = "in_progress"
    PARTIALLY_DONE = "partially_done"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrganizationClaimStatus(str, Enum):
    WAITING_CONFIRMATION = "waiting_confirmation"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class OrganizationFailureClass(str, Enum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"
    PARTIAL = "partial"
    ESCALATION_REQUIRED = "escalation_required"


class OrganizationExceptionType(str, Enum):
    TIMEOUT = "timeout"
    HEARTBEAT_LOST = "heartbeat_lost"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CONTEXT_VERSION_MISMATCH = "context_version_mismatch"
    RESOURCE_CONFLICT = "resource_conflict"
    ACCEPTED_WITH_SCOPE_REDUCTION = "accepted_with_scope_reduction"
    WITHDRAWN = "withdrawn"
    POLICY_CHANGED = "policy_changed"
    MANUAL_OVERRIDE = "manual_override"
    SCHEMA_MISMATCH = "schema_mismatch"
    DEPENDENCY_CYCLE = "dependency_cycle"
    CONTAMINATION_RISK = "contamination_risk"
    ORPHANED_SESSION = "orphaned_session"
    OUT_OF_ORDER_EVENT = "out_of_order_event"
    STALE_RESULT = "stale_result"
    SPLIT_BRAIN_OWNER = "split_brain_owner"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EVIDENCE_MISSING = "evidence_missing"
    SECRECY_BOUNDARY_VIOLATION = "secrecy_boundary_violation"
    TENANT_BOUNDARY_VIOLATION = "tenant_boundary_violation"
    CLOCK_SKEW = "clock_skew"
    DANGLING_TAIL_TASK = "dangling_tail_task"


EXCEPTION_RECOVERY_ACTIONS: dict[OrganizationExceptionType, str] = {
    OrganizationExceptionType.TIMEOUT: "retry",
    OrganizationExceptionType.HEARTBEAT_LOST: "reroute",
    OrganizationExceptionType.IDEMPOTENCY_CONFLICT: "revalidate",
    OrganizationExceptionType.CONTEXT_VERSION_MISMATCH: "revalidate",
    OrganizationExceptionType.RESOURCE_CONFLICT: "reduce_scope",
    OrganizationExceptionType.ACCEPTED_WITH_SCOPE_REDUCTION: "reduce_scope",
    OrganizationExceptionType.WITHDRAWN: "reroute",
    OrganizationExceptionType.POLICY_CHANGED: "revalidate",
    OrganizationExceptionType.MANUAL_OVERRIDE: "suspend",
    OrganizationExceptionType.SCHEMA_MISMATCH: "revalidate",
    OrganizationExceptionType.DEPENDENCY_CYCLE: "suspend",
    OrganizationExceptionType.CONTAMINATION_RISK: "quarantine",
    OrganizationExceptionType.ORPHANED_SESSION: "reroute",
    OrganizationExceptionType.OUT_OF_ORDER_EVENT: "revalidate",
    OrganizationExceptionType.STALE_RESULT: "revalidate",
    OrganizationExceptionType.SPLIT_BRAIN_OWNER: "suspend",
    OrganizationExceptionType.BUDGET_EXHAUSTED: "reduce_scope",
    OrganizationExceptionType.EVIDENCE_MISSING: "revalidate",
    OrganizationExceptionType.SECRECY_BOUNDARY_VIOLATION: "quarantine",
    OrganizationExceptionType.TENANT_BOUNDARY_VIOLATION: "quarantine",
    OrganizationExceptionType.CLOCK_SKEW: "revalidate",
    OrganizationExceptionType.DANGLING_TAIL_TASK: "cancel",
}


class OrganizationAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"g36-audit-{uuid4().hex[:12]}")
    event_seq: int
    action: str
    actor_brain_id: str
    session_id: str | None = None
    task_item_id: str | None = None
    causal_parent: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationNodeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    trust_score: float = Field(default=0.75, ge=0.0, le=1.0)
    active_tasks: int = Field(default=0, ge=0)
    launch_count_window: int = Field(default=0, ge=0)
    status: Literal["online", "degraded", "offline", "paused"] = "online"
    heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationSkillAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement_id: str = Field(default_factory=lambda: f"g36-skill-{uuid4().hex[:12]}")
    brain_id: str
    skill_name: str
    evidence_ref: str
    source: str
    valid_until: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationSecurityReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: f"g36-security-{uuid4().hex[:12]}")
    actor_brain_id: str
    action: str
    accepted: bool
    risk_flags: list[str] = Field(default_factory=list)
    required_action: str = "allow"
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationTaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_item_id: str = Field(default_factory=lambda: f"g36-item-{uuid4().hex[:12]}")
    content: str
    objective: str
    requirements: list[str] = Field(default_factory=list)
    coordination_mode: Literal["solo", "delegated", "handoff"] = "delegated"
    bundle_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    failure_strategy: OrganizationFailureClass = OrganizationFailureClass.RETRYABLE
    recovery_action: str = "retry"
    status: OrganizationTaskItemStatus = OrganizationTaskItemStatus.OPEN
    owner_brain_id: str | None = None
    owner_epoch: int = 0


class OrganizationGoalAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initiator_brain_id: str
    title: str
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    acceptance_criteria: list[str] = Field(min_length=1)
    required_evidence: list[str] = Field(default_factory=list)
    tenant_scope: str = "default"
    secrecy_level: Literal["public", "internal", "restricted"] = "internal"
    context_version: int = Field(default=1, ge=1)
    task_breakdown: list[OrganizationTaskItem] = Field(min_length=1)
    idempotency_key: str | None = None


class OrganizationGoalSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default_factory=lambda: f"g36-session-{uuid4().hex[:12]}")
    title: str
    initiator_brain_id: str
    risk_level: str
    acceptance_criteria: list[str]
    required_evidence: list[str]
    tenant_scope: str
    secrecy_level: str
    context_version: int
    state: OrganizationSessionState = OrganizationSessionState.PENDING
    task_breakdown: list[OrganizationTaskItem]
    security_review: OrganizationSecurityReview
    event_seq: int = 0
    owner_epoch: int = 0
    forward_chain: list[str] = Field(default_factory=list)
    max_forward_depth: int = 1
    final_ack: bool = False
    memory_write_gate: bool = False
    audit_closeout: bool = False
    result_fresh_until: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationGoalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(default_factory=lambda: f"g36-claim-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    claimant_brain_id: str
    deliverables: list[str] = Field(min_length=1)
    required_resources: list[str] = Field(default_factory=list)
    eta_seconds: int = Field(gt=0)
    time_budget_seconds: int = Field(gt=0)
    token_budget: int = Field(default=0, ge=0)
    concurrency_quota: int = Field(default=1, ge=1)
    retry_budget: int = Field(default=1, ge=0)
    status: OrganizationClaimStatus = OrganizationClaimStatus.WAITING_CONFIRMATION
    confirmation_deadline: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationGoalDecline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decline_id: str = Field(default_factory=lambda: f"g36-decline-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    brain_id: str
    blocked_reason: str = Field(min_length=1)
    available_resources: list[str] = Field(default_factory=list)
    blocked_resources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationGoalProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    progress_id: str = Field(default_factory=lambda: f"g36-progress-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    reporter_brain_id: str
    percent_complete: int = Field(ge=0, le=100)
    status_note: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    overdue: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationCompletionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(default_factory=lambda: f"g36-submit-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    submitter_brain_id: str
    summary: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationCompletionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: f"g36-review-{uuid4().hex[:12]}")
    submission_id: str
    reviewer_brain_id: str
    accepted: bool
    checklist_results: dict[str, bool] = Field(default_factory=dict)
    cheating_detected: bool = False
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationFailureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_id: str = Field(default_factory=lambda: f"g36-failure-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    reporter_brain_id: str
    failure_class: OrganizationFailureClass
    exception_type: OrganizationExceptionType
    retry_count: int = Field(default=0, ge=0)
    recovery_action: str
    fallback_target: str | None = None
    blocked_reason: str
    resume_condition: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationRecoveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recovery_id: str = Field(default_factory=lambda: f"g36-recovery-{uuid4().hex[:12]}")
    failure_id: str
    session_id: str
    task_item_id: str
    action: str
    recovery_owner: str | None = None
    takeover_token: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationTrustRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str
    trust_score: float = Field(ge=0.0, le=1.0)
    strike_count: int = Field(ge=0)
    banned: bool = False
    launch_weight: float = Field(ge=0.0, le=1.0)
    participation_weight: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationOutcomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_id: str = Field(default_factory=lambda: f"g36-outcome-{uuid4().hex[:12]}")
    session_id: str
    success: bool
    lessons: list[str] = Field(default_factory=list)
    failure_analysis: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationGroupExperiencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(default_factory=lambda: f"g36-exp-{uuid4().hex[:12]}")
    source_session_id: str
    source_brain_id: str
    applicable_task_types: list[str] = Field(default_factory=list)
    lesson: str
    evidence_refs: list[str] = Field(default_factory=list)
    status: Literal["shared", "adopted", "rejected"] = "shared"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(default_factory=lambda: f"g36-turn-{uuid4().hex[:12]}")
    session_id: str
    actor_brain_id: str
    event_type: Literal[
        "context_sync",
        "capability_query",
        "capability_reply",
        "task_event",
        "resource_event",
        "audit_event",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    context_version: int = Field(ge=1)
    causal_parent: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationForwardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forward_id: str = Field(default_factory=lambda: f"g36-forward-{uuid4().hex[:12]}")
    session_id: str
    task_item_id: str
    requester_brain_id: str
    target_group_id: str
    reason: str = Field(min_length=1)
    parent_subtask_id: str | None = None
    forward_chain: list[str]
    accepted: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationProtocol:
    """In-memory G36 protocol ledger and state machine."""

    def __init__(self, *, heartbeat_ttl_seconds: int = 120) -> None:
        self.heartbeat_ttl = timedelta(seconds=heartbeat_ttl_seconds)
        self._heartbeats: dict[str, OrganizationNodeHeartbeat] = {}
        self._skills: dict[str, OrganizationSkillAnnouncement] = {}
        self._sessions: dict[str, OrganizationGoalSession] = {}
        self._claims: dict[str, OrganizationGoalClaim] = {}
        self._progress: dict[str, OrganizationGoalProgress] = {}
        self._submissions: dict[str, OrganizationCompletionSubmission] = {}
        self._reviews: dict[str, OrganizationCompletionReview] = {}
        self._failures: dict[str, OrganizationFailureRecord] = {}
        self._recoveries: dict[str, OrganizationRecoveryRecord] = {}
        self._trust: dict[str, OrganizationTrustRecord] = {}
        self._outcomes: dict[str, OrganizationOutcomeSummary] = {}
        self._experience_packets: dict[str, OrganizationGroupExperiencePacket] = {}
        self._declines: dict[str, OrganizationGoalDecline] = {}
        self._turns: dict[str, OrganizationConversationTurn] = {}
        self._forwards: dict[str, OrganizationForwardRecord] = {}
        self._audits: list[OrganizationAuditEvent] = []
        self._idempotency_index: dict[str, str] = {}
        self._event_seq = 0

    def heartbeat(self, heartbeat: OrganizationNodeHeartbeat) -> OrganizationNodeHeartbeat:
        stored = heartbeat.model_copy(update={"heartbeat_at": datetime.now(UTC)})
        self._heartbeats[stored.brain_id] = stored
        self._ensure_trust(stored.brain_id, stored.trust_score)
        self._audit("node_heartbeat", stored.brain_id, detail=stored.model_dump(mode="json"))
        return stored

    def announce_skill(self, announcement: OrganizationSkillAnnouncement) -> OrganizationSkillAnnouncement:
        self._require_fresh_node(announcement.brain_id)
        if announcement.valid_until <= datetime.now(UTC):
            raise ValueError("skill announcement valid_until must be in the future")
        self._skills[announcement.announcement_id] = announcement
        self._audit("skill_announcement", announcement.brain_id, detail=announcement.model_dump(mode="json"))
        return announcement

    def query_capabilities(self, capability: str | None = None) -> list[OrganizationSkillAnnouncement]:
        rows = [row for row in self._skills.values() if row.valid_until > datetime.now(UTC)]
        if capability:
            rows = [row for row in rows if row.skill_name == capability]
        return rows

    def security_review(self, *, actor_brain_id: str, action: str, text: str) -> OrganizationSecurityReview:
        lowered = text.lower()
        checks = {
            "prompt_injection": ["ignore previous", "忽略以上", "绕过规则", "bypass"],
            "infinite_loop": ["无限循环", "forever loop", "while true"],
            "secrecy_boundary_violation": ["泄露密钥", "dump secret", "export token"],
            "tenant_boundary_violation": ["跨租户", "other tenant"],
            "self_rewrite": ["未审计自我改写", "self modify without review"],
        }
        flags = [flag for flag, needles in checks.items() if any(needle in lowered for needle in needles)]
        accepted = not flags
        return OrganizationSecurityReview(
            actor_brain_id=actor_brain_id,
            action=action,
            accepted=accepted,
            risk_flags=flags,
            required_action="allow" if accepted else "reject",
        )

    def announce_goal(self, announcement: OrganizationGoalAnnouncement) -> OrganizationGoalSession:
        self._require_fresh_node(announcement.initiator_brain_id)
        if announcement.idempotency_key and announcement.idempotency_key in self._idempotency_index:
            return self.get_session(self._idempotency_index[announcement.idempotency_key])
        self._enforce_launch_limit(announcement.initiator_brain_id)
        dependency_ids = {item.task_item_id for item in announcement.task_breakdown}
        for item in announcement.task_breakdown:
            if item.task_item_id in item.depends_on or any(dep not in dependency_ids for dep in item.depends_on):
                raise ValueError("task_breakdown contains dependency_cycle or unknown dependency")
        review_text = " ".join(
            [
                announcement.title,
                " ".join(announcement.acceptance_criteria),
                " ".join(announcement.required_evidence),
                " ".join(item.content + " " + item.objective for item in announcement.task_breakdown),
            ]
        )
        review = self.security_review(
            actor_brain_id=announcement.initiator_brain_id,
            action="goal_announcement",
            text=review_text,
        )
        if not review.accepted:
            self._audit(
                "goal_security_rejected",
                announcement.initiator_brain_id,
                detail=review.model_dump(mode="json"),
            )
            raise ValueError("goal_security_review rejected announcement: " + ",".join(review.risk_flags))
        session = OrganizationGoalSession(
            title=announcement.title,
            initiator_brain_id=announcement.initiator_brain_id,
            risk_level=announcement.risk_level,
            acceptance_criteria=announcement.acceptance_criteria,
            required_evidence=announcement.required_evidence,
            tenant_scope=announcement.tenant_scope,
            secrecy_level=announcement.secrecy_level,
            context_version=announcement.context_version,
            task_breakdown=announcement.task_breakdown,
            security_review=review,
            state=OrganizationSessionState.PENDING,
        )
        self._sessions[session.session_id] = session
        if announcement.idempotency_key:
            self._idempotency_index[announcement.idempotency_key] = session.session_id
        self._touch_launch_count(announcement.initiator_brain_id)
        self._audit("goal_announcement", announcement.initiator_brain_id, session_id=session.session_id, detail=session.model_dump(mode="json"))
        return session

    def claim_goal(self, claim: OrganizationGoalClaim) -> OrganizationGoalClaim:
        session, item = self._session_item(claim.session_id, claim.task_item_id)
        self._require_fresh_node(claim.claimant_brain_id)
        self._enforce_participation_limit(claim.claimant_brain_id)
        if item.status not in {OrganizationTaskItemStatus.OPEN, OrganizationTaskItemStatus.PARTIALLY_DONE, OrganizationTaskItemStatus.FAILED}:
            raise ValueError(f"task item is not claimable: {item.status.value}")
        missing = sorted(set(item.requirements) - set(self._heartbeats[claim.claimant_brain_id].capabilities))
        if missing:
            raise ValueError("goal_function_check failed, missing capabilities: " + ",".join(missing))
        review = self.security_review(
            actor_brain_id=claim.claimant_brain_id,
            action="goal_claim",
            text=" ".join([item.content, item.objective, " ".join(claim.deliverables)]),
        )
        if not review.accepted:
            self._audit("goal_claim_security_rejected", claim.claimant_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=review.model_dump(mode="json"))
            raise ValueError("goal_security_review rejected claim: " + ",".join(review.risk_flags))
        status = OrganizationClaimStatus.WAITING_CONFIRMATION if session.risk_level in {"high", "critical"} else OrganizationClaimStatus.ACCEPTED
        stored = claim.model_copy(
            update={
                "status": status,
                "confirmation_deadline": datetime.now(UTC) + timedelta(seconds=claim.eta_seconds) if status == OrganizationClaimStatus.WAITING_CONFIRMATION else None,
            }
        )
        self._claims[stored.claim_id] = stored
        item_update = {
            "status": OrganizationTaskItemStatus.WAITING_CONFIRMATION if status == OrganizationClaimStatus.WAITING_CONFIRMATION else OrganizationTaskItemStatus.CLAIMED,
            "owner_brain_id": claim.claimant_brain_id,
            "owner_epoch": item.owner_epoch + 1,
        }
        self._replace_item(session.session_id, item.task_item_id, item.model_copy(update=item_update))
        new_state = OrganizationSessionState.WAITING if status == OrganizationClaimStatus.WAITING_CONFIRMATION else OrganizationSessionState.ACTIVE
        self._update_session(session.session_id, state=new_state, owner_epoch=session.owner_epoch + 1)
        self._audit("goal_claim", claim.claimant_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=stored.model_dump(mode="json"))
        return stored

    def confirm_claim(self, claim_id: str, *, confirmer_brain_id: str, accepted: bool) -> OrganizationGoalClaim:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        session, item = self._session_item(claim.session_id, claim.task_item_id)
        if confirmer_brain_id != session.initiator_brain_id:
            raise ValueError("only the initiating brain can confirm high-risk claims")
        if claim.status != OrganizationClaimStatus.WAITING_CONFIRMATION:
            raise ValueError(f"claim is not waiting confirmation: {claim.status.value}")
        status = OrganizationClaimStatus.ACCEPTED if accepted else OrganizationClaimStatus.REJECTED
        updated = claim.model_copy(update={"status": status})
        self._claims[claim_id] = updated
        item_status = OrganizationTaskItemStatus.CLAIMED if accepted else OrganizationTaskItemStatus.OPEN
        owner = item.owner_brain_id if accepted else None
        self._replace_item(session.session_id, item.task_item_id, item.model_copy(update={"status": item_status, "owner_brain_id": owner}))
        self._update_session(session.session_id, state=OrganizationSessionState.ACTIVE if accepted else OrganizationSessionState.PENDING)
        self._audit("goal_claim_confirmed", confirmer_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=updated.model_dump(mode="json"))
        return updated

    def expire_pending_claims(self, *, now: datetime | None = None) -> list[OrganizationGoalClaim]:
        current = now or datetime.now(UTC)
        expired: list[OrganizationGoalClaim] = []
        for claim in list(self._claims.values()):
            if claim.status != OrganizationClaimStatus.WAITING_CONFIRMATION:
                continue
            if claim.confirmation_deadline is None or claim.confirmation_deadline > current:
                continue
            session, item = self._session_item(claim.session_id, claim.task_item_id)
            updated = claim.model_copy(update={"status": OrganizationClaimStatus.WITHDRAWN})
            self._claims[claim.claim_id] = updated
            self._replace_item(
                session.session_id,
                item.task_item_id,
                item.model_copy(update={"status": OrganizationTaskItemStatus.OPEN, "owner_brain_id": None}),
            )
            self._update_session(session.session_id, state=OrganizationSessionState.PENDING)
            self._audit(
                "goal_claim_expired",
                claim.claimant_brain_id,
                session_id=session.session_id,
                task_item_id=item.task_item_id,
                detail=updated.model_dump(mode="json"),
            )
            expired.append(updated)
        return expired

    def decline_goal(self, decline: OrganizationGoalDecline) -> OrganizationGoalDecline:
        session, item = self._session_item(decline.session_id, decline.task_item_id)
        self._require_fresh_node(decline.brain_id)
        self._declines[decline.decline_id] = decline
        self._audit(
            "goal_decline",
            decline.brain_id,
            session_id=session.session_id,
            task_item_id=item.task_item_id,
            detail=decline.model_dump(mode="json"),
        )
        return decline

    def record_progress(self, progress: OrganizationGoalProgress) -> OrganizationGoalProgress:
        session, item = self._session_item(progress.session_id, progress.task_item_id)
        self._require_owner(item, progress.reporter_brain_id)
        stored = progress.model_copy(update={"overdue": self._is_progress_overdue(progress)})
        self._progress[stored.progress_id] = stored
        status = OrganizationTaskItemStatus.PARTIALLY_DONE if progress.percent_complete < 100 else OrganizationTaskItemStatus.COMPLETED
        if progress.percent_complete < 100:
            status = OrganizationTaskItemStatus.IN_PROGRESS
        self._replace_item(session.session_id, item.task_item_id, item.model_copy(update={"status": status}))
        self._update_session(session.session_id, state=OrganizationSessionState.ACTIVE)
        self._audit("goal_progress", progress.reporter_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=stored.model_dump(mode="json"))
        return stored

    def submit_completion(self, submission: OrganizationCompletionSubmission) -> OrganizationCompletionSubmission:
        session, item = self._session_item(submission.session_id, submission.task_item_id)
        self._require_owner(item, submission.submitter_brain_id)
        missing = sorted(set(session.required_evidence) - set(submission.evidence_refs))
        if missing:
            failure = OrganizationFailureRecord(
                session_id=session.session_id,
                task_item_id=item.task_item_id,
                reporter_brain_id=submission.submitter_brain_id,
                failure_class=OrganizationFailureClass.PARTIAL,
                exception_type=OrganizationExceptionType.EVIDENCE_MISSING,
                recovery_action=EXCEPTION_RECOVERY_ACTIONS[OrganizationExceptionType.EVIDENCE_MISSING],
                blocked_reason="missing required evidence: " + ",".join(missing),
                resume_condition="submit all required_evidence refs",
            )
            self._failures[failure.failure_id] = failure
            self._update_session(session.session_id, state=OrganizationSessionState.BLOCKED)
            self._audit("goal_completion_rejected_missing_evidence", submission.submitter_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=failure.model_dump(mode="json"))
            raise ValueError(f"completion submission missing required evidence: {','.join(missing)}")
        self._submissions[submission.submission_id] = submission
        self._replace_item(session.session_id, item.task_item_id, item.model_copy(update={"status": OrganizationTaskItemStatus.COMPLETED}))
        self._update_session(session.session_id, state=OrganizationSessionState.PARTIALLY_DONE)
        self._audit("goal_completion_submission", submission.submitter_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=submission.model_dump(mode="json"))
        return submission

    def review_completion(self, review: OrganizationCompletionReview) -> OrganizationCompletionReview:
        submission = self._submissions.get(review.submission_id)
        if submission is None:
            raise KeyError(f"Unknown submission_id: {review.submission_id}")
        session, item = self._session_item(submission.session_id, submission.task_item_id)
        if review.reviewer_brain_id not in {session.initiator_brain_id, item.owner_brain_id}:
            raise ValueError("reviewer must be initiator or current owner")
        self._reviews[review.review_id] = review
        if review.cheating_detected:
            self._penalize(submission.submitter_brain_id, "cheating_detected")
        if review.accepted and not review.cheating_detected and all(review.checklist_results.values()):
            all_done = all(row.status == OrganizationTaskItemStatus.COMPLETED for row in session.task_breakdown)
            if all_done:
                outcome = OrganizationOutcomeSummary(
                    session_id=session.session_id,
                    success=True,
                    lessons=["completed through G36 structured claim/progress/review flow"],
                    next_actions=["tail_cleanup", "memory_write_gate", "audit_closeout"],
                )
                self._outcomes[outcome.summary_id] = outcome
                self._update_session(
                    session.session_id,
                    state=OrganizationSessionState.COMPLETED,
                    final_ack=True,
                    memory_write_gate=True,
                    audit_closeout=True,
                    result_fresh_until=datetime.now(UTC) + timedelta(hours=1),
                )
        else:
            self._replace_item(session.session_id, item.task_item_id, item.model_copy(update={"status": OrganizationTaskItemStatus.FAILED}))
            self._update_session(session.session_id, state=OrganizationSessionState.FAILED)
        self._audit("goal_completion_review", review.reviewer_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=review.model_dump(mode="json"))
        return review

    def record_failure(self, failure: OrganizationFailureRecord) -> OrganizationRecoveryRecord:
        session, item = self._session_item(failure.session_id, failure.task_item_id)
        self._failures[failure.failure_id] = failure
        action = failure.recovery_action or EXCEPTION_RECOVERY_ACTIONS[failure.exception_type]
        state = {
            "retry": OrganizationSessionState.RETRYING,
            "reroute": OrganizationSessionState.WAITING,
            "reduce_scope": OrganizationSessionState.PARTIALLY_DONE,
            "revalidate": OrganizationSessionState.BLOCKED,
            "quarantine": OrganizationSessionState.BLOCKED,
            "suspend": OrganizationSessionState.BLOCKED,
            "resume": OrganizationSessionState.ACTIVE,
            "cancel": OrganizationSessionState.CANCELLED,
            "escalate": OrganizationSessionState.ESCALATED,
        }.get(action, OrganizationSessionState.BLOCKED)
        recovery = OrganizationRecoveryRecord(
            failure_id=failure.failure_id,
            session_id=session.session_id,
            task_item_id=item.task_item_id,
            action=action,
            recovery_owner=failure.fallback_target or item.owner_brain_id,
            takeover_token=f"g36-takeover-{uuid4().hex[:12]}" if action in {"reroute", "resume"} else None,
        )
        self._recoveries[recovery.recovery_id] = recovery
        self._replace_item(session.session_id, item.task_item_id, item.model_copy(update={"status": OrganizationTaskItemStatus.FAILED}))
        self._update_session(session.session_id, state=state)
        self._audit("goal_failure_record", failure.reporter_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=failure.model_dump(mode="json"))
        self._audit("goal_recovery_record", failure.reporter_brain_id, session_id=session.session_id, task_item_id=item.task_item_id, detail=recovery.model_dump(mode="json"))
        return recovery

    def share_group_experience(self, packet: OrganizationGroupExperiencePacket) -> OrganizationGroupExperiencePacket:
        self.get_session(packet.source_session_id)
        self._experience_packets[packet.packet_id] = packet
        self._audit("group_experience_packet", packet.source_brain_id, session_id=packet.source_session_id, detail=packet.model_dump(mode="json"))
        return packet

    def record_conversation_turn(self, turn: OrganizationConversationTurn) -> OrganizationConversationTurn:
        session = self.get_session(turn.session_id)
        self._require_fresh_node(turn.actor_brain_id)
        if turn.context_version < session.context_version:
            failure = OrganizationFailureRecord(
                session_id=session.session_id,
                task_item_id=session.task_breakdown[0].task_item_id,
                reporter_brain_id=turn.actor_brain_id,
                failure_class=OrganizationFailureClass.PARTIAL,
                exception_type=OrganizationExceptionType.CONTEXT_VERSION_MISMATCH,
                recovery_action=EXCEPTION_RECOVERY_ACTIONS[OrganizationExceptionType.CONTEXT_VERSION_MISMATCH],
                blocked_reason=f"context_version {turn.context_version} older than session {session.context_version}",
                resume_condition="resubmit context_sync with current context_version",
            )
            self._failures[failure.failure_id] = failure
            self._update_session(session.session_id, state=OrganizationSessionState.BLOCKED)
            self._audit("conversation_turn_rejected", turn.actor_brain_id, session_id=session.session_id, detail=failure.model_dump(mode="json"))
            raise ValueError(f"context_version_mismatch: expected >= {session.context_version}")
        self._turns[turn.turn_id] = turn
        self._audit(
            "conversation_turn",
            turn.actor_brain_id,
            session_id=session.session_id,
            causal_parent=turn.causal_parent,
            detail=turn.model_dump(mode="json"),
        )
        return turn

    def forward_task(
        self,
        *,
        session_id: str,
        task_item_id: str,
        requester_brain_id: str,
        target_group_id: str,
        reason: str,
    ) -> OrganizationForwardRecord:
        session, item = self._session_item(session_id, task_item_id)
        if requester_brain_id != session.initiator_brain_id:
            raise ValueError("only the initiator can authorize cross-group forwarding")
        if len(session.forward_chain) >= session.max_forward_depth:
            record = OrganizationForwardRecord(
                session_id=session_id,
                task_item_id=task_item_id,
                requester_brain_id=requester_brain_id,
                target_group_id=target_group_id,
                reason=reason,
                parent_subtask_id=item.task_item_id,
                forward_chain=session.forward_chain,
                accepted=False,
            )
            self._forwards[record.forward_id] = record
            self._audit("goal_forward_rejected", requester_brain_id, session_id=session_id, task_item_id=task_item_id, detail=record.model_dump(mode="json"))
            raise ValueError("max_forward_depth exceeded")
        updated_chain = [*session.forward_chain, target_group_id]
        record = OrganizationForwardRecord(
            session_id=session_id,
            task_item_id=task_item_id,
            requester_brain_id=requester_brain_id,
            target_group_id=target_group_id,
            reason=reason,
            parent_subtask_id=item.task_item_id,
            forward_chain=updated_chain,
            accepted=True,
        )
        self._forwards[record.forward_id] = record
        self._update_session(session_id, state=OrganizationSessionState.WAITING, forward_chain=updated_chain)
        self._audit("goal_forward", requester_brain_id, session_id=session_id, task_item_id=task_item_id, detail=record.model_dump(mode="json"))
        return record

    def repair_orphaned_session(self, *, session_id: str, recovery_owner: str) -> OrganizationRecoveryRecord:
        session = self.get_session(session_id)
        self._require_fresh_node(recovery_owner)
        orphaned = [
            item
            for item in session.task_breakdown
            if item.status in {OrganizationTaskItemStatus.CLAIMED, OrganizationTaskItemStatus.IN_PROGRESS, OrganizationTaskItemStatus.WAITING_CONFIRMATION}
            and (item.owner_brain_id is None or item.owner_brain_id not in self._heartbeats or self._heartbeats[item.owner_brain_id].status in {"offline", "paused"})
        ]
        if not orphaned:
            raise ValueError("no orphaned_session found")
        item = orphaned[0]
        failure = OrganizationFailureRecord(
            session_id=session.session_id,
            task_item_id=item.task_item_id,
            reporter_brain_id=recovery_owner,
            failure_class=OrganizationFailureClass.PARTIAL,
            exception_type=OrganizationExceptionType.ORPHANED_SESSION,
            recovery_action=EXCEPTION_RECOVERY_ACTIONS[OrganizationExceptionType.ORPHANED_SESSION],
            fallback_target=recovery_owner,
            blocked_reason="current owner missing or not dispatchable",
            resume_condition="assign recovery_owner through new claim",
        )
        recovery = self.record_failure(failure)
        self._replace_item(
            session.session_id,
            item.task_item_id,
            item.model_copy(update={"status": OrganizationTaskItemStatus.OPEN, "owner_brain_id": None, "owner_epoch": item.owner_epoch + 1}),
        )
        return recovery

    def get_session(self, session_id: str) -> OrganizationGoalSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        return session

    def list_sessions(self) -> list[OrganizationGoalSession]:
        return list(self._sessions.values())

    def get_claim(self, claim_id: str) -> OrganizationGoalClaim:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        return claim

    def list_trust_records(self) -> list[OrganizationTrustRecord]:
        return list(self._trust.values())

    def list_declines(self, session_id: str | None = None) -> list[OrganizationGoalDecline]:
        rows = list(self._declines.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    def list_conversation_turns(self, session_id: str | None = None) -> list[OrganizationConversationTurn]:
        rows = list(self._turns.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    def list_forwards(self, session_id: str | None = None) -> list[OrganizationForwardRecord]:
        rows = list(self._forwards.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    def get_trust_record(self, brain_id: str) -> OrganizationTrustRecord:
        return self._ensure_trust(brain_id, self._heartbeats.get(brain_id, OrganizationNodeHeartbeat(brain_id=brain_id)).trust_score)

    def list_audit_events(self, session_id: str | None = None) -> list[OrganizationAuditEvent]:
        if session_id:
            return [row for row in self._audits if row.session_id == session_id]
        return list(self._audits)

    def list_failures(self, session_id: str | None = None) -> list[OrganizationFailureRecord]:
        rows = list(self._failures.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    def list_recoveries(self, session_id: str | None = None) -> list[OrganizationRecoveryRecord]:
        rows = list(self._recoveries.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    def list_outcomes(self, session_id: str | None = None) -> list[OrganizationOutcomeSummary]:
        rows = list(self._outcomes.values())
        if session_id:
            rows = [row for row in rows if row.session_id == session_id]
        return rows

    @staticmethod
    def exception_matrix() -> dict[str, str]:
        return {key.value: value for key, value in EXCEPTION_RECOVERY_ACTIONS.items()}

    def _audit(
        self,
        action: str,
        actor_brain_id: str,
        *,
        session_id: str | None = None,
        task_item_id: str | None = None,
        causal_parent: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> OrganizationAuditEvent:
        self._event_seq += 1
        event = OrganizationAuditEvent(
            event_seq=self._event_seq,
            action=action,
            actor_brain_id=actor_brain_id,
            session_id=session_id,
            task_item_id=task_item_id,
            causal_parent=causal_parent,
            detail=detail or {},
        )
        self._audits.append(event)
        if session_id in self._sessions:
            self._update_session(session_id, event_seq=self._event_seq)
        return event

    def _session_item(self, session_id: str, task_item_id: str) -> tuple[OrganizationGoalSession, OrganizationTaskItem]:
        session = self.get_session(session_id)
        for item in session.task_breakdown:
            if item.task_item_id == task_item_id:
                return session, item
        raise KeyError(f"Unknown task_item_id: {task_item_id}")

    def _replace_item(self, session_id: str, task_item_id: str, updated_item: OrganizationTaskItem) -> None:
        session = self.get_session(session_id)
        items = [updated_item if item.task_item_id == task_item_id else item for item in session.task_breakdown]
        self._update_session(session_id, task_breakdown=items)

    def _update_session(self, session_id: str, **updates: Any) -> OrganizationGoalSession:
        session = self.get_session(session_id)
        updated = session.model_copy(update={**updates, "updated_at": datetime.now(UTC)})
        self._sessions[session_id] = updated
        return updated

    def _require_fresh_node(self, brain_id: str) -> OrganizationNodeHeartbeat:
        heartbeat = self._heartbeats.get(brain_id)
        if heartbeat is None:
            raise ValueError(f"node_heartbeat missing for {brain_id}")
        if heartbeat.status not in {"online", "degraded"}:
            raise ValueError(f"node_heartbeat not dispatchable: {heartbeat.status}")
        if datetime.now(UTC) - heartbeat.heartbeat_at > self.heartbeat_ttl:
            raise ValueError(f"node_heartbeat stale for {brain_id}")
        trust = self._ensure_trust(brain_id, heartbeat.trust_score)
        if trust.banned:
            raise ValueError(f"group_trust_record banned node: {brain_id}")
        return heartbeat

    def _ensure_trust(self, brain_id: str, initial_score: float) -> OrganizationTrustRecord:
        record = self._trust.get(brain_id)
        if record is None:
            record = OrganizationTrustRecord(
                brain_id=brain_id,
                trust_score=initial_score,
                strike_count=0,
                launch_weight=initial_score,
                participation_weight=initial_score,
            )
            self._trust[brain_id] = record
        return record

    def _penalize(self, brain_id: str, reason: str) -> OrganizationTrustRecord:
        record = self._ensure_trust(brain_id, self._heartbeats.get(brain_id, OrganizationNodeHeartbeat(brain_id=brain_id)).trust_score)
        strikes = record.strike_count + 1
        score = max(0.0, record.trust_score - 0.25)
        updated = record.model_copy(
            update={
                "trust_score": score,
                "strike_count": strikes,
                "banned": strikes >= 3,
                "launch_weight": max(0.0, score),
                "participation_weight": 0.0 if strikes >= 3 else max(0.0, score),
                "reasons": [*record.reasons, reason],
                "updated_at": datetime.now(UTC),
            }
        )
        self._trust[brain_id] = updated
        self._audit("trust_penalty_record", brain_id, detail=updated.model_dump(mode="json"))
        if updated.banned:
            self._audit("group_trust_record_banned", brain_id, detail=updated.model_dump(mode="json"))
        return updated

    def _enforce_launch_limit(self, brain_id: str) -> None:
        trust = self._ensure_trust(brain_id, self._heartbeats[brain_id].trust_score)
        allowed = 3 if trust.trust_score >= 0.8 else 1
        if self._heartbeats[brain_id].launch_count_window >= allowed:
            raise ValueError("dynamic launch rate limit exceeded for trust_score")

    def _touch_launch_count(self, brain_id: str) -> None:
        heartbeat = self._heartbeats[brain_id]
        self._heartbeats[brain_id] = heartbeat.model_copy(update={"launch_count_window": heartbeat.launch_count_window + 1})

    def _enforce_participation_limit(self, brain_id: str) -> None:
        heartbeat = self._heartbeats[brain_id]
        trust = self._ensure_trust(brain_id, heartbeat.trust_score)
        allowed = 2 if trust.trust_score >= 0.8 else 1
        open_items = sum(1 for session in self._sessions.values() for item in session.task_breakdown if item.owner_brain_id == brain_id and item.status in {OrganizationTaskItemStatus.CLAIMED, OrganizationTaskItemStatus.IN_PROGRESS, OrganizationTaskItemStatus.WAITING_CONFIRMATION})
        if open_items >= allowed:
            raise ValueError("dynamic participation rate limit exceeded for trust_score")

    @staticmethod
    def _require_owner(item: OrganizationTaskItem, brain_id: str) -> None:
        if item.owner_brain_id != brain_id:
            raise ValueError(f"brain {brain_id} is not current owner for task item {item.task_item_id}")

    @staticmethod
    def _is_progress_overdue(progress: OrganizationGoalProgress) -> bool:
        return progress.percent_complete < 100 and "late" in progress.status_note.lower()
