from __future__ import annotations

"""Public learning service for cross-module access."""

import asyncio
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.module_logs import record_module_log
from zentex.common.flow_audit import FlowAudit
from zentex.common.storage_paths import get_storage_paths
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection, describe_direction
from zentex.learning.engine import (
    LEARNING_SESSION_ID,
    LearningCycleResult,
    get_learning_status,
    list_available_directions,
    run_learning_cycle,
    start_learning,
)
from zentex.learning.store import LEARNING_EVENT_TYPE, LEARNING_OVERALL_EVENT_TYPE, LearningStore
from zentex.llm.providers.config import get_maintenance_llm_config

logger = logging.getLogger(__name__)


class LearningRecord(BaseModel):
    """Compatibility record for callers that need a typed learning event."""

    model_config = ConfigDict(extra="allow")

    trace_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    detail: Dict[str, Any] = Field(default_factory=dict)


class LearningOutcome(BaseModel):
    """Typed wrapper over the engine result payload."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    detail: Dict[str, Any] = Field(default_factory=dict)


class LearningOverallRecord(BaseModel):
    """Normalized overall learning record for timeline-style queries."""

    model_config = ConfigDict(extra="allow")

    trace_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    detail: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(min_length=1)


class LearningMaintenanceResult(BaseModel):
    """Result of learning-maintenance cleanup and synthesis."""

    model_config = ConfigDict(extra="allow")

    trigger: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    used_memory_count: int = Field(ge=0)
    used_reflection_count: int = Field(ge=0)
    deleted_entry_count: int = Field(ge=0)
    top_tags: List[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class LearningService:
    """Single public learning service backed by its own canonical store."""

    def __init__(self, storage_root: Optional[Union[str, Path]] = None, module_log_service: Any = None) -> None:
        if storage_root is None:
            env_root = os.environ.get("ZENTEX_LEARNING_ROOT")
            if env_root:
                storage_root = Path(env_root)
            else:
                storage_root = get_storage_paths().data_root / "learning.sqlite3"
        candidate = Path(storage_root)
        if candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            db_path = candidate
        else:
            db_path = candidate / "learning.sqlite3"
        self.storage_root = db_path.parent
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._store = LearningStore(db_path=db_path, session_id=LEARNING_SESSION_ID)
        self._maintenance_lock = threading.Lock()
        self._maintenance_thread: Optional[threading.Thread] = None
        self._maintenance_stop = threading.Event()
        self._maintenance_interval_seconds = 3600
        self._last_maintenance_at: Optional[datetime] = None
        self._module_log_service = module_log_service
        # P3-L3: idempotency guard — hash of the last processed memory_id set
        self._last_maintenance_memory_hash: Optional[str] = None

    @property
    def store(self) -> LearningStore:
        return self._store

    def attach_module_log_service(self, module_log_service: Any) -> None:
        self._module_log_service = module_log_service

    def close(self) -> None:
        close = getattr(self._store, "close", None)
        if callable(close):
            close()

    async def start_cycle(
        self,
        *,
        direction: Union[str, LearningDirection],
        provider: Any = None,
        llm_service: Any = None,
        model_provider_key: Optional[str] = None,
        doc_url: Optional[str] = None,
        dry_run: bool = False,
        load_factor: float = 0.0,
        store: Any = None,
    ) -> LearningOutcome:
        result = await start_learning(
            store=store or self._store,
            direction=direction,
            provider=provider,
            llm_service=llm_service,
            model_provider_key=model_provider_key,
            doc_url=doc_url,
            dry_run=dry_run,
            load_factor=load_factor,
        )
        outcome = _to_learning_outcome(result)
        self._sync_generated_learning_task(
            task_id=outcome.trace_id,
            direction=str(direction.value if isinstance(direction, LearningDirection) else direction),
            status=outcome.status,
            trace_id=outcome.trace_id,
            doc_url=doc_url,
        )
        return outcome

    def get_status(
        self,
        store: Any = None,
        *,
        trace_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return get_learning_status(store or self._store, trace_id=trace_id, limit=limit)

    def list_history_entries(self, *, limit: int = 200) -> list[Any]:
        return list(self._store.query_by_session(LEARNING_SESSION_ID, limit=limit))

    def query_history_entries(self, *, limit: int = 200, offset: int = 0) -> list[Any]:
        return list(
            self._store.query_history_entries(
                session_id=LEARNING_SESSION_ID,
                entry_type=LEARNING_EVENT_TYPE,
                limit=limit,
                offset=offset,
            )
        )

    def count_history_entries(self) -> int:
        return self._store.count_history_entries(
            session_id=LEARNING_SESSION_ID,
            entry_type=LEARNING_EVENT_TYPE,
        )

    def query_overall_records(
        self,
        *,
        limit: int = 200,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[LearningOverallRecord]:
        rows = self._store.query_history_entries(
            session_id=LEARNING_SESSION_ID,
            entry_type=LEARNING_OVERALL_EVENT_TYPE,
            limit=limit * 4 if (trace_id or status) else limit,
        )
        result: list[LearningOverallRecord] = []
        for row in rows:
            payload = dict(row.payload or {})
            record = LearningOverallRecord(
                trace_id=str(row.trace_id or payload.get("trace_id") or ""),
                status=str(payload.get("status") or "unknown"),
                direction=str(payload.get("direction") or "unknown"),
                summary=str(payload.get("summary") or ""),
                detail=dict(payload.get("detail") or {}),
                timestamp=str(row.timestamp or ""),
            )
            if trace_id and record.trace_id != trace_id:
                continue
            if status and record.status != status:
                continue
            result.append(record)
            if len(result) >= limit:
                break
        return result

    def query_q2_strategy_patches_context(
        self,
        *,
        topic: Optional[str] = None,
        role: Optional[str] = None,
        risk_level: Optional[str] = None,
        top_k: int = 8,
    ) -> Dict[str, Any]:
        """
        Return Q2-ready reusable strategy patches through the LearningService boundary.

        This facade is intentionally stricter than history queries: it extracts only
        structured strategy patch payloads from durable learning records, keeps only
        patches whose own status is `validated` or `active`, excludes candidate or
        revoked material, and returns the fields Q2 needs for
        [Memory_&_Patches_Context]: name, patch_summary, risk_level, and
        applicable_scenario plus trace metadata for auditability.
        """
        limit = max(1, int(top_k or 8))
        rows = self._store.query_by_session(LEARNING_SESSION_ID, limit=max(limit * 8, limit))
        patches: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            for patch in _q2_extract_strategy_patches(row.payload):
                normalized = _q2_normalize_strategy_patch(patch, row=row)
                if not normalized:
                    continue
                status = str(normalized.get("status") or "").strip().lower()
                if status not in {"validated", "active"}:
                    continue
                if not _q2_strategy_patch_matches(
                    normalized,
                    topic=topic,
                    role=role,
                    risk_level=risk_level,
                ):
                    continue
                patch_key = str(normalized.get("patch_id") or normalized.get("name") or "").strip()
                if patch_key in seen:
                    continue
                seen.add(patch_key)
                patches.append(normalized)
                if len(patches) >= limit:
                    break
            if len(patches) >= limit:
                break
        return {
            "source": "zentex.learning.service.LearningService.query_q2_strategy_patches_context",
            "filters": {
                "topic": str(topic or "").strip(),
                "role": str(role or "").strip(),
                "risk_level": str(risk_level or "").strip(),
            },
            "allowed_statuses": ["validated", "active"],
            "excluded_statuses": ["candidate", "revoked"],
            "reusable_strategy_patches": patches,
        }

    def list_directions(self) -> list[Dict[str, Any]]:
        return list_available_directions()

    def record_nine_question_learning(
        self,
        *,
        question_id: str,
        learning_kind: str,
        detail: Dict[str, Any],
        trace_id: str,
        store: Any = None,
        audit: Optional[FlowAudit] = None,
    ) -> LearningRecord:
        effective_store = store or self._store
        if not callable(getattr(effective_store, "write_entry", None)):
            raise RuntimeError("store is required for nine-question learning persistence")

        learning_detail = {
            "question_id": question_id,
            "learning_kind": learning_kind,
            **detail,
        }
        flow_audit = audit or FlowAudit.new(
            "learning",
            source_module="zentex.learning.service",
            question_driver_refs=[question_id],
        )
        result = _run_coroutine_sync(
            run_learning_cycle(
                store=effective_store,
                direction=LearningDirection.NINE_QUESTION_INTEGRATION,
                dry_run=False,
                load_factor=0.0,
                extra_context=learning_detail,
                audit=flow_audit,
            )
        )
        record = LearningRecord(
            trace_id=str(result.get("trace_id") or trace_id),
            status=str(result.get("status") or "unknown"),
            detail=dict(result.get("detail") or learning_detail),
        )
        return record

    def trigger_memory_aware_maintenance(
        self,
        *,
        operator: str = "learning_service_manual",
        trigger: str = "manual",
        memory_limit: int = 50,
        reflection_limit: int = 50,
        cleanup_limit: int = 500,
        force: bool = False,
    ) -> LearningMaintenanceResult:
        from zentex.memory.service import get_service as get_memory_service
        from zentex.reflection.service import get_service as get_reflection_service

        with self._maintenance_lock:
            memory_service = get_memory_service()
            reflection_service = get_reflection_service()

            if callable(getattr(memory_service, "trigger_automatic_consolidation_check", None)):
                try:
                    memory_service.trigger_automatic_consolidation_check(force=force, operator=operator)
                except Exception:
                    logger.warning("Memory consolidation pre-check failed in learning maintenance", exc_info=True)

            memory_records = memory_service.query_managed_records(
                limit=max(1, memory_limit),
                status="active",
            )
            reflection_records = reflection_service.list_overall_records(limit=max(1, reflection_limit))

            # P3-L3: idempotency guard — skip if same memory batch was already processed
            import hashlib as _hashlib
            memory_ids_sorted = sorted(
                str(getattr(r, "memory_id", "") or "") for r in memory_records
            )
            batch_hash = _hashlib.sha256(",".join(memory_ids_sorted).encode()).hexdigest()[:16]
            if not force and self._last_maintenance_memory_hash == batch_hash and memory_records:
                logger.info(
                    "Learning maintenance skipped — same memory batch as last run (idempotency key=%s)", batch_hash
                )
                # Still run cleanup so stale entries don't accumulate indefinitely
                self._cleanup_low_value_learning_entries(limit=max(50, cleanup_limit))
                skipped_trace_id = f"learning-maintenance:idempotent-{batch_hash}"
                self._sync_generated_learning_task(
                    task_id=skipped_trace_id,
                    direction="memory_maintenance",
                    status="skipped",
                    trace_id=skipped_trace_id,
                    summary="Skipped: identical memory batch already processed.",
                )
                return LearningMaintenanceResult(
                    trigger=trigger,
                    trace_id=skipped_trace_id,
                    used_memory_count=len(memory_records),
                    used_reflection_count=len(reflection_records),
                    deleted_entry_count=0,
                    top_tags=[],
                    summary="Skipped: identical memory batch already processed.",
                )

            deleted_entry_count = self._cleanup_low_value_learning_entries(limit=max(50, cleanup_limit))
            snapshot = self._summarize_maintenance_inputs(
                memory_records=memory_records,
                reflection_records=reflection_records,
            )

            trace_id = f"learning-maintenance:{uuid4().hex[:12]}"
            turn_id = "cycle_" + trace_id.split(":")[-1]
            now = datetime.now(timezone.utc).isoformat()
            detail = {
                "operator": operator,
                "maintenance_kind": "memory_aware_cleanup",
                "force": force,
                "used_memory_count": len(memory_records),
                "used_reflection_count": len(reflection_records),
                "deleted_entry_count": deleted_entry_count,
                "top_tags": snapshot["top_tags"],
                "focus_topics": snapshot["focus_topics"],
                "cross_module_pressure": snapshot["cross_module_pressure"],
                "layer_distribution": snapshot["layer_distribution"],
                "source_memory_ids": snapshot["memory_ids"],
            }
            summary = snapshot["summary"] or "Learning maintenance found no reusable memory or reflection context."

            self._store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=LEARNING_EVENT_TYPE,
                payload={
                    "kind": "maintenance_cycle_completed",
                    "direction": "memory_maintenance",
                    "status": "completed",
                    "summary": summary,
                    "detail": detail,
                    "trigger": trigger,
                    "timestamp": now,
                },
                source="zentex.learning.service",
                trace_id=trace_id,
            )
            self._store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=LEARNING_OVERALL_EVENT_TYPE,
                payload={
                    "kind": "overall_record",
                    "direction": "memory_maintenance",
                    "status": "completed",
                    "summary": summary,
                    "detail": detail,
                    "trigger": trigger,
                },
                source="zentex.learning.service",
                trace_id=trace_id,
            )
            self._last_maintenance_at = datetime.now(timezone.utc)
            self._last_maintenance_memory_hash = batch_hash  # P3-L3: record processed batch
            self._sync_generated_learning_task(
                task_id=trace_id,
                direction="memory_maintenance",
                status="completed",
                trace_id=trace_id,
                summary=summary,
            )

            return LearningMaintenanceResult(
                trigger=trigger,
                trace_id=trace_id,
                used_memory_count=len(memory_records),
                used_reflection_count=len(reflection_records),
                deleted_entry_count=deleted_entry_count,
                top_tags=snapshot["top_tags"],
                summary=summary,
            )

    def run_scheduled_maintenance_if_due(
        self,
        *,
        interval_seconds: Optional[int] = None,
        operator: str = "learning_service_scheduler",
    ) -> Optional[LearningMaintenanceResult]:
        effective_interval = max(60, int(interval_seconds or self._maintenance_interval_seconds))
        now = datetime.now(timezone.utc)
        if self._last_maintenance_at is not None:
            elapsed = (now - self._last_maintenance_at).total_seconds()
            if elapsed < effective_interval:
                self._record_scheduled_maintenance_log(
                    status="skipped",
                    action_label="定时维护已跳过",
                    reason=f"距离上次维护仅 {int(elapsed)} 秒，未达到 {effective_interval} 秒间隔。",
                    details={
                        "elapsed_seconds": elapsed,
                        "interval_seconds": effective_interval,
                        "last_maintenance_at": self._last_maintenance_at.isoformat(),
                    },
                )
                return None
        result = self.trigger_memory_aware_maintenance(
            operator=operator,
            trigger="scheduled",
        )
        self._record_scheduled_maintenance_log(
            status="completed",
            action_label="定时维护已执行",
            reason="学习模块定时维护已完成，已汇总记忆与反思并清理低价值学习记录。",
            details=result.model_dump(mode="json"),
            result=result,
        )
        return result

    def start_background_maintenance(
        self,
        *,
        interval_seconds: int = 3600,
        operator: str = "learning_service_scheduler",
    ) -> bool:
        if self._maintenance_thread is not None and self._maintenance_thread.is_alive():
            return False

        self._maintenance_interval_seconds = max(60, int(interval_seconds))
        self._maintenance_stop.clear()

        def _worker() -> None:
            while not self._maintenance_stop.wait(self._maintenance_interval_seconds):
                try:
                    self.run_scheduled_maintenance_if_due(
                        interval_seconds=self._maintenance_interval_seconds,
                        operator=operator,
                    )
                except Exception:
                    logger.warning("Learning background maintenance cycle failed", exc_info=True)

        self._maintenance_thread = threading.Thread(
            target=_worker,
            name="learning-maintenance",
            daemon=True,
        )
        self._maintenance_thread.start()
        return True

    def stop_background_maintenance(self) -> None:
        self._maintenance_stop.set()

    def _record_scheduled_maintenance_log(
        self,
        *,
        status: str,
        action_label: str,
        reason: str,
        details: dict[str, Any],
        result: LearningMaintenanceResult | None = None,
    ) -> None:
        record_module_log(
            self._module_log_service,
            source_module="learning",
            module_label="学习模块",
            action="scheduled_maintenance",
            action_label=action_label,
            object_id=(result.trace_id if result is not None else "learning-maintenance-scheduler"),
            object_label="学习记忆感知维护",
            before_status="running",
            after_status=status,
            reason=reason,
            details=details,
            operator_id="learning-service-scheduler",
            status=status,
        )

    def _sync_generated_learning_task(
        self,
        *,
        task_id: str,
        direction: str,
        status: str,
        trace_id: str,
        doc_url: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        if not task_id or not str(task_id).strip():
            raise RuntimeError("learning generated task_id is required for task-service audit sync")
        from zentex.tasks.integration.workflow_bridge import WorkflowTaskBridge

        bridge = WorkflowTaskBridge()
        synced_task_id = bridge.sync_learning_submission(
            task_id=str(task_id),
            direction=str(direction or "unknown"),
            priority="medium",
            trace_id=str(trace_id or task_id),
            session_id=LEARNING_SESSION_ID,
            doc_url=doc_url,
        )
        bridge.sync_learning_status(
            str(task_id),
            str(status or "unknown"),
            direction=str(direction or "unknown"),
            remarks=summary or f"Learning status -> {status}",
        )
        return synced_task_id

    def _cleanup_low_value_learning_entries(self, *, limit: int) -> int:
        rows = self._store.query_by_session(LEARNING_SESSION_ID, limit=limit)
        now = datetime.now(timezone.utc)
        stale_entry_ids: list[str] = []
        seen_overall_summaries: set[str] = set()

        for row in rows:
            payload = dict(row.payload or {})
            age_seconds = 0.0
            try:
                age_seconds = max(0.0, (now - datetime.fromisoformat(row.timestamp)).total_seconds())
            except Exception:
                logger.warning("Failed to parse timestamp for learning entry %s; treating as age=0", row.entry_id, exc_info=True)
                age_seconds = 0.0

            status = str(payload.get("status") or "")
            kind = str(payload.get("kind") or "")
            direction = str(payload.get("direction") or "")

            if row.entry_type == LEARNING_OVERALL_EVENT_TYPE and direction == "memory_maintenance":
                summary = str(payload.get("summary") or "").strip().lower()
                if summary in seen_overall_summaries and age_seconds > 3600:
                    stale_entry_ids.append(row.entry_id)
                    continue
                seen_overall_summaries.add(summary)

            if status in {"dry_run", "budget_hold", "unknown_direction"} and age_seconds > 86400:
                stale_entry_ids.append(row.entry_id)
                continue
            if kind == "aborted" and age_seconds > 86400:
                stale_entry_ids.append(row.entry_id)

        return self._store.delete_entries(stale_entry_ids)

    def _summarize_maintenance_inputs(
        self,
        *,
        memory_records: List[Any],
        reflection_records: List[Any],
    ) -> Dict[str, Any]:
        """Build a cross-module maintenance summary.

        Phase 1 — counter-based baseline (always runs).
        Phase 2 — LLM semantic synthesis (runs when records are available;
                   falls back silently to Phase 1 output on any failure).
        """
        from zentex.learning.stats_pipeline import (
            compute_weighted_cross_summary,
            merge_cross_module_records,
        )

        snapshot = compute_weighted_cross_summary(
            merge_cross_module_records(
                memory_records,
                reflection_records,
                now=datetime.now(timezone.utc),
            )
        )

        result: Dict[str, Any] = {
            "summary": snapshot["summary"],
            "top_tags": snapshot["top_weighted_tags"],
            "focus_topics": snapshot["focus_topics"][:5],
            "memory_ids": snapshot["memory_ids"],
            "cross_module_pressure": snapshot["cross_module_pressure"],
            "layer_distribution": snapshot["layer_distribution"],
        }

        # Phase 2 — LLM semantic synthesis (P2-L2)
        if memory_records or reflection_records:
            from zentex.learning.llm_prompt import build_learning_maintenance_synthesis_prompt
            from zentex.foundation.specs.model_provider import ModelProviderCallerContext
            try:
                from zentex.llm import get_llm_service
                llm_service = get_llm_service()
                cfg = get_maintenance_llm_config()
                prompt = build_learning_maintenance_synthesis_prompt(
                    top_tags=result["top_tags"],
                    focus_topics=result["focus_topics"][:5],
                    layer_distribution=result["layer_distribution"],
                    cross_module_pressure=result["cross_module_pressure"],
                )
                caller_context = ModelProviderCallerContext(
                    source_module="learning_service.maintenance",
                    invocation_phase="learning_maintenance_synthesis",
                    decision_id="learning-maintenance-synthesis",
                )
                llm_result = llm_service.generate_json(
                    prompt=prompt,
                    context={},
                    caller_context=caller_context,
                    source_module=caller_context.source_module,
                    invocation_phase=caller_context.invocation_phase,
                    decision_id=caller_context.decision_id,
                    provider_key=str(cfg.get("provider_key") or "").strip() or None,
                    model=str(cfg.get("model") or "").strip() or None,
                )
                output = llm_result.output if llm_result is not None else {}
                if isinstance(output, dict):
                    if output.get("summary"):
                        result["summary"] = str(output["summary"])
                    if output.get("top_learning_themes"):
                        result["top_learning_themes"] = [str(t) for t in output["top_learning_themes"]]
                    if output.get("recommended_directions"):
                        result["recommended_directions"] = [str(d) for d in output["recommended_directions"]]
            except Exception:
                logger.warning("LLM synthesis failed in _summarize_maintenance_inputs; using counter-based summary", exc_info=True)

        return result


_default_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    global _default_service
    if _default_service is None:
        _default_service = LearningService()
    return _default_service


def get_service() -> LearningService:
    """Standard service factory function for launcher assembly.
    
    Alias for get_learning_service() to maintain compatibility
    with the SystemAssembler's expectation of a get_service() function.
    """
    return get_learning_service()


def _to_learning_outcome(result: Any) -> LearningOutcome:
    payload = dict(result) if isinstance(result, dict) else {
        "status": getattr(result, "status", "unknown"),
        "trace_id": getattr(result, "trace_id", ""),
        "detail": getattr(result, "detail", {}),
    }
    return LearningOutcome(
        status=str(payload.get("status") or "unknown"),
        trace_id=str(payload.get("trace_id") or ""),
        detail=dict(payload.get("detail") or {}),
    )


def _run_coroutine_sync(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    
    # If we are already in an event loop, we cannot use asyncio.run().
    # We must run the coroutine in a separate thread to avoid blocking or re-entrance issues.
    import threading
    from concurrent.futures import Future

    result_future: Future[Any] = Future()

    def _thread_target() -> None:
        try:
            # Create a new loop for the background thread
            res = asyncio.run(coro)
            result_future.set_result(res)
        except Exception as exc:
            result_future.set_exception(exc)

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return result_future.result()


def _q2_extract_strategy_patches(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    payload = dict(payload or {})
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    for source in (payload, detail):
        for key in ("strategy_patch", "patch"):
            value = source.get(key)
            if isinstance(value, dict):
                candidates.append(dict(value))
        for key in ("strategy_patches", "patches"):
            value = source.get(key)
            if isinstance(value, list):
                candidates.extend(dict(item) for item in value if isinstance(item, dict))
    return candidates


def _q2_text(value: Any) -> str:
    return str(value or "").strip()


def _q2_normalize_strategy_patch(patch: Dict[str, Any], *, row: Any) -> Dict[str, Any]:
    patch_id = _q2_text(patch.get("patch_id") or patch.get("id"))
    name = _q2_text(patch.get("name") or patch.get("patch_name") or patch_id)
    summary = _q2_text(
        patch.get("patch_summary")
        or patch.get("summary")
        or patch.get("recommendation")
        or patch.get("lesson")
    )
    applicable_scenario = _q2_text(
        patch.get("applicable_scenario")
        or patch.get("applies_to")
        or patch.get("target")
        or patch.get("recommendation")
    )
    if not name or not summary:
        return {}
    return {
        "patch_id": patch_id,
        "name": name,
        "patch_summary": summary,
        "risk_level": _q2_text(patch.get("risk_level")),
        "applicable_scenario": applicable_scenario or summary,
        "status": _q2_text(patch.get("status")),
        "source_trace_id": _q2_text(getattr(row, "trace_id", "")),
        "recorded_at": _q2_text(getattr(row, "timestamp", "")),
    }


def _q2_strategy_patch_matches(
    patch: Dict[str, Any],
    *,
    topic: Optional[str],
    role: Optional[str],
    risk_level: Optional[str],
) -> bool:
    risk_filter = _q2_text(risk_level).lower()
    if risk_filter and _q2_text(patch.get("risk_level")).lower() != risk_filter:
        return False
    haystack = " ".join(
        _q2_text(patch.get(key)).lower()
        for key in ("name", "patch_summary", "applicable_scenario")
    )
    for expected in (_q2_text(topic).lower(), _q2_text(role).lower()):
        if expected and expected not in haystack:
            return False
    return True


__all__ = [
    "LearningService",
    "LearningRecord",
    "LearningOutcome",
    "LearningOverallRecord",
    "LearningMaintenanceResult",
    "LearningCycleResult",
    "ReasoningBudget",
    "LearningDirection",
    "describe_direction",
    "LEARNING_SESSION_ID",
    "run_learning_cycle",
    "start_learning",
    "list_available_directions",
    "get_learning_status",
    "get_learning_service",
]
