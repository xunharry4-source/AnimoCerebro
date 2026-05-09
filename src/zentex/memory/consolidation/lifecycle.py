from __future__ import annotations

"""
Memory lifecycle manager.

职责:
  - 基于时间衰减、访问频率、情感强度的自动分层迁移（Hot → Warm → Cold）。
  - TTL 到期检测与过期记录打标（不物理删除；交给 consolidation 引擎决策）。
  - 三类遗忘策略：干扰式（相似记忆竞争）、效用驱动（长期未访问）、情感衰减（低情感中性记忆）。
  - 访问记录与热度统计（访问频次、最近访问时间、检索命中率）。
  - 巩固质量度量（压缩比、噪声删减率、模式发现量）。

不负责:
  - 记忆内容的语义判断（无 LLM 调用）。
  - 物理删除记录（只修改 governance 状态，由 consolidation 执行最终操作）。
  - 与 Kuzu 图数据库的交互（由 kuzu_backend.py 负责）。
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta
UTC = timezone.utc
from typing import NamedTuple, Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOT_MAX_DAYS = 14
_WARM_MAX_DAYS = 180
_DEFAULT_NEUTRAL_DECAY_DAYS = 60   # Neutral memories eligible for forgetting after N days
_DEFAULT_UTILITY_THRESHOLD_DAYS = 30  # Mark for forgetting if unused for N days
_DEFAULT_INTERFERENCE_SIMILARITY_FLOOR = 0.85  # Content hash similarity proxy


# ---------------------------------------------------------------------------
# Access record
# ---------------------------------------------------------------------------

class AccessRecord(NamedTuple):
    """Lightweight record of a single memory access event."""

    memory_id: str
    accessed_at: datetime
    query: str  # The query that triggered this access (empty = direct lookup)
    hit_score: float  # Retrieval score [0, 1]


# ---------------------------------------------------------------------------
# Decay config
# ---------------------------------------------------------------------------

class MemoryDecayConfig(BaseModel):
    """Configures how memories lose relevance over time."""

    model_config = ConfigDict(extra="forbid")

    hot_to_warm_days: int = Field(default=_HOT_MAX_DAYS, ge=1)
    warm_to_cold_days: int = Field(default=_WARM_MAX_DAYS, ge=1)

    # Neutral-affect records with zero accesses older than this → forgetting candidate.
    neutral_decay_days: int = Field(default=_DEFAULT_NEUTRAL_DECAY_DAYS, ge=1)

    # Any record not accessed in this many days → utility-forgetting candidate.
    utility_stale_days: int = Field(default=_DEFAULT_UTILITY_THRESHOLD_DAYS, ge=1)

    # Records with affect_intensity below this are treated as low-affect.
    low_affect_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Lifecycle event
# ---------------------------------------------------------------------------

class LifecycleEvent(BaseModel):
    """One lifecycle action emitted by the manager."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str
    action: str  # "promote_to_warm" | "demote_to_cold" | "mark_ttl_expired"
                  # | "forgetting_candidate_neutral" | "forgetting_candidate_utility"
                  # | "forgetting_candidate_interference"
    reason: str
    old_tier: str
    new_tier: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Consolidation quality metrics
# ---------------------------------------------------------------------------

