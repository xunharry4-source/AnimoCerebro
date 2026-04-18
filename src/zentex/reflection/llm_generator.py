"""
LLM驱动的反思内容生成器

RESPONSIBILITY:
  Orchestrates LLM calls for reflection generation.  Prompt construction and
  content preprocessing are fully delegated to zentex.reflection.llm_prompt —
  this module MUST NOT build or inline any prompt string sent to the LLM.

DOES NOT:
  - Build prompt strings (see llm_prompt.py).
  - Preprocess or truncate input context (see llm_prompt.py).
  - Own service lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from zentex.reflection.models import ReflectionType
from zentex.reflection.llm_prompt import (
    build_reflection_prompt,
    build_type_specific_guidance,
)

logger = logging.getLogger(__name__)


class LLMReflectionGenerator:
    """
    基于LLM的反思内容生成器
    
    使用大语言模型生成深度、个性化的反思内容，包括洞察、教训、风险和改进建议。
    """
    
    def __init__(
        self,
        llm_service=None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ):
        """
        初始化LLM反思生成器
        
        Args:
            llm_service: LLM服务实例（如果为None则自动获取）
            temperature: LLM采样温度（0-1，越低越确定）
            max_tokens: 最大输出token数
        """
        self._temperature = temperature
        self._max_tokens = max_tokens
        
        if llm_service is None:
            try:
                from zentex.llm import get_llm_service
                self._llm_service = get_llm_service()
                logger.info("LLMReflectionGenerator initialized with global LLM service")
            except Exception as e:
                logger.error(f"Failed to initialize LLM service: {e}")
                raise
        else:
            self._llm_service = llm_service
            logger.info("LLMReflectionGenerator initialized with provided LLM service")
    
    def generate_reflection(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用LLM生成深度反思内容

        Args:
            subject: 反思主题
            reflection_type: 反思类型
            context: 反思上下文数据（将由 llm_prompt 模块预处理后再传入 LLM）

        Returns:
            包含summary, insights, lessons, risks, improvements等的字典
        """
        # 所有提示词构建和内容预处理委托给 llm_prompt 模块
        type_guidance = build_type_specific_guidance(reflection_type.value, context)
        prompt = build_reflection_prompt(
            subject=subject,
            reflection_type_value=reflection_type.value,
            reflection_type_name=self._get_reflection_type_name(reflection_type),
            context=context,
            type_specific_guidance=type_guidance,
        )
        
        # 调用LLM生成结构化JSON
        try:
            result = self._llm_service.generate_json(
                prompt=prompt,
                context=context,
                source_module="reflection_service",
                invocation_phase=f"{reflection_type.value}_reflection_generation",
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                metadata={
                    "subject": subject,
                    "reflection_type": reflection_type.value,
                    "context_keys": list(context.keys())
                }
            )
            
            # 解析并验证LLM输出
            output = result.output
            validated_output = self._validate_and_normalize(output, subject)
            
            logger.info(f"LLM reflection generated successfully for: {subject}")
            return validated_output
            
        except Exception as e:
            logger.error(f"LLM reflection generation failed: {e}")
            raise
    
    def _get_reflection_type_name(self, reflection_type: ReflectionType) -> str:
        """获取反思类型的中文名称"""
        type_names = {
            ReflectionType.DECISION_REFLECTION: "决策",
            ReflectionType.ACTION_REFLECTION: "行动执行",
            ReflectionType.OUTCOME_REFLECTION: "结果评估",
            ReflectionType.PROCESS_REFLECTION: "流程优化",
            ReflectionType.STRATEGY_REFLECTION: "战略规划",
            ReflectionType.ERROR_REFLECTION: "错误分析",
            ReflectionType.SUCCESS_REFLECTION: "成功经验",
            ReflectionType.LEARNING_REFLECTION: "学习总结",
        }
        return type_names.get(reflection_type, "事件")
    
    def _validate_and_normalize(
        self,
        output: Dict[str, Any],
        subject: str
    ) -> Dict[str, Any]:
        """
        验证和规范化LLM输出
        
        Args:
            output: LLM原始输出
            subject: 反思主题
            
        Returns:
            验证后的规范化输出
        """
        # 确保必要字段存在
        validated = {
            "summary": output.get("summary", f"关于'{subject}'的反思分析"),
            "insights": output.get("insights", []),
            "lessons": output.get("lessons", []),
            "risks": output.get("risks", []),
            "improvements": output.get("improvements", []),
        }
        
        # 确保列表类型
        for key in ["insights", "lessons", "risks", "improvements"]:
            if not isinstance(validated[key], list):
                validated[key] = [str(validated[key])] if validated[key] else []
        
        # 验证数值范围
        confidence = float(output.get("confidence", 0.7))
        validated["confidence"] = max(0.0, min(1.0, confidence))
        
        impact_score = float(output.get("impact_score", 0.6))
        validated["impact_score"] = max(0.0, min(1.0, impact_score))
        
        actionability = float(output.get("actionability", 0.5))
        validated["actionability"] = max(0.0, min(1.0, actionability))
        
        # 质量检查：如果内容为空，记录警告
        if not validated["insights"] and not validated["lessons"]:
            logger.warning(f"LLM generated empty insights/lessons for: {subject}")
        
        return validated


# 全局单例（可选）
_default_generator = None


def get_llm_reflection_generator() -> LLMReflectionGenerator:
    """
    获取全局LLM反思生成器实例
    
    Returns:
        LLMReflectionGenerator实例
    """
    global _default_generator
    if _default_generator is None:
        _default_generator = LLMReflectionGenerator()
    return _default_generator
