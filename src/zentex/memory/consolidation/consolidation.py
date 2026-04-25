from __future__ import annotations

"""
Sleep-like consolidation engine / 睡眠式巩固与遗忘机制。

Why:
- 长期运行的外部大脑不能把所有反思记录、待办和假设无限堆积。
- B8 负责在离线路径中提炼高复用模式、清理低价值噪音，并把巩固结果写回
  记忆治理状态。
- 这是高成本后台任务，必须卸载到 Worker/队列执行，绝不能阻塞在线热路径。
"""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple, Union
from zentex.common.locking import get_lock_for_resource
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from zentex.foundation.specs.model_provider import (
    ModelProviderCallerContext,
    ModelProviderRateLimitError,
    ModelProviderSpec,
)
from zentex.llm.service import LLMService
from zentex.kernel import BrainTranscriptEntryType, BrainTranscriptStore
from zentex.plugins.contracts import PluginLifecycleStatus
from zentex.memory.consolidation.llm_prompt import build_consolidation_summary_prompt

try:
    from zentex.common.plugin_registry import PluginNotBoundError
except ModuleNotFoundError:  # pragma: no cover
    class PluginNotBoundError(RuntimeError):
        pass


logger = logging.getLogger(__name__)


class StaleWriteError(RuntimeError):
    """Raised when a background consolidation result targets stale memory state."""


class ConsolidationTaskRejectedError(RuntimeError):
    """Raised when a consolidation task cannot acquire the required brain-scope lease."""


class MemoryPromotionCandidate(BaseModel):
    """Candidate memory fragment that may be promoted into durable knowledge."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    source_ref: str = Field(min_length=1)
    candidate_type: Literal[
        "lesson",
        "constraint",
        "pattern",
        "agenda_rule",
        "self_model_update",
    ]
    stability_score: float = Field(ge=0.0, le=1.0)
    reuse_value: float = Field(ge=0.0, le=1.0)
    promotion_reason: str = Field(min_length=1)
    status: Literal["candidate", "quarantined", "promoted", "rejected"] = "candidate"


class ForgettableNoiseRule(BaseModel):
    """Rule declaring when low-value memory fragments may be safely forgotten."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    noise_kind: Literal[
        "stale_agenda",
        "low_value_reflection",
        "duplicate_case",
        "expired_assumption",
    ]
    age_threshold_seconds: int = Field(ge=0)
    reuse_threshold: float = Field(ge=0.0, le=1.0)
    confidence_threshold: float = Field(ge=0.0, le=1.0)


class PatternStabilityScore(BaseModel):
    """Structured stability signal for a reusable pattern found during consolidation."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(min_length=1)
    frequency: int = Field(ge=0)
    time_span_seconds: int = Field(ge=0)
    cross_context_reuse: float = Field(ge=0.0, le=1.0)
    conflict_count: int = Field(ge=0)
    failure_count: int = Field(ge=0, default=0) # Convergence Rule 4
    stability_score: float = Field(ge=0.0, le=1.0)


class ConsolidationPluginOutput(BaseModel):
    """Normalized output contract produced by a consolidation analysis plugin."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str = Field(min_length=1)
    promotion_candidates: List[MemoryPromotionCandidate] = Field(default_factory=list)
    pruned_refs: List[str] = Field(default_factory=list)
    compressed_refs: List[str] = Field(default_factory=list)
    pattern_scores: List[PatternStabilityScore] = Field(default_factory=list)


class ConsolidationCycle(BaseModel):
    """A full offline consolidation cycle and its resulting memory governance actions."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    input_refs: List[str] = Field(default_factory=list)
    promoted_refs: List[str] = Field(default_factory=list)
    pruned_refs: List[str] = Field(default_factory=list)
    compressed_refs: List[str] = Field(default_factory=list)
    summary: str = ""
    trigger_stage: Literal[
        "sleep_phase",
        "reflection_postprocess",
        "memory_governance_review",
        "agenda_cleanup",
    ] = "sleep_phase"
    brain_scope: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    snapshot_version: int = Field(ge=0)
    status: Literal["queued", "completed", "failed", "stale_rejected"] = "queued"
    promotion_candidates: List[MemoryPromotionCandidate] = Field(default_factory=list)
    pattern_scores: List[PatternStabilityScore] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    backoff_seconds: Optional[int] = Field(default=None, ge=0)


class ConsolidationTaskRequest(BaseModel):
    """Background task envelope for one consolidation run."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(default_factory=lambda: str(uuid4()))
    brain_scope: str = Field(min_length=1)
    lease_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str = Field(min_length=1)
    snapshot_version: int = Field(ge=0)
    trigger_stage: Literal[
        "sleep_phase",
        "reflection_postprocess",
        "memory_governance_review",
        "agenda_cleanup",
    ]
    input_memory_refs: List[Dict[str, Any]] = Field(default_factory=list)
    noise_rules: List[ForgettableNoiseRule] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


