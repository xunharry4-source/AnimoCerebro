"""
反思服务 - 纯接口层

Service层职责：仅提供对外服务接口，不包含任何业务逻辑或编排逻辑。
所有业务逻辑和编排都已移至专门模块。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.reflection.models import (
    ReflectionRecord, ReflectionTemplate, ReflectionMetrics, ReflectionType, ReflectionTrigger,
    GovernanceStatus
)
from zentex.reflection.errors import ReflectionGenerationError
from zentex.reflection.persistence import ReflectionPersistence
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

class ReflectionService:
    
    def __init__(
        self,
        persistence: Optional[ReflectionPersistence] = None,
        llm_temperature: float = 0.3,
        llm_max_tokens: int = 2048,
        use_llm: bool = True
    ) -> None:
        """初始化服务"""
        self.persistence = persistence
        self._reflection_cache: Dict[str, ReflectionRecord] = {}
        self._use_llm = use_llm
        try:
            llm_generator = LLMReflectionGenerator(
                temperature=llm_temperature,
                max_tokens=llm_max_tokens
            )
        except Exception as e:
            logger.error(f"Failed to initialize mandatory LLM: {e}")
            raise ReflectionGenerationError(
                f"Reflection service requires LLM but initialization failed: {e}"
            )
        # expose for tests
        self._llm_generator = llm_generator
        """初始化服务"""
        self.persistence = persistence
        self._reflection_cache: Dict[str, ReflectionRecord] = {}
        
        try:
            llm_generator = LLMReflectionGenerator(
                temperature=llm_temperature,
                max_tokens=llm_max_tokens
            )
        except Exception as e:
            logger.error(f"Failed to initialize mandatory LLM: {e}")
            raise ReflectionGenerationError(
                f"Reflection service requires LLM but initialization failed: {e}"
            )
        
        self._orchestrator = ReflectionWorkflowOrchestrator(
            llm_generator=llm_generator,
            quality_assessor=ReflectionQualityAssessor(),
            data_sync=ReflectionDataSync(),
            template_mgr=ReflectionTemplateManager(),
            meta_audit=MetaAuditGenerator()
        )
        self._metrics_calculator = ReflectionMetricsCalculator()
        self._update_policy = ReflectionUpdatePolicy()
        self.outcome_binding = OutcomeBinding()
        
        logger.info("ReflectionService initialized")
    
    def generate_reflection(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trigger: ReflectionTrigger = ReflectionTrigger.AUTOMATIC,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        template_id: Optional[str] = None
    ) -> ReflectionRecord:
        """生成反思记录 - 委托给工作流编排器"""
        try:
            reflection = self._orchestrator.generate_reflection(
                subject=subject,
                reflection_type=reflection_type,
                context=context,
                trigger=trigger,
                trace_id=trace_id,
                session_id=session_id,
                template_id=template_id
            )
            
            if self.persistence:
                self.persistence.save_reflection(reflection)
            
            self._reflection_cache[reflection.reflection_id] = reflection
            return reflection
            
        except Exception as e:
            logger.error(f"Failed to generate reflection: {e}")
            raise ReflectionGenerationError(f"Reflection generation failed: {e}")
    
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
        
        if self.persistence:
            reflection = self.persistence.get_reflection(reflection_id)
            if reflection:
                self._reflection_cache[reflection_id] = reflection
                return reflection
        
        raise ValueError(f"Reflection not found: {reflection_id}")
    
    def list_reflections(self, filters: Optional[Dict[str, Any]] = None) -> List[ReflectionRecord]:
        """列出反思记录"""
        if self.persistence:
            return self.persistence.query_reflections(filters or {})
        return list(self._reflection_cache.values())
    
    def update_reflection(self, reflection_id: str, updates: Dict[str, Any]) -> ReflectionRecord:
        """更新反思记录"""
        reflection = self.get_reflection(reflection_id)
        
        for key, value in updates.items():
            if hasattr(reflection, key):
                setattr(reflection, key, value)
        
        if self.persistence:
            self.persistence.save_reflection(reflection)
        
        self._reflection_cache[reflection_id] = reflection
        return reflection
    
    def delete_reflection(self, reflection_id: str) -> bool:
        """删除反思记录"""
        if self.persistence:
            success = self.persistence.delete_reflection(reflection_id)
            if success and reflection_id in self._reflection_cache:
                del self._reflection_cache[reflection_id]
            return success
        
        if reflection_id in self._reflection_cache:
            del self._reflection_cache[reflection_id]
            return True
        return False
    
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
        
        if self.persistence:
            self.persistence.save_reflection(reflection)
        
        return reflection
    
    def mark_suspect(self, reflection_id: str, reason: str) -> ReflectionRecord:
        """标记可疑"""
        reflection = self.get_reflection(reflection_id)
        reflection.governance_status = GovernanceStatus.SUSPECT
        reflection.suspect_reason = reason
        
        if self.persistence:
            self.persistence.save_reflection(reflection)
        
        return reflection
    
    def archive_reflection(self, reflection_id: str) -> ReflectionRecord:
        """归档反思"""
        reflection = self.get_reflection(reflection_id)
        reflection.governance_status = GovernanceStatus.ARCHIVED
        
        if self.persistence:
            self.persistence.save_reflection(reflection)
        
        return reflection
    
    def get_metrics(self) -> ReflectionMetrics:
        """获取指标 - 委托给metrics_calculator"""
        reflections = self.list_reflections()
        metrics = self._metrics_calculator.calculate_metrics(reflections)
        
        if self.persistence:
            self.persistence.save_metrics(metrics)
        
        return metrics
    
    def should_update_reflection_list(self, reflection: ReflectionRecord) -> bool:
        """判断是否更新反思列表 - 委托给update_policy"""
        return self._update_policy.should_update_reflection_list(reflection)


# Global singleton instance for reflection service
_default_service: ReflectionService | None = None


def get_service() -> ReflectionService:
    """Standard service factory function for launcher assembly.
    
    Returns the global ReflectionService instance, creating it if necessary.
    This function is required by the SystemAssembler to initialize the reflection service.
    """
    global _default_service
    if _default_service is None:
        _default_service = ReflectionService()
    return _default_service