class ConsolidationQualityReport(BaseModel):
    """Outcome metrics from a consolidation cycle (for observability / dashboard)."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    started_at: datetime
    finished_at: datetime

    # Compression
    records_before: int = 0
    records_after: int = 0
    compression_ratio: float = 0.0  # records_before / records_after (> 1 = good)

    # Noise reduction
    low_value_pruned: int = 0
    noise_reduction_pct: float = 0.0  # pruned / before * 100

    # Retrieval quality (filled in by benchmarking harness, not the engine itself)
    retrieval_improvement: float = 0.0  # Average score delta before/after consolidation

    # Pattern discovery
    new_patterns_found: int = 0
    false_positive_rate: float = 0.0  # Incorrectly promoted memories (filled by review)

    def compute_derived(self) -> "ConsolidationQualityReport":
        """Recompute compression_ratio and noise_reduction_pct from raw counts."""
        ratio = self.records_before / max(self.records_after, 1)
        noise_pct = (self.low_value_pruned / max(self.records_before, 1)) * 100.0
        return self.model_copy(update={"compression_ratio": ratio, "noise_reduction_pct": noise_pct})


# ---------------------------------------------------------------------------
# Memory access tracker
# ---------------------------------------------------------------------------

class MemoryAccessTracker:
    """
    Tracks access frequency and recency for all memory records.

    Thread-safe.  Backed by in-memory structures only; periodically flushed to disk
    by the lifecycle manager.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # memory_id → list[AccessRecord]  (bounded to last 1 000 per record)
        self._accesses: dict[str, list[AccessRecord]] = defaultdict(list)
        self._ACCESS_WINDOW = 1_000

    def record(self, memory_id: str, *, query: str = "", hit_score: float = 0.0) -> None:
        with self._lock:
            lst = self._accesses[memory_id]
            lst.append(AccessRecord(
                memory_id=memory_id,
                accessed_at=datetime.now(UTC),
                query=query,
                hit_score=hit_score,
            ))
            if len(lst) > self._ACCESS_WINDOW:
                # Keep newest window.
                self._accesses[memory_id] = lst[-self._ACCESS_WINDOW:]

    def access_count(self, memory_id: str) -> int:
        with self._lock:
            return len(self._accesses.get(memory_id, []))

    def last_accessed(self, memory_id: str) -> Optional[datetime]:
        with self._lock:
            lst = self._accesses.get(memory_id)
            return lst[-1].accessed_at if lst else None

    def days_since_access(self, memory_id: str) -> float:
        last = self.last_accessed(memory_id)
        if last is None:
            return float("inf")
        return (datetime.now(UTC) - last).total_seconds() / 86_400.0

    def hot_memories(self, *, top_n: int = 50) -> list[tuple[str, int]]:
        """Return top_n most-accessed memory IDs with their counts."""
        with self._lock:
            counts = [(mid, len(lst)) for mid, lst in self._accesses.items()]
        return sorted(counts, key=lambda x: x[1], reverse=True)[:top_n]

    def analytics_snapshot(self) -> dict:
        with self._lock:
            total_memories = len(self._accesses)
            total_accesses = sum(len(v) for v in self._accesses.values())
        return {
            "tracked_memories": total_memories,
            "total_access_events": total_accesses,
            "avg_accesses_per_memory": total_accesses / max(total_memories, 1),
        }


# ---------------------------------------------------------------------------
# Lifecycle manager
# ---------------------------------------------------------------------------

