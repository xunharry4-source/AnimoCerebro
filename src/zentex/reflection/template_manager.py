from __future__ import annotations
"""
反思模板管理器

负责管理反思模板的创建、查询和更新。
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

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

    def create_template(
        self,
        name: str,
        description: str,
        template_data: Dict[str, Any],
    ) -> ReflectionTemplate:
        """创建反思模板并写入内存仓。"""
        template_id = f"tpl_{uuid4().hex[:12]}"

        reflection_type_raw = template_data.get("reflection_type")
        if isinstance(reflection_type_raw, ReflectionType):
            reflection_type = reflection_type_raw
        elif isinstance(reflection_type_raw, str):
            reflection_type = ReflectionType(reflection_type_raw)
        else:
            reflection_type = ReflectionType.LEARNING_REFLECTION

        required_fields = template_data.get("required_fields")
        if not isinstance(required_fields, list) or not required_fields:
            required_fields = ["summary", "insights", "lessons"]

        optional_fields = template_data.get("optional_fields")
        if not isinstance(optional_fields, list):
            optional_fields = []

        prompt_template = str(
            template_data.get("prompt_template")
            or f"请围绕主题生成{name}相关反思，输出摘要、洞察与经验。"
        )

        applicable_types_raw = template_data.get("applicable_types")
        applicable_types = []
        if isinstance(applicable_types_raw, list):
            for item in applicable_types_raw:
                if isinstance(item, ReflectionType):
                    applicable_types.append(item)
                elif isinstance(item, str):
                    applicable_types.append(ReflectionType(item))
        if not applicable_types:
            applicable_types = [reflection_type]

        suggested_depth_raw = template_data.get("suggested_depth")
        suggested_depth: Optional[ReflectionDepth] = None
        if isinstance(suggested_depth_raw, ReflectionDepth):
            suggested_depth = suggested_depth_raw
        elif isinstance(suggested_depth_raw, str):
            suggested_depth = ReflectionDepth(suggested_depth_raw)

        guidance_notes = template_data.get("guidance_notes")
        if not isinstance(guidance_notes, list):
            guidance_notes = []

        template = ReflectionTemplate(
            template_id=template_id,
            name=name,
            description=description,
            reflection_type=reflection_type,
            required_fields=required_fields,
            optional_fields=optional_fields,
            prompt_template=prompt_template,
            applicable_types=applicable_types,
            suggested_depth=suggested_depth,
            guidance_notes=guidance_notes,
            evaluation_criteria=template_data.get("evaluation_criteria", {}),
            tags=template_data.get("tags", []),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._templates[template_id] = template
        return template
    
    def _initialize_default_templates(self) -> None:
        """初始化默认模板"""
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
