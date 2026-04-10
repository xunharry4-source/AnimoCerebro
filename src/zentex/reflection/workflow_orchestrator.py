"""
反思工作流编排器

负责协调各个业务模块完成完整的反思生成流程。
Service层应该只调用这个编排器，而不包含任何编排逻辑。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zentex.reflection.models import (
    ReflectionRecord, ReflectionTemplate, ReflectionType, ReflectionTrigger,
    create_reflection_id
)
from zentex.reflection.llm_generator import LLMReflectionGenerator
from zentex.reflection.quality_assessor import ReflectionQualityAssessor
from zentex.reflection.data_sync import ReflectionDataSync
from zentex.reflection.template_manager import ReflectionTemplateManager
from zentex.reflection.metrics_calculator import MetaAuditGenerator

logger = logging.getLogger(__name__)


class ReflectionWorkflowOrchestrator:
    """
    反思工作流编排器
    
    协调LLM生成、质量评估、数据同步等步骤，完成完整的反思生成流程。
    Service层只需调用此编排器的方法，无需关心内部细节。
    """
    
    def __init__(
        self,
        llm_generator: LLMReflectionGenerator,
        quality_assessor: ReflectionQualityAssessor,
        data_sync: ReflectionDataSync,
        template_mgr: ReflectionTemplateManager,
        meta_audit: MetaAuditGenerator
    ):
        """
        初始化工作流编排器
        
        Args:
            llm_generator: LLM生成器
            quality_assessor: 质量评估器
            data_sync: 数据同步器
            template_mgr: 模板管理器
            meta_audit: 元审计生成器
        """
        self._llm_generator = llm_generator
        self._quality_assessor = quality_assessor
        self._data_sync = data_sync
        self._template_mgr = template_mgr
        self._meta_audit = meta_audit
    
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
        """
        生成完整的反思记录
        
        这是核心工作流方法，按顺序执行：
        1. 获取模板（可选）
        2. LLM生成反思内容
        3. 评估深度和质量
        4. 创建反思记录
        5. 数据同步（旧格式→新格式）
        6. 添加核心固定项目
        7. 添加元反思审计
        8. 反向同步（新格式→旧格式，向后兼容）
        
        Args:
            subject: 反思主题
            reflection_type: 反思类型
            context: 反思上下文
            trigger: 触发器
            trace_id: 追踪ID
            session_id: 会话ID
            template_id: 模板ID
            
        Returns:
            生成的反思记录
        """
        # 步骤1：获取模板（可选）
        template = None
        if template_id:
            template = self._template_mgr.get_template(template_id)
        
        # 步骤2：LLM生成反思内容
        reflection_content = self._llm_generator.generate_reflection(
            subject=subject,
            reflection_type=reflection_type,
            context=context
        )
        
        # 步骤3：评估深度和质量
        depth = self._quality_assessor.determine_depth(context)
        quality = self._quality_assessor.assess_quality(reflection_content)
        
        # 步骤4：创建反思记录
        reflection = ReflectionRecord(
            reflection_id=create_reflection_id(),
            trace_id=trace_id,
            session_id=session_id,
            reflection_type=reflection_type,
            depth=depth,
            quality=quality,
            trigger=trigger,
            reflection_timestamp=datetime.now(timezone.utc),
            subject=subject,
            context=context,
            **reflection_content
        )
        
        # 步骤5-8：数据后处理
        self._post_process_reflection(reflection)
        
        logger.info(f"Generated reflection: {reflection.reflection_id}")
        return reflection
    
    def _post_process_reflection(self, reflection: ReflectionRecord) -> None:
        """
        反思记录后处理
        
        执行数据同步、核心项目添加、元审计等步骤。
        
        Args:
            reflection: 反思记录
        """
        # 步骤5：数据同步（旧格式→新格式）
        self._data_sync.sync_legacy_to_list(reflection)
        
        # 步骤6：添加核心固定项目
        self._data_sync.ensure_core_fixed_items(reflection)
        
        # 步骤7：添加元反思审计
        meta_item = self._meta_audit.generate_meta_audit_item(reflection)
        reflection.reflection_list.append(meta_item)
        
        # 步骤8：反向同步（新格式→旧格式，向后兼容）
        self._data_sync.sync_list_to_legacy(reflection)
