"""
LLM驱动的反思内容生成器

提供基于大语言模型的深度反思生成能力，支持多种反思类型的专业化提示词。
"""

from __future__ import annotations

import logging
import json
from typing import Any, Dict, Optional

from zentex.reflection.models import ReflectionType

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
            context: 反思上下文数据
            
        Returns:
            包含summary, insights, lessons, risks, improvements等的字典
        """
        # 构建专业化的提示词
        prompt = self._build_prompt(subject, reflection_type, context)
        
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
    
    def _build_prompt(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any]
    ) -> str:
        """
        根据反思类型构建专业化的提示词
        
        Args:
            subject: 反思主题
            reflection_type: 反思类型
            context: 上下文数据
            
        Returns:
            格式化的提示词字符串
        """
        # 基础提示词框架
        base_prompt = f"""
你是一个专业的反思分析师，擅长深度思考和系统性分析。

请对以下{self._get_reflection_type_name(reflection_type)}进行深度反思分析。

## 反思主题
{subject}

## 上下文信息
{json.dumps(context, ensure_ascii=False, indent=2, default=str)}

## 任务要求
请从以下几个维度进行深入分析：

1. **核心洞察 (insights)**: 发现的关键洞见和深层理解（至少2-3条）
2. **经验教训 (lessons)**: 可以复用的经验和教训（至少1-2条）
3. **潜在风险 (risks)**: 可能存在的风险和隐患（如有）
4. **改进建议 (improvements)**: 具体可行的改进方案（至少1-2条）
5. **置信度评估 (confidence)**: 你对这次分析的信心程度（0-1之间）
6. **影响力评分 (impact_score)**: 这次反思的重要性（0-1之间）
7. **可操作性 (actionability)**: 建议的可执行程度（0-1之间）

## 输出要求
- 洞察要深刻，不要表面化
- 结合具体数据和事实
- 提供可操作的建议
- 保持客观和专业
- 用中文回答

请以JSON格式返回，包含以下字段：
- summary: 反思摘要（一句话总结）
- insights: 洞察列表（字符串数组）
- lessons: 经验教训列表（字符串数组）
- risks: 风险列表（字符串数组）
- improvements: 改进建议列表（字符串数组）
- confidence: 置信度（0-1的浮点数）
- impact_score: 影响力评分（0-1的浮点数）
- actionability: 可操作性（0-1的浮点数）
"""
        
        # 根据反思类型添加专业化指导
        type_specific_guidance = self._get_type_specific_guidance(reflection_type, context)
        if type_specific_guidance:
            base_prompt += f"\n\n## 专业指导\n{type_specific_guidance}"
        
        return base_prompt
    
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
    
    def _get_type_specific_guidance(
        self,
        reflection_type: ReflectionType,
        context: Dict[str, Any]
    ) -> str:
        """
        根据反思类型获取专业化的分析指导
        
        Args:
            reflection_type: 反思类型
            context: 上下文数据
            
        Returns:
            专业化指导文本
        """
        if reflection_type == ReflectionType.DECISION_REFLECTION:
            decision = context.get("decision", {})
            alternatives = context.get("alternatives", [])
            
            guidance = """
### 决策反思的专业分析要点

1. **决策质量评估**:
   - 决策依据是否充分？
   - 是否考虑了足够的备选方案？
   - 风险评估是否全面？

2. **决策过程分析**:
   - 决策流程是否合理？
   - 是否有偏见或盲点？
   - 时间压力是否影响了决策质量？

3. **结果对比**:
   - 实际结果与预期是否一致？
   - 如果有偏差，原因是什么？
   - 其他备选方案可能的结果如何？

4. **长期影响**:
   - 这个决策的长期后果是什么？
   - 是否会影响未来的决策空间？
   - 是否有不可逆的影响？
"""
            
            # 如果有具体数据，加入提示
            if alternatives:
                guidance += f"\n注意：本次决策考虑了{len(alternatives)}个备选方案，请分析这个数量是否足够。\n"
            
            if decision.get("risk_level"):
                guidance += f"\n注意：决策的风险等级为{decision['risk_level']}，请重点关注风险控制。\n"
            
            return guidance
        
        elif reflection_type == ReflectionType.ERROR_REFLECTION:
            error_data = context.get("error", {})
            impact = context.get("impact", {})
            
            guidance = """
### 错误反思的专业分析要点

1. **根本原因分析**:
   - 错误的直接原因是什么？
   - 深层次的根本原因是什么？
   - 是否有系统性问题？

2. **影响评估**:
   - 对用户/业务的影响程度？
   - 是否有连锁反应？
   - 恢复成本有多高？

3. **预防措施**:
   - 如何防止类似错误再次发生？
   - 需要什么样的监控和预警？
   - 是否需要流程改进？

4. **学习价值**:
   - 从这个错误中学到了什么？
   - 如何将教训转化为最佳实践？
   - 是否可以分享给团队？
"""
            
            if error_data.get("severity"):
                guidance += f"\n注意：错误严重程度为{error_data['severity']}，请相应调整分析的深度。\n"
            
            return guidance
        
        elif reflection_type == ReflectionType.SUCCESS_REFLECTION:
            success_data = context.get("success", {})
            
            guidance = """
### 成功反思的专业分析要点

1. **成功因素识别**:
   - 哪些因素促成了成功？
   - 哪些是关键成功因素？
   - 有多少是运气成分？

2. **可复制性分析**:
   - 成功经验是否可以复制？
   - 需要什么条件才能重现？
   - 有哪些依赖因素？

3. **优化空间**:
   - 是否可以做得更好？
   - 有没有被忽视的机会？
   - 效率是否可以提升？

4. **知识沉淀**:
   - 如何将成功经验标准化？
   - 是否可以形成最佳实践？
   - 如何推广到其他场景？
"""
            
            return guidance
        
        elif reflection_type == ReflectionType.ACTION_REFLECTION:
            execution = context.get("execution", {})
            
            guidance = """
### 行动反思的专业分析要点

1. **执行质量**:
   - 是否按计划执行？
   - 执行过程中的偏差？
   - 资源利用是否合理？

2. **效率评估**:
   - 时间管理是否有效？
   - 是否有不必要的步骤？
   - 自动化机会在哪里？

3. **协作效果**:
   - 团队协作是否顺畅？
   - 沟通是否存在障碍？
   - 责任分工是否清晰？

4. **改进方向**:
   - 下次如何做得更好？
   - 需要什么样的工具支持？
   - 流程优化的切入点？
"""
            
            if execution.get("duration"):
                guidance += f"\n注意：执行耗时{execution['duration']}分钟，请评估是否合理。\n"
            
            return guidance
        
        # 默认指导
        return """
### 通用分析要点

1. **全面性**: 是否考虑了所有重要方面？
2. **深度**: 分析是否触及本质？
3. **实用性**: 结论是否有实际价值？
4. **前瞻性**: 是否考虑了未来影响？
"""
    
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
