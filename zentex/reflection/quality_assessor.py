"""
反思质量评估器

负责评估反思的深度、质量和可操作性。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from zentex.reflection.models import ReflectionDepth, ReflectionQuality

logger = logging.getLogger(__name__)


class ReflectionQualityAssessor:
    """
    反思质量评估器
    
    根据上下文和内容评估反思的质量和深度。
    """
    
    def determine_depth(self, context: Dict[str, Any]) -> ReflectionDepth:
        """
        根据上下文确定反思深度
        
        Args:
            context: 反思上下文
            
        Returns:
            反思深度级别
        """
        # 基于上下文复杂度判断
        complexity_score = self._calculate_complexity(context)
        
        if complexity_score > 0.7:
            return ReflectionDepth.SYSTEMIC
        elif complexity_score > 0.4:
            return ReflectionDepth.STRATEGIC
        else:
            return ReflectionDepth.ANALYTICAL
    
    def assess_quality(self, content: Dict[str, Any]) -> ReflectionQuality:
        """
        评估反思内容质量
        
        Args:
            content: 反思内容字典
            
        Returns:
            质量等级
        """
        # 基于内容丰富度评估
        richness_score = self._calculate_richness(content)
        
        if richness_score > 0.8:
            return ReflectionQuality.EXCELLENT
        elif richness_score > 0.6:
            return ReflectionQuality.GOOD
        elif richness_score > 0.4:
            return ReflectionQuality.FAIR
        else:
            return ReflectionQuality.POOR
    
    def _calculate_complexity(self, context: Dict[str, Any]) -> float:
        """
        计算上下文复杂度（0-1）
        
        Args:
            context: 反思上下文
            
        Returns:
            复杂度分数
        """
        score = 0.0
        
        # 因素数量
        factors = context.get("decision", {}).get("factors", [])
        if len(factors) > 5:
            score += 0.3
        elif len(factors) > 2:
            score += 0.15
        
        # 备选方案数量
        alternatives = context.get("alternatives", [])
        if len(alternatives) > 3:
            score += 0.3
        elif len(alternatives) > 1:
            score += 0.15
        
        # 是否有历史数据
        if "history" in context or "previous_outcomes" in context:
            score += 0.2
        
        # 是否有利益相关者
        if "stakeholders" in context:
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_richness(self, content: Dict[str, Any]) -> float:
        """
        计算内容丰富度（0-1）
        
        Args:
            content: 反思内容
            
        Returns:
            丰富度分数
        """
        score = 0.0
        
        # 洞察数量和质量
        insights = content.get("insights", [])
        if len(insights) >= 3:
            score += 0.3
        elif len(insights) >= 1:
            score += 0.15
        
        # 教训数量
        lessons = content.get("lessons", [])
        if len(lessons) >= 2:
            score += 0.2
        elif len(lessons) >= 1:
            score += 0.1
        
        # 风险识别
        risks = content.get("risks", [])
        if len(risks) >= 2:
            score += 0.2
        elif len(risks) >= 1:
            score += 0.1
        
        # 改进建议
        improvements = content.get("improvements", [])
        if len(improvements) >= 2:
            score += 0.2
        elif len(improvements) >= 1:
            score += 0.1
        
        # 置信度和影响力
        confidence = content.get("confidence", 0)
        impact = content.get("impact_score", 0)
        score += (confidence + impact) * 0.1
        
        return min(score, 1.0)
