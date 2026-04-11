"""
反思数据同步器

负责反思列表与旧格式之间的数据同步，以及核心固定项目的管理。
"""

from __future__ import annotations

import logging
from typing import List

from zentex.reflection.models import ReflectionRecord, ReflectionItem, CORE_FIXED_REFLECTION_ITEMS

logger = logging.getLogger(__name__)


class ReflectionDataSync:
    """
    反思数据同步器
    
    处理反思列表的结构化数据与旧格式字符串列表之间的同步。
    """
    
    def sync_legacy_to_list(self, reflection: ReflectionRecord) -> None:
        """
        将旧格式的字符串列表同步到结构化的reflection_list
        
        仅在reflection_list为空时执行，避免重复同步。
        
        Args:
            reflection: 反思记录
        """
        # 如果已经有反思列表，跳过同步（避免重复添加）
        if reflection.reflection_list:
            return
        
        for text in reflection.insights:
            reflection.reflection_list.append(ReflectionItem(
                content=text, 
                category="insight",
                name="Insight"
            ))
        for text in reflection.lessons:
            reflection.reflection_list.append(ReflectionItem(
                content=text, 
                category="lesson",
                name="Lesson"
            ))
        for text in reflection.risks:
            reflection.reflection_list.append(ReflectionItem(
                content=text, 
                category="risk",
                name="Risk"
            ))
        for text in reflection.improvements:
            reflection.reflection_list.append(ReflectionItem(
                content=text, 
                category="improvement",
                name="Improvement"
            ))
    
    def ensure_core_fixed_items(self, reflection: ReflectionRecord) -> None:
        """
        确保核心固定项目存在
        
        仅在缺失时添加，不重复添加。核心项目不可删除和修改。
        
        Args:
            reflection: 反思记录
        """
        existing_item_ids = {item.item_id for item in reflection.reflection_list}
        
        for core_item in CORE_FIXED_REFLECTION_ITEMS:
            if core_item.item_id not in existing_item_ids:
                # 添加核心项目的副本，保持独立性
                reflection.reflection_list.append(core_item.copy())
                logger.debug(f"Added core fixed item: {core_item.name}")
    
    def sync_list_to_legacy(self, reflection: ReflectionRecord) -> None:
        """
        将结构化的reflection_list同步回旧格式的字符串列表
        
        用于向后兼容旧版UI。
        
        Args:
            reflection: 反思记录
        """
        # 清空旧格式列表以避免重复
        reflection.insights = []
        reflection.lessons = []
        reflection.risks = []
        reflection.improvements = []
        
        for item in reflection.reflection_list:
            if item.category == "insight":
                reflection.insights.append(item.content)
            elif item.category == "lesson":
                reflection.lessons.append(item.content)
            elif item.category == "risk":
                reflection.risks.append(item.content)
            elif item.category in ["improvement", "meta", "safety"]:
                # 将meta和safety映射到improvements以在通用UI中可见
                label = f"[{item.category.upper()}] " if item.category in ["meta", "safety"] else ""
                reflection.improvements.append(f"{label}{item.content}")