class ConsolidationTaskHandle(BaseModel):
    """Visible handle returned to the caller when a background task is accepted."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    lease_id: str
    idempotency_key: str
    snapshot_version: int
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsolidationQueue(Protocol):
    """Queue interface for background consolidation execution."""

    def submit(
        self,
        fn: Any,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[ConsolidationCycle]:
        """Submit a background consolidation task."""


class ThreadPoolConsolidationQueue:
    """Local worker adapter used in development and tests."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="memory-consolidation",
        )

    def submit(
        self,
        fn: Any,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[ConsolidationCycle]:
        return self._executor.submit(fn, *args, **kwargs)


class ConsolidationAnalysisPlugin(Protocol):
    """Protocol implemented by active cognitive plugins that analyze memory for consolidation."""

    plugin_id: str
    status: PluginLifecycleStatus
    behavior_key: str
    supports_multi_active: bool

    def analyze_memory(
        self,
        *,
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        """Return structured consolidation hints without mutating external state."""


class ReflectionClusteringPlugin:
    """Concrete analyzer for topic-based reflection clustering (Sub-function 59 gap)."""

    def __init__(self, plugin_id: str = "reflection_clusterer") -> None:
        self.plugin_id = plugin_id
        self.lifecycle_status=PluginLifecycleStatus.ACTIVE
        self.behavior_key = "memory_consolidation"
        self.supports_multi_active = True

    def analyze_memory(
        self,
        *,
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        input_refs = context.get("input_memory_refs", [])
        import time

        from zentex.memory.consolidation.stats_pipeline import (
            compute_pattern_scores,
            refs_to_dataframe,
        )

        promotion_candidates = []
        pruned_refs = []
        pattern_scores: list[PatternStabilityScore] = []
        
        # Simple heuristic: cluster by topic tag and outcome type
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        for ref in input_refs:
            topic = ref.get("topic") or "general"
            clusters.setdefault(topic, []).append(ref)
            
        for topic, refs in clusters.items():
            if len(refs) >= 3:
                cluster_scores = compute_pattern_scores(refs_to_dataframe(refs, now_ts=time.time()))
                best_score = cluster_scores[0] if cluster_scores else None
                stability_score = best_score.stability_score if best_score is not None else 0.0
                reuse_value = best_score.cross_context_reuse if best_score is not None else 0.0
                pattern_scores.extend(cluster_scores)
                promotion_candidates.append(
                    MemoryPromotionCandidate(
                        source_ref=f"cluster:{topic}",
                        candidate_type="pattern",
                        stability_score=stability_score,
                        reuse_value=reuse_value,
                        promotion_reason=f"Topic '{topic}' appears in {len(refs)} reflections; stable pattern detected.",
                    )
                )
        
        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            promotion_candidates=promotion_candidates,
            pruned_refs=pruned_refs,
            pattern_scores=pattern_scores,
        )


class ConsolidationEngine:
    """
    Offline memory consolidation engine with worker offloading and optimistic locking.

    Responsibilities:
    - dispatch expensive consolidation work to background workers
    - merge outputs from multiple active consolidation plugins
    - use live model inference to summarize and score reusable memory
    - reject stale writes when shared memory changed during consolidation
    """

    def __init__(
        self,
        *,
        llm_service: Optional[LLMService] = None,
        model_provider: Optional[ModelProviderSpec] = None,
        model_provider_key: Optional[str] = None,
        analysis_plugins: List[ConsolidationAnalysisPlugin],
        transcript_store: BrainTranscriptStore,
        brain_scope: str,
        queue: Optional[ConsolidationQueue] = None,
        enhanced_archive_service: Any = None,
    ) -> None:
        """
        Initialize the consolidation engine.

        Args:
            llm_service: Unified LLM service entrypoint for semantic summarization.
            model_provider: Legacy fallback provider.
            analysis_plugins: Active multi-plugin analyzers for clustering/pruning hints.
            transcript_store: Append-only audit stream for cycle success/failure records.
            brain_scope: Shared state scope used for lease ownership and stale-write checks.
            queue: Optional background queue adapter. Defaults to a local thread-pool queue.
        """
        self._llm_service = llm_service
        self._model_provider: Optional[ModelProviderSpec] = model_provider
        self._model_provider_key = model_provider_key
        self._analysis_plugins: List[ConsolidationAnalysisPlugin] = list(analysis_plugins)
        self._transcript_store: BrainTranscriptStore = transcript_store
        self._brain_scope: str = brain_scope
        self._queue: ConsolidationQueue = queue or ThreadPoolConsolidationQueue()
        self._enhanced_archive_service = enhanced_archive_service
        self._lock = get_lock_for_resource(f"consolidation:{brain_scope}")
        self._cycles_by_id: Dict[str, ConsolidationCycle] = {}
        self._snapshot_version: int = 0
        self._memory_versions: Dict[str, int] = {}
        self._tombstone_state: Dict[str, bool] = {}
        self._active_lease_by_scope: Dict[str, str] = {}
        self._rate_limit_failures: int = 0
        self._heartbeat_running: bool = False
        
        # Explicit Tiered Storage Budgets (Sub-function 59.5 Gap)
        self.HOT_TIER_LIMIT = 2 * 1024 * 1024 * 1024 # 2GB (14 days)
        self.WARM_TIER_LIMIT = 10 * 1024 * 1024 * 1024 # 10GB (180 days)
        self.COLD_TIER_LIMIT = 50 * 1024 * 1024 * 1024 # 50GB
        
        self._last_cycle_timestamp: Optional[datetime] = None
        
        # Sub-function 59.5 - Storage Budget Monitoring (Priority 3)
        self.storage_usage_stats: Dict[str, float] = {"hot": 0.0, "warm": 0.0, "cold": 0.0}

    @property
    def brain_scope(self) -> str:
        """Return the shared-state scope guarded by this engine."""
        return self._brain_scope

    @property
    def snapshot_version(self) -> int:
        """Expose the current memory-governance snapshot version."""
        with self._lock:
            return self._snapshot_version

    def bump_snapshot_version(self) -> int:
        """Advance the memory snapshot version after an external state mutation."""
        with self._lock:
            self._snapshot_version += 1
            return self._snapshot_version

    def seed_memory_snapshot(
        self,
        *,
        ref_versions: Dict[str, int],
        tombstone_state: Dict[str, Optional[bool]] = None,
        snapshot_version: int = 0,
    ) -> None:
        """Seed in-memory version/tombstone state for development or isolated tests."""
        with self._lock:
            self._memory_versions = dict(ref_versions)
            self._tombstone_state = dict(tombstone_state or {})
            self._snapshot_version = snapshot_version

    def mark_memory_ref_updated(self, ref_id: str) -> None:
        """Simulate a hot-path mutation so stale background results can be rejected."""
        with self._lock:
            self._memory_versions[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            self._snapshot_version += 1

    def seed_cycle(self, cycle: ConsolidationCycle) -> None:
        """Inject a completed cycle for development-mode UI inspection."""
        with self._lock:
            self._cycles_by_id[cycle.cycle_id] = cycle

    def list_cycles(
        self,
        *,
        cycle_id: Optional[str] = None,
        started_after: Optional[datetime] = None,
        started_before: Optional[datetime] = None,
    ) -> List[ConsolidationCycle]:
        """Return cycle history filtered by id or time range."""
        with self._lock:
            cycles: List[ConsolidationCycle] = list(self._cycles_by_id.values())
        if cycle_id is not None:
            cycles = [cycle for cycle in cycles if cycle.cycle_id == cycle_id]
        if started_after is not None:
            cycles = [cycle for cycle in cycles if cycle.started_at >= started_after]
        if started_before is not None:
            cycles = [cycle for cycle in cycles if cycle.started_at <= started_before]
        return sorted(cycles, key=lambda cycle: cycle.started_at, reverse=True)

    def submit_cycle(
        self,
        *,
        trigger_stage: Literal[
            "sleep_phase",
            "reflection_postprocess",
            "memory_governance_review",
            "agenda_cleanup",
        ],
        input_memory_refs: List[Dict[str, Any]],
        noise_rules: List[ForgettableNoiseRule],
        context: Dict[str, Any],
        idempotency_key: str,
        snapshot_version: int,
    ) -> Tuple[ConsolidationTaskHandle, Future[ConsolidationCycle]]:
        """
        Submit a consolidation cycle to the background queue.

        Raises:
            ConsolidationTaskRejectedError: Another worker already owns this brain_scope lease.
        """
        task_request = ConsolidationTaskRequest(
            brain_scope=self._brain_scope,
            idempotency_key=idempotency_key,
            snapshot_version=snapshot_version,
            trigger_stage=trigger_stage,
            input_memory_refs=input_memory_refs,
            noise_rules=noise_rules,
            context=context,
        )
        self._acquire_scope_lease(task_request)
        handle = ConsolidationTaskHandle(
            cycle_id=task_request.cycle_id,
            lease_id=task_request.lease_id,
            idempotency_key=idempotency_key,
            snapshot_version=snapshot_version,
        )
        queued_cycle = ConsolidationCycle(
            cycle_id=task_request.cycle_id,
            started_at=handle.queued_at,
            input_refs=[self._extract_ref_id(item) for item in input_memory_refs],
            promoted_refs=[],
            pruned_refs=[],
            compressed_refs=[],
            summary="",
            trigger_stage=trigger_stage,
            brain_scope=self._brain_scope,
            lease_id=task_request.lease_id,
            idempotency_key=idempotency_key,
            snapshot_version=snapshot_version,
            status="queued",
        )
        with self._lock:
            self._cycles_by_id[queued_cycle.cycle_id] = queued_cycle
        future = self._queue.submit(self._execute_cycle, task_request)
        return handle, future

    def submit_manual_trigger(self, operator: str = "web_console") -> "ConsolidationTaskHandle":
        """Convenience entry-point for ad-hoc / operator-initiated consolidation.

        All business decisions (trigger_stage, idempotency_key generation,
        snapshot_version capture, empty refs/rules) are owned HERE in the
        domain layer so that callers such as web_console routers remain
        parameter-free.

        Returns the task handle; the associated Future is discarded because
        manual triggers are fire-and-forget from the caller's perspective.
        """
        import uuid as _uuid

        handle, _future = self.submit_cycle(
            trigger_stage="sleep_phase",
            input_memory_refs=[],
            noise_rules=[],
            context={"operator": operator, "trigger": "manual"},
            idempotency_key=str(_uuid.uuid4()),
            snapshot_version=self.snapshot_version,
        )
        return handle

    def _execute_cycle(self, task_request: ConsolidationTaskRequest) -> ConsolidationCycle:
        """Run a consolidation cycle inside a worker thread and commit the result safely."""
        started_at = datetime.now(timezone.utc)
        captured_versions, captured_tombstones = self._capture_memory_state(
            task_request.input_memory_refs
        )
        try:
            active_plugins = self._resolve_active_analysis_plugins()
            plugin_outputs = self._run_plugins(
                active_plugins=active_plugins,
                context={
                    **task_request.context,
                    "input_memory_refs": task_request.input_memory_refs,
                    "trigger_stage": task_request.trigger_stage,
                },
                noise_rules=task_request.noise_rules,
            )
            cycle = self._synthesize_cycle_with_model(
                task_request=task_request,
                started_at=started_at,
                plugin_outputs=plugin_outputs,
            )
            committed_cycle = self._commit_cycle(
                cycle=cycle,
                captured_versions=captured_versions,
                captured_tombstones=captured_tombstones,
            )
            self._record_cycle_event(
                entry_type=BrainTranscriptEntryType.CONSOLIDATION_COMPLETED,
                cycle=committed_cycle,
                payload={
                    "status": committed_cycle.status,
                    "trigger_stage": committed_cycle.trigger_stage,
                    "summary": committed_cycle.summary,
                    "promoted_refs": committed_cycle.promoted_refs,
                    "pruned_refs": committed_cycle.pruned_refs,
                    "compressed_refs": committed_cycle.compressed_refs,
                },
            )
            with self._lock:
                self._rate_limit_failures = 0
            return committed_cycle
        except ModelProviderRateLimitError as exc:
            failed_cycle = self._build_failed_cycle(
                task_request=task_request,
                started_at=started_at,
                reason=str(exc),
                backoff_seconds=self._next_backoff_seconds(),
            )
            self._record_failed_cycle(failed_cycle)
            raise
        except Exception as exc:
            failed_cycle = self._build_failed_cycle(
                task_request=task_request,
                started_at=started_at,
                reason=str(exc),
                backoff_seconds=None,
            )
            self._record_failed_cycle(failed_cycle)
            raise
        finally:
            self._release_scope_lease(task_request)

    def _resolve_active_analysis_plugins(self) -> List[ConsolidationAnalysisPlugin]:
        """Resolve the active consolidation analysis plugins and enforce active-only access."""
        active_plugins = [
            plugin
            for plugin in self._analysis_plugins
            if getattr(plugin, "status", None) == PluginLifecycleStatus.ACTIVE
            and getattr(plugin, "behavior_key", "") == "memory_consolidation"
        ]
        if not active_plugins:
            raise PluginNotBoundError(
                "No active consolidation analysis plugin is bound to memory_consolidation."
            )
        return active_plugins

    def _run_plugins(
        self,
        *,
        active_plugins: List[ConsolidationAnalysisPlugin],
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> List[ConsolidationPluginOutput]:
        """Run active analysis plugins in parallel and collect their structured outputs."""
        max_workers = max(1, len(active_plugins))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="consolidation-plugins") as executor:
            futures = [
                executor.submit(
                    plugin.analyze_memory,
                    context=context,
                    noise_rules=noise_rules,
                )
                for plugin in active_plugins
            ]
            return [future.result() for future in futures]

    def _synthesize_cycle_with_model(
        self,
        *,
        task_request: ConsolidationTaskRequest,
        started_at: datetime,
        plugin_outputs: List[ConsolidationPluginOutput],
    ) -> ConsolidationCycle:
        """Use the active LLM provider to summarize reusable memory and compression value."""
        aggregate_candidates = [
            candidate
            for output in plugin_outputs
            for candidate in output.promotion_candidates
        ]
        aggregate_pattern_scores = [
            score
            for output in plugin_outputs
            for score in output.pattern_scores
        ]
        aggregate_pruned_refs = [
            ref
            for output in plugin_outputs
            for ref in output.pruned_refs
        ]
        aggregate_compressed_refs = [
            ref
            for output in plugin_outputs
            for ref in output.compressed_refs
        ]

        prompt = build_consolidation_summary_prompt()["prompt"]
        llm_context = self._translate_model_context(
            task_request=task_request,
            plugin_outputs=plugin_outputs,
        )
        caller_context = ModelProviderCallerContext(
            source_module="Offline memory consolidation engine",
            invocation_phase="extracting stable memory patterns and compression summary",
            question_driver_refs=["什么值得长期记住", "哪些内容可以安全遗忘", "哪些模式值得升格"],
            decision_id=task_request.cycle_id,
        )
        if self._llm_service is not None:
            response = self._llm_service.generate_json(
                prompt=prompt,
                context=llm_context,
                caller_context=caller_context,
                source_module=caller_context.source_module,
                invocation_phase=caller_context.invocation_phase,
                decision_id=caller_context.decision_id,
                model_provider=self._model_provider_key,
                metadata={"question_driver_refs": caller_context.question_driver_refs},
            ).output
        elif self._model_provider is not None:
            response = self._model_provider.generate_json(
                prompt=prompt,
                context=llm_context,
                caller_context=caller_context,
            )
        else:
            raise RuntimeError("LLM MANDATORY: missing llm_service and model_provider fallback")

        promoted_candidates = [
            MemoryPromotionCandidate.model_validate({**candidate, "status": "quarantined"})
            for candidate in list(response.get("promotion_candidates") or [])
        ]
        promoted_refs = [candidate.source_ref for candidate in promoted_candidates]
        compressed_refs = list(dict.fromkeys([
            *aggregate_compressed_refs,
            *[str(ref) for ref in list(response.get("compressed_refs") or [])],
        ]))
        # 为什么这里要统一做身份包保护：遗忘与压缩可以清理噪音，但绝不能越权
        # 触碰 identity_role_pack 这类主体连续性核心记忆。
        pruned_refs = [
            ref
            for ref in dict.fromkeys(aggregate_pruned_refs)
            if not self._is_protected_ref(ref)
        ]

        return ConsolidationCycle(
            cycle_id=task_request.cycle_id,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            input_refs=[self._extract_ref_id(item) for item in task_request.input_memory_refs],
            promoted_refs=promoted_refs,
            pruned_refs=pruned_refs,
            compressed_refs=compressed_refs,
            summary=str(response.get("summary") or ""),
            trigger_stage=task_request.trigger_stage,
            brain_scope=task_request.brain_scope,
            lease_id=task_request.lease_id,
            idempotency_key=task_request.idempotency_key,
            snapshot_version=task_request.snapshot_version,
            status="completed",
            promotion_candidates=[
                *aggregate_candidates,
                *promoted_candidates,
            ],
            pattern_scores=aggregate_pattern_scores,
        )

    def _commit_cycle(
        self,
        *,
        cycle: ConsolidationCycle,
        captured_versions: Dict[str, int],
        captured_tombstones: Dict[str, bool],
    ) -> ConsolidationCycle:
        """Commit a completed cycle only if the targeted memory snapshot is still current."""
        with self._lock:
            if cycle.snapshot_version != self._snapshot_version:
                stale_cycle = cycle.model_copy(update={"status": "stale_rejected"})
                self._cycles_by_id[stale_cycle.cycle_id] = stale_cycle
                raise StaleWriteError(
                    f"Stale consolidation write for brain_scope={self._brain_scope}: "
                    f"expected snapshot_version {self._snapshot_version}, got {cycle.snapshot_version}"
                )
            for ref_id, expected_version in captured_versions.items():
                current_version = self._memory_versions.get(ref_id, 0)
                current_tombstone = self._tombstone_state.get(ref_id, False)
                if current_version != expected_version or current_tombstone != captured_tombstones.get(ref_id, False):
                    stale_cycle = cycle.model_copy(update={"status": "stale_rejected"})
                    self._cycles_by_id[stale_cycle.cycle_id] = stale_cycle
                    raise StaleWriteError(
                        f"Stale consolidation write for ref {ref_id}: "
                        f"expected version {expected_version}, got {current_version}"
                    )

            # Stage updates to ensure either all apply or none
            version_updates: Dict[str, int] = {}
            tombstone_updates: Dict[str, bool] = {}

            for ref_id in cycle.promoted_refs:
                version_updates[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            for ref_id in cycle.compressed_refs:
                version_updates[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            for ref_id in cycle.pruned_refs:
                tombstone_updates[ref_id] = True
                version_updates[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            
            # ATOMIC APPLY
            self._memory_versions.update(version_updates)
            self._tombstone_state.update(tombstone_updates)
            self._snapshot_version += 1
            self._last_cycle_timestamp = datetime.now(timezone.utc)

            committed_cycle = cycle.model_copy(update={"snapshot_version": self._snapshot_version})
            self._cycles_by_id[committed_cycle.cycle_id] = committed_cycle

        # Persist governance snapshot outside the lock so a slow disk write
        # doesn't block other readers.  Best-effort: failure is logged but
        # never raises (in-memory state is already authoritative).
        self._persist_governance_snapshot()
        return committed_cycle

    def _persist_governance_snapshot(self) -> None:
        """Write the current in-memory governance state to disk (best-effort).

        Snapshot file: <app_data_dir>/memory/governance/<brain_scope>.json

        On restart, callers can reload this file to restore the last committed
        memory_versions, tombstone_state, and snapshot_version without
        re-running all historical consolidation cycles.

        This method never raises — disk failures are logged as warnings.
        """
        import json as _json
        from pathlib import Path as _Path
        from zentex.common.storage_paths import get_storage_paths

        try:
            with self._lock:
                snapshot = {
                    "brain_scope": self._brain_scope,
                    "snapshot_version": self._snapshot_version,
                    "memory_versions": dict(self._memory_versions),
                    "tombstone_state": dict(self._tombstone_state),
                    "persisted_at": datetime.now(timezone.utc).isoformat(),
                }

            gov_dir = _Path(get_storage_paths().app_data_dir) / "memory" / "governance"
            gov_dir.mkdir(parents=True, exist_ok=True)
            target = self.get_governance_snapshot_path()
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(target)  # atomic rename on POSIX; best-effort on Windows
        except Exception:
            logger.warning(
                "consolidation: failed to persist governance snapshot for brain_scope=%s",
                self._brain_scope,
                exc_info=True,
            )

    def get_governance_snapshot_path(self) -> Path:
        """Return the filesystem path used to persist the current governance snapshot."""
        from zentex.common.storage_paths import get_storage_paths

        gov_dir = Path(get_storage_paths().app_data_dir) / "memory" / "governance"
        gov_dir.mkdir(parents=True, exist_ok=True)
        safe_scope = re.sub(r"[^A-Za-z0-9._-]+", "_", self._brain_scope).strip("._-") or "default"
        return gov_dir / f"{safe_scope}.json"

    def _build_failed_cycle(
        self,
        *,
        task_request: ConsolidationTaskRequest,
        started_at: datetime,
        reason: str,
        backoff_seconds: Optional[int],
    ) -> ConsolidationCycle:
        """Construct a failed cycle record without pretending to have compressed memory."""
        return ConsolidationCycle(
            cycle_id=task_request.cycle_id,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            input_refs=[self._extract_ref_id(item) for item in task_request.input_memory_refs],
            promoted_refs=[],
            pruned_refs=[],
            compressed_refs=[],
            summary="",
            trigger_stage=task_request.trigger_stage,
            brain_scope=task_request.brain_scope,
            lease_id=task_request.lease_id,
            idempotency_key=task_request.idempotency_key,
            snapshot_version=task_request.snapshot_version,
            status="failed",
            promotion_candidates=[],
            pattern_scores=[],
            failure_reason=reason,
            backoff_seconds=backoff_seconds,
        )

    def _record_failed_cycle(self, cycle: ConsolidationCycle) -> None:
        """Persist a failed cycle and append a failure audit event."""
        with self._lock:
            self._cycles_by_id[cycle.cycle_id] = cycle
        self._record_cycle_event(
            entry_type=BrainTranscriptEntryType.CONSOLIDATION_FAILED,
            cycle=cycle,
            payload={
                "status": cycle.status,
                "trigger_stage": cycle.trigger_stage,
                "failure_reason": cycle.failure_reason,
                "backoff_seconds": cycle.backoff_seconds,
            },
        )

    def _record_cycle_event(
        self,
        *,
        entry_type: BrainTranscriptEntryType,
        cycle: ConsolidationCycle,
        payload: Dict[str, Any],
    ) -> None:
        """Write a cycle audit record into the append-only transcript stream."""
        self._transcript_store.write_entry(
            session_id=f"memory:{self._brain_scope}",
            turn_id=cycle.cycle_id,
            entry_type=entry_type,
            payload={
                "cycle_id": cycle.cycle_id,
                "brain_scope": cycle.brain_scope,
                "lease_id": cycle.lease_id,
                **payload,
            },
            source="memory.consolidation",
            trace_id=cycle.cycle_id,
        )

    def _acquire_scope_lease(self, task_request: ConsolidationTaskRequest) -> None:
        """Acquire an exclusive lease for the brain scope before background execution starts."""
        with self._lock:
            current_lease = self._active_lease_by_scope.get(task_request.brain_scope)
            if current_lease is not None:
                raise ConsolidationTaskRejectedError(
                    f"Consolidation lease already held for brain_scope={task_request.brain_scope}"
                )
            self._active_lease_by_scope[task_request.brain_scope] = task_request.lease_id

    def _release_scope_lease(self, task_request: ConsolidationTaskRequest) -> None:
        """Release the previously acquired exclusive lease."""
        with self._lock:
            if self._active_lease_by_scope.get(task_request.brain_scope) == task_request.lease_id:
                self._active_lease_by_scope.pop(task_request.brain_scope, None)

    def _capture_memory_state(
        self,
        input_memory_refs: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, int], Dict[str, bool]]:
        """Capture per-ref version/tombstone state before the worker begins heavy processing."""
        with self._lock:
            captured_versions = {
                self._extract_ref_id(item): self._memory_versions.get(self._extract_ref_id(item), 0)
                for item in input_memory_refs
            }
            captured_tombstones = {
                self._extract_ref_id(item): self._tombstone_state.get(self._extract_ref_id(item), False)
                for item in input_memory_refs
            }
        return captured_versions, captured_tombstones

    def _translate_model_context(
        self,
        *,
        task_request: ConsolidationTaskRequest,
        plugin_outputs: List[ConsolidationPluginOutput],
    ) -> Dict[str, Any]:
        """Translate internal memory records into model-readable natural-language context."""
        from zentex.memory.consolidation.stats_pipeline import (
            compute_tier_pressure,
            refs_to_dataframe,
        )

        tier_pressure = compute_tier_pressure(
            refs_to_dataframe(
                task_request.input_memory_refs,
                now_ts=datetime.now(timezone.utc).timestamp(),
            )
        )
        return {
            "trigger_stage": task_request.trigger_stage.replace("_", " "),
            "current_memory_state_version": task_request.snapshot_version,
            "deduplication_reference": task_request.idempotency_key,
            "memory_fragments": [
                {
                    "reference": self._extract_ref_id(ref),
                    "kind": str(ref.get("kind") or "memory fragment").replace("_", " "),
                    "description": str(ref.get("summary") or ref.get("text") or ref.get("title") or self._extract_ref_id(ref)),
                    "importance": ref.get("importance"),
                    "reuse_value": ref.get("reuse_value"),
                }
                for ref in task_request.input_memory_refs
            ],
            "plugin_findings": [output.model_dump(mode="json") for output in plugin_outputs],
            "noise_rules": [rule.model_dump(mode="json") for rule in task_request.noise_rules],
            "tier_pressure": tier_pressure,
        }

    def _next_backoff_seconds(self) -> int:
        """Return the next exponential backoff delay for rate-limited consolidation cycles."""
        with self._lock:
            self._rate_limit_failures += 1
            return min(30 * (2 ** (self._rate_limit_failures - 1)), 1800)

    def _extract_ref_id(self, item: Dict[str, Any]) -> str:
        """Extract the stable memory reference id from an input memory object."""
        return str(item.get("ref_id") or item.get("id") or "unknown-ref")

    def _trigger_consolidation_for_reason(self, reason: str) -> None:
        """Helper to submit a consolidation cycle for a specific resource reason."""
        self.submit_cycle(
            trigger_stage="memory_governance_review",
            input_memory_refs=[{"ref_id": k, "v": v} for k, v in list(self._memory_versions.items())[:100]],
            noise_rules=[],
            context={"trigger_reason": reason},
            idempotency_key=f"auto-{uuid4().hex[:8]}",
            snapshot_version=self.snapshot_version
        )

    def prune_stale_agenda(self, agenda_items: List[Any], rules: List[ForgettableNoiseRule]) -> List[str]:
        """Prune expired agenda items using DeferredRiskScore logic (Sub-function 59 gap).

        Items without a ``created_at_ts`` field are skipped conservatively —
        same policy as apply_forgetting_rules.
        """
        pruned_ids = []
        now = datetime.now(timezone.utc).timestamp()
        for item in agenda_items:
            if "created_at_ts" not in item:
                logger.debug(
                    "prune_stale_agenda: skipping item %s — missing created_at_ts",
                    item.get("item_id", "<unknown>"),
                )
                continue
            age = now - item["created_at_ts"]
            risk_score = item.get("deferred_risk_score", 0.5)
            
            for rule in rules:
                if rule.noise_kind == "stale_agenda":
                    if age > rule.age_threshold_seconds and risk_score < rule.reuse_threshold:
                        pruned_ids.append(item.get("item_id"))
                        break
        return pruned_ids

    def detect_stable_patterns(self, input_refs: List[Dict[str, Any]]) -> List[PatternStabilityScore]:
        """Detect patterns with historical failure tracking (Convergence Rule 4 gap)."""
        import time

        from zentex.memory.consolidation.stats_pipeline import (
            compute_pattern_scores,
            refs_to_dataframe,
        )

        return compute_pattern_scores(refs_to_dataframe(input_refs, now_ts=time.time()))

    def archive_cold(self, memory_ids: List[str]) -> bool:
        """Move memory references from warm/hot to cold storage (Priority 3)."""
        if self._enhanced_archive_service is None:
            raise RuntimeError(
                "Enhanced memory archive service is required for archive_cold; "
                "simulation-only success is forbidden."
            )

        archived_any = False
        for memory_id in memory_ids:
            try:
                self._enhanced_archive_service.archive_cold(
                    memory_id,
                    operator="consolidation_engine",
                )
                archived_any = True
                self.mark_memory_ref_updated(memory_id)
            except Exception as exc:
                # Forbidden: returning True here would pretend cold-archive succeeded
                # even though physical memory governance failed for part of the batch.
                logger.exception(
                    "Consolidation archive_cold failed for %s: %s",
                    memory_id,
                    exc,
                )
                return False

        return archived_any

    def check_and_trigger_automatic_consolidation(self) -> None:
        """Sub-function 59.4 — idle heartbeat + tiered storage pressure trigger.

        Rules (in priority order):
        1. Heartbeat idle: no cycle for >1 h → submit heartbeat_idle cycle and return.
           Idle cycle takes priority; we don't stack additional pressure cycles on the
           same pass to avoid submitting two competing leases simultaneously.
        2. Hot-tier pressure: usage_ratio > 85% → submit hot_tier_pressure cycle.
        3. Warm-tier pressure: usage_ratio > 85% → submit warm_tier_pressure cycle.
        """
        now = datetime.now(timezone.utc)

        # Rule 1 — heartbeat idle slot
        last_time = self._last_cycle_timestamp or datetime.fromtimestamp(0, timezone.utc)
        if (now - last_time).total_seconds() > 3600:
            try:
                self._trigger_consolidation_for_reason("heartbeat_idle")
            except ConsolidationTaskRejectedError:
                pass  # lease already held — skip this tick
            except Exception:
                logger.warning("Auto-consolidation heartbeat trigger failed", exc_info=True)
            # Update usage stats even when we skip pressure rules this pass
            self.storage_usage_stats["hot"] = self._calculate_tier_usage_ratio("hot")
            self.storage_usage_stats["warm"] = self._calculate_tier_usage_ratio("warm")
            return

        # Rules 2 & 3 — storage budget pressure
        hot_ratio = self._calculate_tier_usage_ratio("hot")
        self.storage_usage_stats["hot"] = hot_ratio
        if hot_ratio > 0.85:
            try:
                self._trigger_consolidation_for_reason("hot_tier_pressure")
            except ConsolidationTaskRejectedError:
                pass
            except Exception:
                logger.warning("Auto-consolidation hot-tier trigger failed", exc_info=True)
            return  # don't also trigger warm if hot already scheduled a cycle

        warm_ratio = self._calculate_tier_usage_ratio("warm")
        self.storage_usage_stats["warm"] = warm_ratio
        if warm_ratio > 0.85:
            try:
                self._trigger_consolidation_for_reason("warm_tier_pressure")
            except ConsolidationTaskRejectedError:
                pass
            except Exception:
                logger.warning("Auto-consolidation warm-tier trigger failed", exc_info=True)

    def _calculate_tier_usage_ratio(self, tier: str) -> float:
        """Return the fraction (0.0–1.0) of the budget consumed by this storage tier.

        Reads actual disk usage under the tier's storage path.  Falls back to 0.0
        (safe — no false pressure trigger) if the path is absent or unreadable.
        """
        import shutil
        from pathlib import Path as _Path
        from zentex.common.storage_paths import get_storage_paths

        tier_limit = getattr(self, f"{tier.upper()}_TIER_LIMIT", None)
        if not tier_limit:
            return 0.0

        tier_path_attr = f"{tier}_memory_dir"
        storage_paths = get_storage_paths()
        tier_dir = getattr(storage_paths, tier_path_attr, None)
        if tier_dir is None:
            # Tier directory not configured; treat as empty.
            return 0.0

        tier_path = _Path(tier_dir)
        if not tier_path.exists():
            return 0.0

        try:
            usage = shutil.disk_usage(tier_path)
            return min(1.0, usage.used / tier_limit)
        except Exception:
            logger.warning("Failed to measure disk usage for %s tier at %s", tier, tier_path, exc_info=True)
            return 0.0

    def apply_forgetting_rules(self, input_refs: List[Dict[str, Any]], rules: List[ForgettableNoiseRule]) -> List[str]:
        """Apply noise rules to identify fragments for pruning (Priority 3).

        Refs without a ``created_at_ts`` field are skipped conservatively —
        we never prune what we cannot age-verify.
        """
        pruned = []
        now = datetime.now(timezone.utc).timestamp()
        for ref in input_refs:
            if "created_at_ts" not in ref:
                # Conservative: missing timestamp → cannot confirm age → do not prune.
                logger.debug(
                    "apply_forgetting_rules: skipping ref %s — missing created_at_ts",
                    self._extract_ref_id(ref),
                )
                continue
            ref_age = now - ref["created_at_ts"]
            reuse = ref.get("reuse_value", 1.0)

            for rule in rules:
                if ref.get("kind") == rule.noise_kind:
                    if ref_age > rule.age_threshold_seconds and reuse < rule.reuse_threshold:
                        pruned.append(self._extract_ref_id(ref))
                        break
        return pruned
    def merge_reflections(self, recent_records: List[Dict[str, Any]]) -> List[MemoryPromotionCandidate]:
        """Cluster reflections by topic + risk_level + outcome_type (Priority 1)."""
        from collections import defaultdict
        
        clusters = defaultdict(list)
        for record in recent_records:
            # Group by topic, risk_level, and outcome_type
            key = (
                record.get("topic", "general"),
                record.get("risk_level", "low"),
                record.get("outcome_type", "success")
            )
            clusters[key].append(record)
        
        candidates = []
        for key, records in clusters.items():
            if len(records) >= 2:  # Only merge if multiple similar records exist
                topic, risk, outcome = key
                candidate_id = f"cluster:{topic}-{uuid4().hex[:4]}"
                
                # Synthesis logic (Sub-function 59.1 Gap)
                candidates.append(
                    MemoryPromotionCandidate(
                        source_ref=candidate_id,
                        candidate_type="pattern",
                        stability_score=min(1.0, len(records) * 0.15),
                        reuse_value=0.6 if outcome == "success" else 0.3,
                        promotion_reason=f"Merged {len(records)} reflections for topic '{topic}' with '{outcome}' outcome."
                    )
                )
                
        return candidates

    def _is_protected_ref(self, ref_id: str) -> bool:
        """Safety check to prevent accidental pruning of identity/safety modules."""
        protected_prefixes = [
            "runtime.identity",
            "runtime.safety",
            "runtime.supervision",
            "identity_role_pack"
        ]
        return any(ref_id.startswith(p) for p in protected_prefixes)
