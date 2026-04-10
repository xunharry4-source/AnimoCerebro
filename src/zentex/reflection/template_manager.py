"""
反思模板管理器

负责管理反思模板的创建、查询和更新。
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from zentex.reflection.models import ReflectionTemplate, ReflectionType, ReflectionDepth

logger = logging.getLogger(__name__)


class ReflectionTemplateManager:
    """
    反思模板管理器
    
    管理预定义的反思模板，支持按类型和ID查询。
    """
    
    def __init__(self):
        """初始化模板管理器"""
        self._templates: Dict[str, ReflectionTemplate] = {}
        self._initialize_default_templates()
    
    def get_template(self, template_id: str) -> Optional[ReflectionTemplate]:
        """
        获取指定ID的模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板对象，如果不存在则返回None
        """
        return self._templates.get(template_id)
    
    def get_template_by_type(self, reflection_type: ReflectionType) -> Optional[ReflectionTemplate]:
        """
        根据反思类型获取默认模板
        
        Args:
            reflection_type: 反思类型
            
        Returns:
            对应的模板对象
        """
        for template in self._templates.values():
            if template.applicable_types and reflection_type in template.applicable_types:
                return template
        return None
    
    def list_templates(self) -> Dict[str, ReflectionTemplate]:
        """
        列出所有可用模板
        
        Returns:
            模板字典
        """
        return self._templates.copy()
    
    def _initialize_default_templates(self) -> None:
        """初始化默认模板"""
        try:
            # 决策反思模板
            decision_template = ReflectionTemplate(
                template_id="default_decision",
                name="决策反思模板",
                description="用于决策过程的深度反思",
                reflection_type=ReflectionType.DECISION_REFLECTION,
                required_fields=["summary", "insights", "lessons"],
                optional_fields=["risks", "improvements"],
                prompt_template="请对这个决策进行深度反思...",
                applicable_types=[ReflectionType.DECISION_REFLECTION],
                suggested_depth=ReflectionDepth.STRATEGIC,
                guidance_notes=[
                    "分析决策依据是否充分",
                    "评估备选方案的完整性",
                    "考虑长期影响和风险"
                ]
            )
            self._templates[decision_template.template_id] = decision_template
            
            # 错误反思模板
            error_template = ReflectionTemplate(
                template_id="default_error",
                name="错误反思模板",
                description="用于错误分析和预防",
                reflection_type=ReflectionType.ERROR_REFLECTION,
                required_fields=["summary", "insights", "lessons"],
                optional_fields=["risks", "improvements"],
                prompt_template="请对这个错误进行根因分析...",
                applicable_types=[ReflectionType.ERROR_REFLECTION],
                suggested_depth=ReflectionDepth.SYSTEMIC,
                guidance_notes=[
                    "识别根本原因而非表面症状",
                    "评估系统性风险",
                    "制定预防措施"
                ]
            )
            self._templates[error_template.template_id] = error_template
            
            # 成功反思模板
            success_template = ReflectionTemplate(
                template_id="default_success",
                name="成功反思模板",
                description="用于成功经验总结",
                reflection_type=ReflectionType.SUCCESS_REFLECTION,
                required_fields=["summary", "insights", "lessons"],
                optional_fields=["risks", "improvements"],
                prompt_template="请总结这次成功的关键因素...",
                applicable_types=[ReflectionType.SUCCESS_REFLECTION],
                suggested_depth=ReflectionDepth.STRATEGIC,
                guidance_notes=[
                    "识别关键成功因素",
                    "评估可复制性",
                    "标准化最佳实践"
                ]
            )
            self._templates[success_template.template_id] = success_template
            
            logger.info(f"Initialized {len(self._templates)} default templates")
            
        except Exception as e:
            logger.warning(f"Failed to create default templates: {e}")
