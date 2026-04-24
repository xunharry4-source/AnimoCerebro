from __future__ import annotations
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


import logging
from typing import Any, Dict, Optional, List, Union

from zentex.foundation.specs.model_provider import ModelProviderTimeoutError
from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.reflection.models import ReflectionType
from zentex.reflection.llm_prompt import (
    build_reflection_prompt,
    build_maintenance_synthesis_prompt,
    build_type_specific_guidance,
)

logger = logging.getLogger(__name__)

_REFLECTION_LLM_TIMEOUT_SECONDS = 8.0
_TIMEOUT_FALLBACK_PROVIDER_ORDER = ("gemini", "openai_compat")
_TIMEOUT_FALLBACK_MODELS = {
    "openai_compat": "gemini-3-flash",
}


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
        decision_id = f"reflection:{subject}:{reflection_type.value}"
        logger.info(f"[REFLECTION AUDIT] Generating {reflection_type.value} reflection for subject: {subject}")
        
        try:
            caller_context = ModelProviderCallerContext(
                source_module="reflection_service",
                invocation_phase=f"{reflection_type.value}_reflection_generation",
                decision_id=decision_id,
            )
            metadata = {
                "subject": subject,
                "reflection_type": reflection_type.value,
                "context_keys": list(context.keys()),
                "request_timeout_seconds": _REFLECTION_LLM_TIMEOUT_SECONDS,
            }
            result = self._invoke_with_timeout_fallback(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                metadata=metadata,
            )
            
            # 解析并验证LLM输出
            output = result.output
            validated_output = self._validate_and_normalize(output, subject)
            
            logger.info(f"[REFLECTION AUDIT] Reflection generated Union[successfully, Subject]: {subject} | Trace: {result.provider_key}")
            return validated_output
            
        except Exception as e:
            logger.error(f"[REFLECTION AUDIT] Reflection generation Union[failed, Subject]: {subject} | Error: {e}")
            return self._build_fallback_reflection(subject, reflection_type, context, error=e)

    def synthesize_maintenance_insights(
        self,
        *,
        top_tags: List[str],
        titles: List[str],
        layer_distribution: Dict[str, Any],
        unverified_count: int,
    ) -> Dict[str, Any]:
        """Call the LLM to produce semantic maintenance insights from memory statistics.

        Returns a dict with keys: summary, insights, lessons, improvements.
        On any LLM failure, returns an empty dict so the caller can fall back
        to its counter-based values — no silent swallowing.
        """
        prompt = build_maintenance_synthesis_prompt(
            top_tags=top_tags,
            titles=titles,
            layer_distribution=layer_distribution,
            unverified_count=unverified_count,
        )
        caller_context = ModelProviderCallerContext(
            source_module="reflection_service.maintenance",
            invocation_phase="memory_maintenance_synthesis",
            decision_id="reflection-maintenance-synthesis",
        )
        try:
            result = self._invoke_with_timeout_fallback(
                prompt=prompt,
                context={},
                caller_context=caller_context,
                metadata={"top_tags": top_tags, "title_count": len(titles)},
            )
            output = result.output if result is not None else {}
            if not isinstance(output, dict):
                logger.warning(
                    "synthesize_maintenance_insights: LLM returned non-dict output (%s); ignoring",
                    type(output).__name__,
                )
                return {}
            return output
        except Exception:
            logger.warning("synthesize_maintenance_insights: LLM call failed; falling back to counter-based insights", exc_info=True)
            return {}

    def _invoke_with_timeout_fallback(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        metadata: Dict[str, Any],
    ) -> Any:
        try:
            return self._invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                metadata=metadata,
                provider_key=None,
                model=None,
            )
        except ModelProviderTimeoutError as primary_exc:
            logger.warning(
                "Reflection LLM timed out on primary provider; trying online fallback providers: %s",
                ", ".join(_TIMEOUT_FALLBACK_PROVIDER_ORDER),
            )
            last_exc: Exception = primary_exc
            primary_provider = self._resolve_default_provider_key()
            for provider_key in _TIMEOUT_FALLBACK_PROVIDER_ORDER:
                if provider_key == primary_provider:
                    continue
                try:
                    return self._invoke_generate_json(
                        prompt=prompt,
                        context=context,
                        caller_context=caller_context,
                        metadata=metadata,
                        provider_key=provider_key,
                        model=_TIMEOUT_FALLBACK_MODELS.get(provider_key),
                    )
                except Exception as fallback_exc:
                    last_exc = fallback_exc
                    logger.warning(
                        "Reflection LLM fallback provider failed | provider=%s error=%s",
                        provider_key,
                        fallback_exc,
                    )
            raise last_exc

    def _invoke_generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        metadata: Dict[str, Any],
        provider_key: Optional[str],
        model: Optional[str],
    ) -> Any:
        gateway = getattr(self._llm_service, "_gateway", None)
        if gateway is not None and callable(getattr(gateway, "invoke_generate_json", None)):
            return gateway.invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                provider_key=provider_key,
                model=model,
                system_prompt=None,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                metadata=metadata,
            )
        return self._llm_service.generate_json(
            prompt=prompt,
            context=context,
            caller_context=caller_context,
            source_module=caller_context.source_module,
            invocation_phase=caller_context.invocation_phase,
            decision_id=caller_context.decision_id,
            model_provider=provider_key,
            model=model,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            metadata=metadata,
        )

    def _resolve_default_provider_key(self) -> Optional[str]:
        gateway = getattr(self._llm_service, "_gateway", None)
        return getattr(gateway, "_default_provider_key", None)
    
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

    def _build_fallback_reflection(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        *,
        error: Exception,
    ) -> Dict[str, Any]:
        """Build a deterministic reflection when the LLM path times out or fails."""
        summary = str(context.get("summary") or f"关于“{subject}”的{self._get_reflection_type_name(reflection_type)}反思")
        question_id = str(context.get("question_id") or "").strip()
        subject_text = str(subject or "").strip()
        subject_hint = subject_text or "当前事件"
        context_keys = sorted(str(key) for key in context.keys())
        insight = f"{subject_hint} 已进入反思流程，当前上下文包含 {len(context_keys)} 个字段。"
        if question_id:
            insight = f"{subject_hint} 关联问题 {question_id}，需要围绕该问题的上下文持续校准。"
        lesson = "优先保留可追踪上下文与明确主题，再逐步补充更深层分析。"
        risk = f"LLM 反思生成失败：{type(error).__name__}"
        improvement = "在完整上下文已持久化的前提下，可后续补跑更深入的反思生成。"
        return {
            "summary": summary,
            "insights": [insight],
            "lessons": [lesson],
            "risks": [risk],
            "improvements": [improvement],
            "confidence": 0.45,
            "impact_score": 0.4,
            "actionability": 0.75,
        }


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
