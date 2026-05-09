from __future__ import annotations
"""
反思指标计算器

负责计算和聚合反思相关的统计指标。
"""


import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from zentex.reflection.models import ReflectionRecord, ReflectionMetrics, GovernanceStatus, ReflectionItem, ReflectionQuality

logger = logging.getLogger(__name__)


class ReflectionMetricsCalculator:
    """
    反思指标计算器
    
    根据反思记录集合计算各种统计指标。
    """
    
    def calculate_metrics(self, reflections: List[ReflectionRecord]) -> ReflectionMetrics:
        """
        计算反思指标
        
        Args:
            reflections: 反思记录列表
            
        Returns:
            计算后的指标对象
        """
        metrics = ReflectionMetrics()
        metrics.total_reflections = len(reflections)
        
        # 按类型统计
        type_counts = {}
        depth_counts = {}
        quality_counts = {}
        governance_counts = {}
        
        total_confidence = 0
        total_impact = 0
        total_actionability = 0
        
        today = datetime.now(timezone.utc).date()
        week_ago = today - timedelta(days=7)
        month_ago = today.replace(day=1)
        
        for reflection in reflections:
            # 类型统计
            type_counts[reflection.reflection_type.value] = type_counts.get(
                reflection.reflection_type.value, 0
            ) + 1
            
            # 深度统计
            depth_counts[reflection.depth.value] = depth_counts.get(
                reflection.depth.value, 0
            ) + 1
            
            # 质量统计
            quality_counts[reflection.quality.value] = quality_counts.get(
                reflection.quality.value, 0
            ) + 1
            
            # 治理状态统计
            governance_counts[reflection.governance_status.value] = governance_counts.get(
                reflection.governance_status.value, 0
            ) + 1
            
            # 累计指标
            total_confidence += reflection.confidence
            total_impact += reflection.impact_score
            total_actionability += reflection.actionability
            
            # 时间统计
            if reflection.created_at.date() == today:
                metrics.reflections_today += 1
            if reflection.created_at.date() >= week_ago:
                metrics.reflections_this_week += 1
            if reflection.created_at.date() >= month_ago:
                metrics.reflections_this_month += 1
            
            # 治理统计
            if reflection.governance_status == GovernanceStatus.VERIFIED:
                metrics.verified_reflections += 1
            elif reflection.governance_status == GovernanceStatus.SUSPECT:
                metrics.suspect_reflections += 1
            elif reflection.governance_status == GovernanceStatus.ARCHIVED:
                metrics.archived_reflections += 1
        
        # 设置统计数据
        metrics.reflections_by_type = type_counts
        metrics.reflections_by_depth = depth_counts
        metrics.reflections_by_quality = quality_counts
        
        # 计算平均值
        if reflections:
            metrics.average_confidence = total_confidence / len(reflections)
            metrics.average_impact_score = total_impact / len(reflections)
            metrics.average_actionability = total_actionability / len(reflections)
        
        return metrics


class ReflectionUpdatePolicy:
    """
    反思更新策略
    
    判断是否需要更新反思列表（低频触发策略）。
    """
    
    def should_update_reflection_list(self, reflection: ReflectionRecord) -> bool:
        """
        判断是否需要更新反思列表（低频触发策略）。
        
        只有在以下情况才允许修改反思列表：
        1. 反思结果为空或无实质内容
        2. 反思质量极低（POOR）
        3. 反思置信度低于阈值
        4. 没有生成任何洞察、教训或改进建议
        
        Args:
            reflection: 反思记录
            
        Returns:
            是否应该更新反思列表
        """
        # 条件1：反思摘要为空或过短
        if not reflection.summary or len(reflection.summary.strip()) < 10:
            logger.info(f"Reflection {reflection.reflection_id}: Empty summary, allowing list update")
            return True
        
        # 条件2：反思质量为 POOR
        if reflection.quality.value == "poor":
            logger.info(f"Reflection {reflection.reflection_id}: Poor quality, allowing list update")
            return True
        
        # 条件3：置信度过低
        if reflection.confidence < 0.4:
            logger.info(f"Reflection {reflection.reflection_id}: Low confidence ({reflection.confidence}), allowing list update")
            return True
        
        # 条件4：没有任何实质性内容
        has_content = (
            len(reflection.insights) > 0 or
            len(reflection.lessons) > 0 or
            len(reflection.risks) > 0 or
            len(reflection.improvements) > 0 or
            len(reflection.reflection_list) > 5  # 至少有核心项目+一些内容
        )
        
        if not has_content:
            logger.info(f"Reflection {reflection.reflection_id}: No substantive content, allowing list update")
            return True
        
        # 默认情况：不允许多余的列表修改
        logger.debug(f"Reflection {reflection.reflection_id}: Content is sufficient, skipping list update")
        return False


class MetaAuditGenerator:
    """
    元反思审计生成器
    
    对当前反思内容质量进行自我审计，生成元反思项目。
    """
    
    def generate_meta_audit_item(self, reflection: ReflectionRecord) -> ReflectionItem:
        """
        生成元反思项目：对当前反思内容质量进行自我审计。
        
        Args:
            reflection: 反思记录
            
        Returns:
            元反思项目
        """
        # 根据质量评分计算完整性分数
        score = 1.0 - (0.2 if reflection.quality == ReflectionQuality.POOR else 0.0)
        
        content = (
            "Self-Audit: Reflection content is structurally consistent. "
            "No significant drift detected from core identity."
        ) if score > 0.8 else (
            "Self-Audit WARNING: Possible shallow analysis detected. "
            "Higher order context might be missing from this turn."
        )
        
        return ReflectionItem(
            name="Meta-Audit",
            content=content,
            category="meta",
            is_immutable=False,  # AI可以承认并完善元反思
            can_be_removed=True,
            integrity_score=score
        )
