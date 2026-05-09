from __future__ import annotations

"""Memory lifecycle and compaction governance for G39."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.memory.management.enhanced import EnhancedMemoryRecord, EnhancedMemoryService, MemoryRecallHit


UTC = timezone.utc
BLOCKED_REWARM_STATUSES = {"rejected"}
BLOCKED_REWARM_TRUST_LEVELS = {"revoked", "contaminated"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _age_days(created_at: datetime, now: datetime) -> float:
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return (now - created.astimezone(UTC)).total_seconds() / 86_400.0


def _memory_bytes(record: EnhancedMemoryRecord) -> int:
    return len(record.title.encode("utf-8")) + len(record.summary.encode("utf-8")) + len(record.content.encode("utf-8"))


class MemoryLifecyclePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hot_max_days: int = Field(default=14, ge=1)
    warm_max_days: int = Field(default=180, ge=1)
    hot_budget_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    warm_budget_bytes: int = Field(default=10 * 1024 * 1024 * 1024, ge=1)
    cold_budget_bytes: int = Field(default=50 * 1024 * 1024 * 1024, ge=1)
    experience_threshold: int = Field(default=3, ge=1)
    strategy_patch_threshold: int = Field(default=5, ge=1)
    strategy_patch_min_windows: int = Field(default=2, ge=1)
    low_value_confidence: float = Field(default=0.25, ge=0.0, le=1.0)


class MemoryLifecycleState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1)
    lifecycle_tier: str = Field(default="hot", min_length=1)
    status: str = Field(default="active", min_length=1)
    compressed_into_id: str | None = None
    rewarm_blocked: bool = False
    last_action: str = Field(default="tracked", min_length=1)
    updated_at: datetime = Field(default_factory=_utc_now)


class MemoryPromotionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_type: str = Field(min_length=1)
    pattern_key: str = Field(min_length=1)
    source_memory_ids: list[str]
    occurrence_count: int = Field(ge=1)
    window_count: int = Field(ge=1)
    requires_memory_governance_validation: bool = True


class MemoryCompactionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    compressed_memory_id: str = Field(min_length=1)
    source_memory_ids: list[str]
    records_before: int = Field(ge=0)
    records_after: int = Field(ge=0)
    bytes_before: int = Field(ge=0)
    bytes_after: int = Field(ge=0)
    benefit_ratio: float = Field(ge=0.0)
    reference_chain_preserved: bool
    created_at: datetime = Field(default_factory=_utc_now)


class MemoryLifecycleCycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str = Field(default_factory=lambda: str(uuid4()))
    scanned_count: int
    tier_updates: list[MemoryLifecycleState]
    archived_memory_ids: list[str]
    promotion_candidates: list[MemoryPromotionCandidate]
    hot_usage_bytes: int
    warm_usage_bytes: int
    cold_usage_bytes: int
    retrieval_latency_ms: float
    compaction_reports: list[MemoryCompactionReport] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class GovernedRecallHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit: MemoryRecallHit
    lifecycle_tier: str
    lifecycle_status: str
    adjusted_score: float
    rank_reason: str


class MemoryLifecycleGovernance:
    """G39 lifecycle governance backed by the real enhanced memory service."""

    def __init__(
        self,
        enhanced_service: EnhancedMemoryService,
        *,
        policy: MemoryLifecyclePolicy | None = None,
    ) -> None:
        self._enhanced_service = enhanced_service
        self.policy = policy or MemoryLifecyclePolicy()
        self._states: dict[str, MemoryLifecycleState] = {}
        self._cycles: list[MemoryLifecycleCycleReport] = []
        self._compactions: list[MemoryCompactionReport] = []
        self._contaminated_memory_ids: set[str] = set()
        self._lock = Lock()

    def run_cycle(self, *, operator: str = "memory_lifecycle", now: datetime | None = None) -> MemoryLifecycleCycleReport:
        now = now or _utc_now()
        started = _utc_now()
        records = self._enhanced_service.list_managed_records(limit=99999)
        tier_updates: list[MemoryLifecycleState] = []
        archived: list[str] = []
        usage = {"hot": 0, "warm": 0, "cold": 0}

        for record in records:
            state = self._state_for(record)
            target_tier = self._target_tier(record, now)
            should_archive = self._should_archive(record, target_tier, usage)
            if target_tier != state.lifecycle_tier:
                state = self._set_state(
                    record.memory_id,
                    lifecycle_tier=target_tier,
                    status="active",
                    last_action=f"tier_changed:{target_tier}",
                )
                tier_updates.append(state)
                self._enhanced_service.update_management_state(
                    record.memory_id,
                    management_note=f"G39 lifecycle tier={target_tier}",
                    operator=operator,
                    reason=f"G39 lifecycle tier changed to {target_tier}.",
                )
            usage[target_tier] += _memory_bytes(record)
            if should_archive:
                self._enhanced_service.update_management_state(
                    record.memory_id,
                    status="archived",
                    visibility="hidden",
                    management_note="G39 auto archived due to low value or budget pressure.",
                    operator=operator,
                    reason="G39 lifecycle auto archive.",
                )
                archived.append(record.memory_id)
                state = self._set_state(
                    record.memory_id,
                    lifecycle_tier=target_tier,
                    status="archived",
                    last_action="auto_archived",
                )
                tier_updates.append(state)

        candidates = self._promotion_candidates(records, now)
        report = MemoryLifecycleCycleReport(
            scanned_count=len(records),
            tier_updates=tier_updates,
            archived_memory_ids=archived,
            promotion_candidates=candidates,
            hot_usage_bytes=usage["hot"],
            warm_usage_bytes=usage["warm"],
            cold_usage_bytes=usage["cold"],
            retrieval_latency_ms=(_utc_now() - started).total_seconds() * 1000.0,
            compaction_reports=list(self._compactions),
        )
        with self._lock:
            self._cycles.append(report)
        return report

    def governed_recall(self, query: str, *, limit: int = 10) -> list[GovernedRecallHit]:
        hits = self._enhanced_service.recall(query=query, limit=limit * 5)
        governed: list[GovernedRecallHit] = []
        for hit in hits:
            managed = self._enhanced_service.get_managed_record(hit.memory_id)
            if managed is None:
                continue
            state = self._state_for(managed)
            if not self._can_recall(managed.status, managed.visibility, managed.trust_level, state):
                continue
            tier_weight = {"hot": 0.04, "warm": 0.02, "cold": -0.04}.get(state.lifecycle_tier, 0.0)
            status_weight = -0.08 if managed.status == "deprecated" else 0.0
            adjusted = max(0.0, min(1.0, hit.score + tier_weight + status_weight))
            governed.append(
                GovernedRecallHit(
                    hit=hit,
                    lifecycle_tier=state.lifecycle_tier,
                    lifecycle_status=managed.status,
                    adjusted_score=adjusted,
                    rank_reason=f"tier={state.lifecycle_tier};status={managed.status};visibility={managed.visibility}",
                )
            )
        return sorted(governed, key=lambda row: row.adjusted_score, reverse=True)[:limit]

    def compress_memories(
        self,
        memory_ids: list[str],
        *,
        summary: str,
        operator: str = "memory_lifecycle",
    ) -> MemoryCompactionReport:
        if len(memory_ids) < 2:
            raise ValueError("at least two memories are required for compaction")
        records = [self._required_record(memory_id) for memory_id in memory_ids]
        for record in records:
            state = self._state_for(record)
            if state.rewarm_blocked or record.status == "rejected" or record.trust_level in BLOCKED_REWARM_TRUST_LEVELS:
                raise ValueError(f"memory {record.memory_id} is blocked from compaction")
        content = "\n".join(f"- {record.title}: {record.summary}" for record in records)
        compressed = self._enhanced_service.store_memory(
            title=f"Compressed lifecycle memory {uuid4().hex[:8]}",
            summary=summary,
            content=content,
            layer="semantic",
            source_kind="consolidation",
            trace_id=f"g39-compaction-{uuid4().hex}",
            tags=["lifecycle-compaction", "compressed"],
            payload={"compressed_memory_ids": memory_ids, "compression_summary": summary},
        )
        bytes_before = sum(_memory_bytes(record) for record in records)
        bytes_after = _memory_bytes(compressed)
        report = MemoryCompactionReport(
            compressed_memory_id=compressed.memory_id,
            source_memory_ids=memory_ids,
            records_before=len(records),
            records_after=1,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            benefit_ratio=bytes_before / max(bytes_after, 1),
            reference_chain_preserved=True,
        )
        for record in records:
            self._enhanced_service.update_management_state(
                record.memory_id,
                status="archived",
                visibility="hidden",
                superseded_by_memory_id=compressed.memory_id,
                management_note=f"G39 compressed into {compressed.memory_id}",
                operator=operator,
                reason="G39 compaction archived source memory while preserving reference chain.",
            )
            self._set_state(
                record.memory_id,
                lifecycle_tier=self._state_for(record).lifecycle_tier,
                status="archived",
                compressed_into_id=compressed.memory_id,
                last_action="compressed_source_archived",
            )
        self._enhanced_service.update_management_state(
            compressed.memory_id,
            trust_level="tentative",
            management_note=f"G39 compaction report {report.report_id}",
            operator=operator,
            reason="G39 compressed memory created with source reference chain.",
        )
        self._set_state(compressed.memory_id, lifecycle_tier="warm", status="active", last_action="compressed_memory_created")
        with self._lock:
            self._compactions.append(report)
        return report

    def rewarm_memory(self, memory_id: str, *, operator: str = "memory_lifecycle", reason: str = "manual rewarm") -> MemoryLifecycleState:
        record = self._required_record(memory_id)
        state = self._state_for(record)
        if record.status in BLOCKED_REWARM_STATUSES or record.trust_level in BLOCKED_REWARM_TRUST_LEVELS or state.rewarm_blocked:
            raise ValueError(f"memory {memory_id} is blocked from rewarm")
        updated = self._enhanced_service.update_management_state(
            memory_id,
            status="active",
            visibility="internal",
            management_note=f"G39 rewarm: {reason}",
            operator=operator,
            reason=reason,
        )
        return self._set_state(
            memory_id,
            lifecycle_tier="hot",
            status=updated.status,
            compressed_into_id=state.compressed_into_id,
            last_action="rewarmed",
        )

    def mark_contaminated(self, memory_id: str, *, reason: str, operator: str = "memory_lifecycle") -> MemoryLifecycleState:
        self._required_record(memory_id)
        self._enhanced_service.update_management_state(
            memory_id,
            status="rejected",
            visibility="hidden",
            trust_level="contaminated",
            correction_note=reason,
            operator=operator,
            reason=reason,
        )
        with self._lock:
            self._contaminated_memory_ids.add(memory_id)
        return self._set_state(memory_id, status="rejected", rewarm_blocked=True, last_action="contaminated")

    def restore_compressed_chain(self, compressed_memory_id: str, *, operator: str = "memory_lifecycle") -> list[MemoryLifecycleState]:
        compressed = self._required_record(compressed_memory_id)
        source_ids = list(compressed.payload.get("compressed_memory_ids", []))
        restored: list[MemoryLifecycleState] = []
        for memory_id in source_ids:
            try:
                restored.append(self.rewarm_memory(memory_id, operator=operator, reason=f"restore chain from {compressed_memory_id}"))
            except ValueError:
                continue
        return restored

    def list_states(self) -> list[MemoryLifecycleState]:
        with self._lock:
            return list(self._states.values())

    def list_cycles(self) -> list[MemoryLifecycleCycleReport]:
        with self._lock:
            return list(self._cycles)

    def list_compaction_reports(self) -> list[MemoryCompactionReport]:
        with self._lock:
            return list(self._compactions)

    def _required_record(self, memory_id: str):
        record = self._enhanced_service.get_managed_record(memory_id)
        if record is None:
            raise KeyError(memory_id)
        return record

    def _state_for(self, record: Any) -> MemoryLifecycleState:
        with self._lock:
            state = self._states.get(record.memory_id)
            if state is None:
                state = MemoryLifecycleState(
                    memory_id=record.memory_id,
                    lifecycle_tier=getattr(record, "memory_tier", "hot") or "hot",
                    status=getattr(record, "status", "active") or "active",
                    rewarm_blocked=record.memory_id in self._contaminated_memory_ids,
                )
                self._states[record.memory_id] = state
            return state

    def _set_state(self, memory_id: str, **updates: Any) -> MemoryLifecycleState:
        with self._lock:
            current = self._states.get(memory_id) or MemoryLifecycleState(memory_id=memory_id)
            updated = current.model_copy(update={**updates, "updated_at": _utc_now()})
            self._states[memory_id] = updated
            return updated

    def _target_tier(self, record: EnhancedMemoryRecord, now: datetime) -> str:
        age = _age_days(record.created_at, now)
        if age > self.policy.warm_max_days:
            return "cold"
        if age > self.policy.hot_max_days:
            return "warm"
        return "hot"

    def _should_archive(self, record: Any, target_tier: str, usage: dict[str, int]) -> bool:
        if record.status in {"archived", "rejected"} or record.visibility == "hidden":
            return False
        if record.payload.get("lifecycle_value") == "low":
            return True
        if record.confidence_score < self.policy.low_value_confidence:
            return True
        projected = usage[target_tier] + _memory_bytes(record)
        budget = {
            "hot": self.policy.hot_budget_bytes,
            "warm": self.policy.warm_budget_bytes,
            "cold": self.policy.cold_budget_bytes,
        }[target_tier]
        return projected > budget and record.affect_intensity < 0.5

    def _promotion_candidates(self, records: list[Any], now: datetime) -> list[MemoryPromotionCandidate]:
        groups: dict[str, list[Any]] = defaultdict(list)
        for record in records:
            pattern_key = str(record.payload.get("pattern_key") or next((tag for tag in record.tags if tag.startswith("pattern:")), ""))
            if not pattern_key:
                continue
            if record.status in {"archived", "rejected"} or record.visibility == "hidden":
                continue
            groups[pattern_key].append(record)

        candidates: list[MemoryPromotionCandidate] = []
        for pattern_key, group in groups.items():
            recent = [record for record in group if _age_days(record.created_at, now) <= self.policy.hot_max_days]
            windows = {
                int(_age_days(record.created_at, now) // max(self.policy.hot_max_days, 1))
                for record in group
            }
            if len(recent) >= self.policy.experience_threshold:
                candidates.append(
                    MemoryPromotionCandidate(
                        candidate_type="experience",
                        pattern_key=pattern_key,
                        source_memory_ids=[record.memory_id for record in recent],
                        occurrence_count=len(recent),
                        window_count=max(1, len(windows)),
                    )
                )
            if len(group) >= self.policy.strategy_patch_threshold and len(windows) >= self.policy.strategy_patch_min_windows:
                candidates.append(
                    MemoryPromotionCandidate(
                        candidate_type="strategy_patch",
                        pattern_key=pattern_key,
                        source_memory_ids=[record.memory_id for record in group],
                        occurrence_count=len(group),
                        window_count=len(windows),
                    )
                )
        return candidates

    def _can_recall(self, status: str, visibility: str, trust_level: str, state: MemoryLifecycleState) -> bool:
        if status in {"archived", "rejected"} or visibility == "hidden":
            return False
        if trust_level in BLOCKED_REWARM_TRUST_LEVELS:
            return False
        if state.rewarm_blocked or state.status in {"archived", "rejected"}:
            return False
        return True


def build_memory_lifecycle_governance(
    enhanced_service: EnhancedMemoryService,
    *,
    policy: MemoryLifecyclePolicy | None = None,
) -> MemoryLifecycleGovernance:
    return MemoryLifecycleGovernance(enhanced_service, policy=policy)