class MemoryLifecycleManager:
    """
    Evaluates memory records against lifecycle rules and emits LifecycleEvents.

    这个类自身不修改任何存储——它只产生"应该做什么"的事件列表，由调用方
    （EnhancedMemoryService 或 ConsolidationEngine）决定是否执行。
    这样可以避免生命周期管理代码绕过 G38 隔离门和审计链。
    """

    def __init__(
        self,
        *,
        decay_config: Optional[MemoryDecayConfig] = None,
        access_tracker: Optional[MemoryAccessTracker] = None,
    ) -> None:
        self.config = decay_config or MemoryDecayConfig()
        self.tracker = access_tracker or MemoryAccessTracker()

    # ── tier transition ──────────────────────────────────────────────────

    def evaluate_tier_transition(
        self,
        memory_id: str,
        current_tier: str,
        created_at: datetime,
    ) -> Optional[LifecycleEvent]:
        """
        Return a LifecycleEvent if the record should change tier, else None.

        Promotion / demotion logic:
          HOT  → WARM  if age > hot_to_warm_days
          WARM → COLD  if age > warm_to_cold_days
        """
        age_days = (datetime.now(UTC) - created_at).total_seconds() / 86_400.0

        if current_tier == "hot" and age_days > self.config.hot_to_warm_days:
            return LifecycleEvent(
                memory_id=memory_id,
                action="promote_to_warm",
                reason=f"Age {age_days:.1f}d > hot_max {self.config.hot_to_warm_days}d",
                old_tier="hot",
                new_tier="warm",
            )
        if current_tier == "warm" and age_days > self.config.warm_to_cold_days:
            return LifecycleEvent(
                memory_id=memory_id,
                action="demote_to_cold",
                reason=f"Age {age_days:.1f}d > warm_max {self.config.warm_to_cold_days}d",
                old_tier="warm",
                new_tier="cold",
            )
        return None

    # ── TTL check ────────────────────────────────────────────────────────

    def evaluate_ttl(
        self,
        memory_id: str,
        current_tier: str,
        created_at: datetime,
        ttl_days: Optional[int] = None,
    ) -> Optional[LifecycleEvent]:
        """Return a LifecycleEvent if an explicit TTL has expired."""
        if ttl_days is None:
            return None
        expiry = created_at + timedelta(days=ttl_days)
        if datetime.now(UTC) >= expiry:
            return LifecycleEvent(
                memory_id=memory_id,
                action="mark_ttl_expired",
                reason=f"TTL {ttl_days}d expired at {expiry.isoformat()}",
                old_tier=current_tier,
                new_tier=current_tier,
            )
        return None

    # ── forgetting strategies ────────────────────────────────────────────

    def evaluate_forgetting(
        self,
        memory_id: str,
        current_tier: str,
        emotional_valence: str,
        affect_intensity: float,
        created_at: datetime,
    ) -> Optional[LifecycleEvent]:
        """
        Evaluate whether a record is eligible for forgetting.

        Strategy priority:
          1. Utility-driven — never accessed AND old.
          2. Neutral-decay  — low-affect neutral record AND old.

        Returns None if the record should be retained.
        The caller decides whether to apply forgetting.
        """
        age_days = (datetime.now(UTC) - created_at).total_seconds() / 86_400.0
        days_idle = self.tracker.days_since_access(memory_id)

        # Strategy 1: Utility-driven — not accessed in N days.
        if days_idle > self.config.utility_stale_days and age_days > self.config.utility_stale_days:
            return LifecycleEvent(
                memory_id=memory_id,
                action="forgetting_candidate_utility",
                reason=(
                    f"Not accessed for {days_idle:.0f}d "
                    f"(threshold {self.config.utility_stale_days}d)"
                ),
                old_tier=current_tier,
                new_tier=current_tier,
            )

        # Strategy 2: Neutral decay — low-affect + old + never accessed.
        is_low_affect = affect_intensity < self.config.low_affect_threshold
        is_neutral = emotional_valence in ("neutral",)
        if (
            is_low_affect
            and is_neutral
            and age_days > self.config.neutral_decay_days
            and self.tracker.access_count(memory_id) == 0
        ):
            return LifecycleEvent(
                memory_id=memory_id,
                action="forgetting_candidate_neutral",
                reason=(
                    f"Neutral low-affect (intensity={affect_intensity:.2f}) "
                    f"unaccessed for {age_days:.0f}d"
                ),
                old_tier=current_tier,
                new_tier=current_tier,
            )

        return None

    def evaluate_interference_forgetting(
        self,
        memory_id: str,
        current_tier: str,
        duplicate_count: int,
    ) -> Optional[LifecycleEvent]:
        """
        Interference-based forgetting: a record with many near-duplicates should lose.

        The duplicate_count is supplied by the caller (e.g. from the conflict detection
        pass).  If a record has >= 3 duplicates it is a forgetting candidate.
        """
        if duplicate_count >= 3:
            return LifecycleEvent(
                memory_id=memory_id,
                action="forgetting_candidate_interference",
                reason=f"Superseded by {duplicate_count} near-duplicates",
                old_tier=current_tier,
                new_tier=current_tier,
            )
        return None

    # ── batch scan ───────────────────────────────────────────────────────

    def scan(
        self,
        records: list[dict],
    ) -> list[LifecycleEvent]:
        """
        Run all lifecycle checks over a list of record dicts and return events.

        Expected dict keys: memory_id, memory_tier, emotional_valence, affect_intensity,
        created_at (ISO string), ttl_days (optional int), contradiction_count (optional int).
        """
        events: list[LifecycleEvent] = []
        for rec in records:
            mid = rec.get("memory_id", "")
            tier = rec.get("memory_tier", "hot")
            valence = rec.get("emotional_valence", "neutral")
            intensity = float(rec.get("affect_intensity", 0.0))
            created_raw = rec.get("created_at")
            try:
                created_at = datetime.fromisoformat(str(created_raw)).replace(tzinfo=UTC) if created_raw else datetime.now(UTC)
            except ValueError:
                created_at = datetime.now(UTC)

            # Tier transitions.
            ev = self.evaluate_tier_transition(mid, tier, created_at)
            if ev:
                events.append(ev)

            # TTL.
            ttl = rec.get("ttl_days")
            ev = self.evaluate_ttl(mid, tier, created_at, ttl_days=int(ttl) if ttl else None)
            if ev:
                events.append(ev)

            # Forgetting.
            ev = self.evaluate_forgetting(mid, tier, valence, intensity, created_at)
            if ev:
                events.append(ev)

            # Interference.
            dups = int(rec.get("contradiction_count", 0))
            ev = self.evaluate_interference_forgetting(mid, tier, dups)
            if ev:
                events.append(ev)

        return events
