from __future__ import annotations
"""
反思服务 - 纯接口层

Service层职责：仅提供对外服务接口，不包含任何业务逻辑或编排逻辑。
所有业务逻辑和编排都已移至专门模块。
"""


import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.flow_audit import FlowAudit
from zentex.common.database import DatabaseConnection, LRUCache
from zentex.reflection.errors import ReflectionGenerationError
from zentex.reflection.reflection_dao import ReflectionDAO
from zentex.reflection.models import (
    ReflectionRecord, ReflectionTemplate, ReflectionMetrics, ReflectionType, ReflectionTrigger,
    GovernanceStatus, ReflectionDepth, ReflectionQuality, ReflectionItem, ReflectionOverallRecord,
    create_reflection_id
)
from zentex.reflection.outcome import OutcomeBinding
from zentex.reflection.llm_generator import LLMReflectionGenerator
from zentex.reflection.quality_assessor import ReflectionQualityAssessor
from zentex.reflection.data_sync import ReflectionDataSync
from zentex.reflection.template_manager import ReflectionTemplateManager
from zentex.reflection.metrics_calculator import (
    ReflectionMetricsCalculator, ReflectionUpdatePolicy, MetaAuditGenerator
)
from zentex.reflection.workflow_orchestrator import ReflectionWorkflowOrchestrator

logger = logging.getLogger(__name__)


class ReflectionMaintenanceResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    trigger: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    generated_reflection_id: str = Field(min_length=1)
    used_memory_count: int = Field(ge=0)
    deleted_reflection_count: int = Field(ge=0)
    top_tags: List[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class ReflectionService:
    
    def __init__(
        self,
        persistence: Optional[Any] = None,
        llm_temperature: float = 0.3,
        llm_max_tokens: int = 2048,
        use_llm: bool = True,
        max_cache_size: int = 1000,
        db_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """初始化服务"""
        self.persistence = None
        self._reflection_cache: Dict[str, ReflectionRecord] = {}
        self._max_cache_size = max_cache_size
        self._use_llm = use_llm
        self._dao: ReflectionDAO = self._build_reflection_dao(persistence, db_path=db_path)
        
        try:
            llm_generator = LLMReflectionGenerator(
                temperature=llm_temperature,
                max_tokens=llm_max_tokens
            )
        except Exception as e:
            logger.error("Failed to initialize mandatory LLM: %s", e, exc_info=True)
            raise ReflectionGenerationError(
                f"Reflection service requires LLM but initialization failed: {e}"
            )
        
        # expose for tests
        self._llm_generator = llm_generator
        
        self._orchestrator = ReflectionWorkflowOrchestrator(
            llm_generator=llm_generator,
            quality_assessor=ReflectionQualityAssessor(llm_service=llm_generator._llm_service),
            data_sync=ReflectionDataSync(),
            template_mgr=ReflectionTemplateManager(),
            meta_audit=MetaAuditGenerator()
        )
        self._metrics_calculator = ReflectionMetricsCalculator()
        self._update_policy = ReflectionUpdatePolicy()
        self.outcome_binding = OutcomeBinding()
        self._maintenance_lock = threading.Lock()
        self._maintenance_thread: Optional[threading.Thread] = None
        self._maintenance_stop = threading.Event()
        self._maintenance_interval_seconds = 3600
        self._last_maintenance_at: Optional[datetime] = None
        
        logger.info(f"ReflectionService initialized (max_cache={max_cache_size})")

    def _build_reflection_dao(
        self,
        persistence: Optional[Any],
        *,
        db_path: Optional[Union[str, Path]],
    ) -> ReflectionDAO:
        if db_path is not None:
            resolved_db_path = Path(db_path)
        elif persistence is not None and hasattr(persistence, "storage_path"):
            resolved_db_path = Path(str(persistence.storage_path)) / "reflection.sqlite3"
        else:
            from zentex.common.storage_paths import get_storage_paths

            resolved_db_path = get_storage_paths().app_data_dir / "reflection" / "reflection.sqlite3"
        db = DatabaseConnection(str(resolved_db_path))
        cache = LRUCache(max_size=500, ttl_seconds=300)
        return ReflectionDAO(db, cache)
    
    def generate_reflection(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trigger: ReflectionTrigger = ReflectionTrigger.AUTOMATIC,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        template_id: Optional[str] = None,
        audit: Optional[FlowAudit] = None,
    ) -> ReflectionRecord:
        """生成反思记录 - 委托给工作流编排器"""
        # Merge FlowAudit identity into context so it gets stored in the reflection record.
        effective_context = {**context, **(audit.as_payload() if audit is not None else {})}
        # Phase 1: Generation & Assessment
        try:
            reflection = self._orchestrator.generate_reflection(
                subject=subject,
                reflection_type=reflection_type,
                context=effective_context,
                trigger=trigger,
                trace_id=trace_id,
                session_id=session_id,
                template_id=template_id
            )
        except Exception as e:
            logger.error("Reflection generation/assessment phase failed: %s", e, exc_info=True)
            raise ReflectionGenerationError(f"Generation phase failed: {e}") from e
            
        # Phase 2: Persistence (Mandatory for Integrity)
        self._dao.save_reflection(reflection)
        
        # Bounded Cache Logic
        if len(self._reflection_cache) >= self._max_cache_size:
            # Evict oldest entry (not strictly LRU but O(1) in current dict impl for first key)
            oldest_id = next(iter(self._reflection_cache))
            del self._reflection_cache[oldest_id]
            
        self._reflection_cache[reflection.reflection_id] = reflection
            
        return reflection

    def reflect(
        self,
        *,
        subject: str,
        context: Dict[str, Any],
        reflection_type: Union[str, ReflectionType] = ReflectionType.DECISION_REFLECTION,
        trace_id: Optional[str] = None,
    ) -> ReflectionRecord:
        effective_type = (
            reflection_type
            if isinstance(reflection_type, ReflectionType)
            else ReflectionType(str(reflection_type))
        )
        return self.generate_reflection(
            subject=subject,
            reflection_type=effective_type,
            context=context,
            trace_id=trace_id,
        )

    def record_nine_question_reflection(
        self,
        *,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trace_id: Optional[str] = None,
        audit: Optional[FlowAudit] = None,
    ) -> ReflectionRecord:
        now = datetime.now(timezone.utc)
        effective_context = {**context, **(audit.as_payload() if audit is not None else {})}
        summary = str(effective_context.get("summary") or subject)
        record = ReflectionRecord(
            reflection_id=create_reflection_id(),
            trace_id=trace_id,
            audit_id=str(effective_context.get("audit_id") or "") or None,
            session_id=str(effective_context.get("session_id") or "") or None,
            reflection_type=reflection_type,
            depth=ReflectionDepth.ANALYTICAL,
            quality=ReflectionQuality.GOOD,
            trigger=ReflectionTrigger.AUTOMATIC,
            created_at=now,
            updated_at=now,
            reflection_timestamp=now,
            subject=subject,
            context=effective_context,
            summary=summary,
            insights=[summary],
            lessons=[summary],
            risks=[],
            improvements=[],
            reflection_list=[
                ReflectionItem(
                    content=summary,
                    category="insight",
                    priority=5,
                    metadata={
                        "source": "nine_question_integration",
                        "question_id": effective_context.get("question_id"),
                    },
                )
            ],
            confidence=0.8,
            impact_score=0.5,
            actionability=0.6,
            tags=["nine_question_integration"],
            metadata={
                "source": "nine_question_integration",
                "module_id": effective_context.get("module_id"),
                "question_id": effective_context.get("question_id"),
            },
        )
        self._dao.save_reflection(record)
        self._reflection_cache[record.reflection_id] = record
        return record
    
    def register_expectation(self, target_state: str, criteria: List[str], confidence: float = 0.5) -> str:
        """注册期望 - 委托给OutcomeBinding"""
        exp = self.outcome_binding.register_expectation(target_state, criteria, confidence)
        return exp.expectation_id
    
    def process_outcome(self, expectation_id: str, actual_state: str, metrics: Dict[str, Any]) -> Any:
        """处理结果 - 委托给OutcomeBinding并触发反思"""
        result = self.outcome_binding.collect_result(expectation_id, actual_state, metrics)
        deviation = self.outcome_binding.compare(result)
        
        reflection = self.generate_reflection(
            subject=f"Outcome Analysis for {expectation_id}",
            reflection_type=ReflectionType.OUTCOME_REFLECTION,
            context={
                "expectation_id": expectation_id,
                "result_id": result.result_id,
                "deviation": deviation.model_dump(),
                "metrics": metrics
            }
        )
        
        if deviation.deviation_score > 0.3:
            logger.info(f"Significant deviation detected. Growth feedback triggered.")
        
        return reflection
    
    def get_reflection(self, reflection_id: str) -> ReflectionRecord:
        """获取反思记录"""
        if reflection_id in self._reflection_cache:
            return self._reflection_cache[reflection_id]

        reflection = self._dao.get_reflection(reflection_id)
        if reflection:
            self._reflection_cache[reflection_id] = reflection
            return reflection
        
        raise ValueError(f"Reflection not found: {reflection_id}")
    
    def list_reflections(self, filters: Optional[Dict[str, Any]] = None) -> List[ReflectionRecord]:
        """列出反思记录"""
        return self._dao.query_reflections(filters or {})

    def list_overall_records(
        self,
        *,
        limit: int = 100,
        trace_id: Optional[str] = None,
        reflection_type: Optional[ReflectionType] = None,
    ) -> List[ReflectionOverallRecord]:
        """查询自动派生的整体记录摘要。"""
        return self._dao.list_overall_records(
            limit=limit,
            trace_id=trace_id,
            reflection_type=reflection_type,
        )
    
    def update_reflection(self, reflection_id: str, updates: Dict[str, Any]) -> ReflectionRecord:
        """更新反思记录"""
        reflection = self.get_reflection(reflection_id)
        
        for key, value in updates.items():
            if hasattr(reflection, key):
                setattr(reflection, key, value)
        
        self._dao.save_reflection(reflection)
        
        self._reflection_cache[reflection_id] = reflection
        return reflection
    
    def delete_reflection(self, reflection_id: str) -> bool:
        """删除反思记录"""
        success = self._dao.delete_reflection(reflection_id)
        if reflection_id in self._reflection_cache:
            del self._reflection_cache[reflection_id]
        return success
    
    def create_template(self, name: str, description: str, template_data: Dict[str, Any]) -> ReflectionTemplate:
        """创建模板 - 委托给template_manager"""
        return self._orchestrator._template_mgr.create_template(name, description, template_data)
    
    def get_template(self, template_id: str) -> Optional[ReflectionTemplate]:
        """获取模板"""
        return self._orchestrator._template_mgr.get_template(template_id)
    
    def list_templates(self) -> List[ReflectionTemplate]:
        """列出模板"""
        return list(self._orchestrator._template_mgr.list_templates().values())
    
    def verify_reflection(self, reflection_id: str, verified_by: str) -> ReflectionRecord:
        """验证反思"""
        reflection = self.get_reflection(reflection_id)
        reflection.governance_status = GovernanceStatus.VERIFIED
        reflection.verified_by = verified_by
        
        self._dao.save_reflection(reflection)
        
        return reflection
    
    def mark_suspect(self, reflection_id: str, reason: str) -> ReflectionRecord:
        """标记可疑"""
        reflection = self.get_reflection(reflection_id)
        reflection.governance_status = GovernanceStatus.SUSPECT
        reflection.suspect_reason = reason
        
        self._dao.save_reflection(reflection)
        
        return reflection
    
    def archive_reflection(self, reflection_id: str) -> ReflectionRecord:
        """归档反思"""
        reflection = self.get_reflection(reflection_id)
        reflection.governance_status = GovernanceStatus.ARCHIVED
        
        self._dao.save_reflection(reflection)
        
        return reflection
    
    def get_metrics(self) -> ReflectionMetrics:
        """获取指标 - 委托给metrics_calculator"""
        reflections = self.list_reflections()
        metrics = self._metrics_calculator.calculate_metrics(reflections)
        
        return metrics
    
    def should_update_reflection_list(self, reflection: ReflectionRecord) -> bool:
        """判断是否更新反思列表 - 委托给update_policy"""
        return self._update_policy.should_update_reflection_list(reflection)

    def trigger_memory_aware_maintenance(
        self,
        *,
        operator: str = "reflection_service_manual",
        trigger: ReflectionTrigger = ReflectionTrigger.MANUAL,
        memory_limit: int = 50,
        reflection_limit: int = 500,
    ) -> ReflectionMaintenanceResult:
        from zentex.memory.service import get_service as get_memory_service

        with self._maintenance_lock:
            memory_service = get_memory_service()
            if callable(getattr(memory_service, "trigger_automatic_consolidation_check", None)):
                try:
                    memory_service.trigger_automatic_consolidation_check()
                except Exception:
                    logger.warning("Memory consolidation pre-check failed for reflection maintenance", exc_info=True)

            memory_records = memory_service.query_managed_records(
                limit=max(1, memory_limit),
                status="active",
            )
            deleted_reflection_count = self._cleanup_low_value_reflections(limit=max(50, reflection_limit))
            memory_snapshot = self._summarize_memory_records(memory_records)

            # P2-R2: LLM semantic synthesis — enriches counter-based snapshot with
            # genuine insights.  Falls back to counter-based values on any failure.
            if self._use_llm and memory_records:
                llm_synthesis = self._llm_generator.synthesize_maintenance_insights(
                    top_tags=memory_snapshot["top_tags"],
                    titles=memory_snapshot["titles"],
                    layer_distribution=memory_snapshot["layer_distribution"],
                    unverified_count=memory_snapshot["unverified_count"],
                    tier_pressure=memory_snapshot["tier_pressure"],
                )
                if llm_synthesis:
                    if llm_synthesis.get("summary"):
                        memory_snapshot["summary"] = str(llm_synthesis["summary"])
                    if llm_synthesis.get("insights"):
                        memory_snapshot["insights"] = [str(s) for s in llm_synthesis["insights"]]
                    if llm_synthesis.get("lessons"):
                        memory_snapshot["lessons"] = [str(s) for s in llm_synthesis["lessons"]]
                    if llm_synthesis.get("improvements"):
                        memory_snapshot["improvements"] = [str(s) for s in llm_synthesis["improvements"]]

            now = datetime.now(timezone.utc)
            trace_id = f"reflection-maintenance:{uuid4().hex[:12]}"
            summary = memory_snapshot["summary"] or "No useful memory records were available for reflection maintenance."
            reflection = ReflectionRecord(
                reflection_id=create_reflection_id(),
                trace_id=trace_id,
                audit_id=None,
                session_id=None,
                reflection_type=ReflectionType.LEARNING_REFLECTION,
                depth=ReflectionDepth.ANALYTICAL,
                quality=ReflectionQuality.GOOD if memory_snapshot["top_tags"] else ReflectionQuality.FAIR,
                trigger=trigger,
                created_at=now,
                updated_at=now,
                reflection_timestamp=now,
                subject="Memory-aware reflection maintenance",
                context={
                    "operator": operator,
                    "maintenance_kind": "memory_aware_cleanup",
                    "used_memory_count": len(memory_records),
                    "top_tags": memory_snapshot["top_tags"],
                    "layer_distribution": memory_snapshot["layer_distribution"],
                    "tier_pressure": memory_snapshot["tier_pressure"],
                    "deleted_reflection_count": deleted_reflection_count,
                    "memory_ids": memory_snapshot["memory_ids"],
                },
                summary=summary,
                insights=memory_snapshot["insights"],
                lessons=memory_snapshot["lessons"],
                risks=memory_snapshot["risks"],
                improvements=memory_snapshot["improvements"],
                reflection_list=[
                    ReflectionItem(
                        content=item,
                        category="insight",
                        priority=5,
                        metadata={"source": "memory_aware_maintenance", "operator": operator},
                    )
                    for item in (memory_snapshot["insights"][:2] or [summary])
                ],
                confidence=0.8 if memory_records else 0.55,
                impact_score=0.65 if memory_records else 0.3,
                actionability=0.7 if memory_snapshot["improvements"] else 0.4,
                tags=["maintenance", "memory_aware", *memory_snapshot["top_tags"][:3]],
                metadata={
                    "source": "memory_aware_maintenance",
                    "operator": operator,
                    "cleanup_deleted_count": deleted_reflection_count,
                },
            )
            self._dao.save_reflection(reflection)
            self._reflection_cache[reflection.reflection_id] = reflection
            self._last_maintenance_at = now

            return ReflectionMaintenanceResult(
                trigger=trigger.value if hasattr(trigger, "value") else str(trigger),
                trace_id=trace_id,
                generated_reflection_id=reflection.reflection_id,
                used_memory_count=len(memory_records),
                deleted_reflection_count=deleted_reflection_count,
                top_tags=memory_snapshot["top_tags"],
                summary=summary,
            )

    def run_scheduled_maintenance_if_due(
        self,
        *,
        interval_seconds: Optional[int] = None,
        operator: str = "reflection_service_scheduler",
    ) -> Optional[ReflectionMaintenanceResult]:
        effective_interval = max(60, int(interval_seconds or self._maintenance_interval_seconds))
        now = datetime.now(timezone.utc)
        if self._last_maintenance_at is not None:
            elapsed = (now - self._last_maintenance_at).total_seconds()
            if elapsed < effective_interval:
                return None
        return self.trigger_memory_aware_maintenance(
            operator=operator,
            trigger=ReflectionTrigger.SCHEDULED,
        )

    def start_background_maintenance(
        self,
        *,
        interval_seconds: int = 3600,
        operator: str = "reflection_service_scheduler",
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
                    logger.warning("Reflection background maintenance failed", exc_info=True)

        self._maintenance_thread = threading.Thread(
            target=_worker,
            name="reflection-maintenance",
            daemon=True,
        )
        self._maintenance_thread.start()
        return True

    def stop_background_maintenance(self) -> None:
        self._maintenance_stop.set()

    def _cleanup_low_value_reflections(self, *, limit: int) -> int:
        """Delete low-value reflection records across ALL sources.

        Deletion criteria (applied in order; first match wins):
        1. Maintenance duplicates — same (subject, summary) seen before AND age > 1 h.
           Only applies to records produced by automatic maintenance passes.
        2. Governance-retired — ARCHIVED / DEPRECATED / HIDDEN AND age > 1 h.
        3. Poor quality + low confidence + low actionability AND age > 7 days.
           Applies to all sources; does NOT touch records younger than 7 days so
           that recent but initially low-scored reflections get a chance to be
           updated before they are cleaned up.
        """
        from zentex.reflection.reflection_cleanup_pipeline import (
            extract_deletion_candidates,
            reflections_to_dataframe,
        )

        rows = self.list_reflections({"limit": limit})
        now = datetime.now(timezone.utc)
        cleanup_df = reflections_to_dataframe(rows, now=now)
        candidate_ids = set(extract_deletion_candidates(cleanup_df))
        protected_ids: set[str] = set()
        audit_window_ids = {
            str(reflection_id)
            for reflection_id in cleanup_df.loc[cleanup_df["age_days"] > 7.0, "reflection_id"].tolist()
            if str(reflection_id)
        }
        audit_rows = [row for row in rows if row.reflection_id in audit_window_ids]
        if len(audit_rows) < 100:
            audit_rows = rows
        if len(audit_rows) >= 100:
            try:
                from zentex.reflection.label_auditor import ReflectionLabelAuditor

                report = ReflectionLabelAuditor().audit(audit_rows)
                protected_ids = set(report.suspicious_ids)
                for reflection_id in protected_ids:
                    try:
                        self.mark_suspect(reflection_id, "cleanlab_label_issue")
                    except Exception:
                        logger.warning(
                            "Failed to mark reflection %s as suspect after label audit",
                            reflection_id,
                            exc_info=True,
                        )
            except (ImportError, ValueError) as exc:
                logger.warning("Reflection label audit skipped: %s", exc, exc_info=True)
            except Exception:
                logger.warning("Reflection label audit failed; proceeding without protection", exc_info=True)
        deleted_count = 0

        for reflection in rows:
            if reflection.reflection_id in protected_ids:
                continue
            if reflection.reflection_id in candidate_ids and self.delete_reflection(reflection.reflection_id):
                deleted_count += 1

        return deleted_count

    def _summarize_memory_records(self, records: List[Any]) -> Dict[str, Any]:
        from zentex.reflection.memory_snapshot_pipeline import (
            build_memory_snapshot,
            memory_records_to_dataframe,
        )

        return build_memory_snapshot(
            memory_records_to_dataframe(records, now=datetime.now(timezone.utc))
        )


# Global singleton instance for reflection service
_default_service: Optional[ReflectionService] = None


def get_service() -> ReflectionService:
    """Standard service factory function for launcher assembly.
    
    Returns the global ReflectionService instance, creating it if necessary.
    """
    global _default_service
    if _default_service is None:
        import os
        from zentex.common.storage_paths import get_storage_paths
        
        env_root = os.environ.get("ZENTEX_REFLECTION_ROOT")
        db_path = (
            Path(env_root).absolute() / "reflection.sqlite3"
            if env_root
            else (get_storage_paths().app_data_dir / "reflection" / "reflection.sqlite3").absolute()
        )
        _default_service = ReflectionService(db_path=db_path)
    return _default_service


def get_reflection_service() -> ReflectionService:
    return get_service()
