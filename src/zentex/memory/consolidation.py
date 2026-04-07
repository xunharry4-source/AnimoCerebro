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
from threading import Lock
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderRateLimitError,
    ModelProviderSpec,
)
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.transcript import (
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)


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
        model_provider: ModelProviderSpec,
        analysis_plugins: List[ConsolidationAnalysisPlugin],
        transcript_store: BrainTranscriptStore,
        brain_scope: str,
        queue: Optional[ConsolidationQueue] = None,
    ) -> None:
        """
        Initialize the consolidation engine.

        Args:
            model_provider: Active live LLM plugin used for semantic summarization.
            analysis_plugins: Active multi-plugin analyzers for clustering/pruning hints.
            transcript_store: Append-only audit stream for cycle success/failure records.
            brain_scope: Shared state scope used for lease ownership and stale-write checks.
            queue: Optional background queue adapter. Defaults to a local thread-pool queue.
        """
        self._model_provider: ModelProviderSpec = model_provider
        self._analysis_plugins: List[ConsolidationAnalysisPlugin] = list(analysis_plugins)
        self._transcript_store: BrainTranscriptStore = transcript_store
        self._brain_scope: str = brain_scope
        self._queue: ConsolidationQueue = queue or ThreadPoolConsolidationQueue()
        self._lock: Lock = Lock()
        self._cycles_by_id: Dict[str, ConsolidationCycle] = {}
        self._snapshot_version: int = 0
        self._memory_versions: Dict[str, int] = {}
        self._tombstone_state: Dict[str, bool] = {}
        self._active_lease_by_scope: Dict[str, str] = {}
        self._rate_limit_failures: int = 0

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
        tombstone_state: Dict[str, bool] | None = None,
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

        response = self._model_provider.generate_json(
            prompt=(
                "Summarize the reusable memory value of the supplied memory fragments. "
                "Return JSON with keys summary, promotion_candidates, compressed_refs."
            ),
            context=self._translate_model_context(
                task_request=task_request,
                plugin_outputs=plugin_outputs,
            ),
            caller_context=ModelProviderCallerContext(
                source_module="Offline memory consolidation engine",
                invocation_phase="extracting stable memory patterns and compression summary",
                question_driver_refs=["什么值得长期记住", "哪些内容可以安全遗忘", "哪些模式值得升格"],
                decision_id=task_request.cycle_id,
            ),
        )

        promoted_candidates = [
            MemoryPromotionCandidate.model_validate(candidate)
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

            for ref_id in cycle.promoted_refs:
                self._memory_versions[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            for ref_id in cycle.compressed_refs:
                self._memory_versions[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            for ref_id in cycle.pruned_refs:
                self._tombstone_state[ref_id] = True
                self._memory_versions[ref_id] = self._memory_versions.get(ref_id, 0) + 1
            self._snapshot_version += 1
            committed_cycle = cycle.model_copy(update={"snapshot_version": self._snapshot_version})
            self._cycles_by_id[committed_cycle.cycle_id] = committed_cycle
        return committed_cycle

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
        }

    def _next_backoff_seconds(self) -> int:
        """Return the next exponential backoff delay for rate-limited consolidation cycles."""
        with self._lock:
            self._rate_limit_failures += 1
            return min(30 * (2 ** (self._rate_limit_failures - 1)), 1800)

    def _extract_ref_id(self, item: Dict[str, Any]) -> str:
        """Extract the stable memory reference id from an input memory object."""
        return str(item.get("ref_id") or item.get("id") or "unknown-ref")

    def _is_protected_ref(self, ref_id: str) -> bool:
        """Return whether a ref belongs to protected identity memory and cannot be pruned."""
        protected_markers = (
            "identity_role_pack",
            "identity_constraint_pack",
            "identity_experience_pack",
        )
        return any(marker in ref_id for marker in protected_markers)
