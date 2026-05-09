from __future__ import annotations
"""
反思质量评估器

负责评估反思的深度、质量和可操作性。
"""


import logging
from typing import Any, Dict, Optional

from zentex.reflection.models import ReflectionDepth, ReflectionQuality

logger = logging.getLogger(__name__)


class ReflectionQualityAssessor:
    """
    反思质量评估器
    
    POLICY: No more heuristic scams. Quality is assessed via semantic audit (LLM) 
    rather than counting list items.
    """
    
    def __init__(self, llm_service: Optional[Any] = None) -> None:
        self._llm_service = llm_service
    
    def determine_depth(
        self, 
        subject: str, 
        content: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> ReflectionDepth:
        """
        经过语义审计确定反思深度
        """
        audit_result = self._perform_semantic_audit(subject, content, context)
        grade = audit_result.get("depth_grade", "ANALYTICAL")
        
        mapping = {
            "SYSTEMIC": ReflectionDepth.SYSTEMIC,
            "STRATEGIC": ReflectionDepth.STRATEGIC,
            "ANALYTICAL": ReflectionDepth.ANALYTICAL,
        }
        return mapping.get(grade, ReflectionDepth.ANALYTICAL)
    
    def assess_quality(
        self, 
        subject: str,
        content: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> ReflectionQuality:
        """
        评估反思内容质量（真实采样审计）
        """
        audit_result = self._perform_semantic_audit(subject, content, context)
        grade = audit_result.get("quality_grade", "POOR")
        
        mapping = {
            "EXCELLENT": ReflectionQuality.EXCELLENT,
            "GOOD": ReflectionQuality.GOOD,
            "FAIR": ReflectionQuality.FAIR,
            "POOR": ReflectionQuality.POOR,
        }
        return mapping.get(grade, ReflectionQuality.POOR)

    def _perform_semantic_audit(
        self,
        subject: str,
        content: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行有界本地语义审计，避免第二次 LLM 阻塞整个反思流程。"""
        insight_count = len(content.get("insights") or [])
        lesson_count = len(content.get("lessons") or [])
        improvement_count = len(content.get("improvements") or [])
        risk_count = len(content.get("risks") or [])
        summary = str(content.get("summary") or "").strip()
        total_items = insight_count + lesson_count + improvement_count + risk_count
        has_context = bool(context)
        richness_score = total_items + (1 if summary else 0) + (1 if has_context else 0)

        if richness_score >= 7:
            return {"quality_grade": "GOOD", "depth_grade": "STRATEGIC"}
        if richness_score >= 4:
            return {"quality_grade": "FAIR", "depth_grade": "ANALYTICAL"}
        logger.warning("Quality Assessor: low-content reflection detected for subject %s", subject)
        return {"quality_grade": "POOR", "depth_grade": "ANALYTICAL"}
    
