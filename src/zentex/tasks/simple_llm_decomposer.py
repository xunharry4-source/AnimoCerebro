from __future__ import annotations

import logging
import json
import os
from typing import Any, Dict, List, Optional
from enum import Enum

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus
from zentex.tasks.models import TaskType, CoordinationMode
from zentex.llm.gateway import LLMGateway
from zentex.core.model_provider_spec import ModelProviderCallerContext

logger = logging.getLogger(__name__)

class TaskDecompositionStrategy(str, Enum):
    """任务拆解策略"""
    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"     # 并行执行
    HYBRID = "hybrid"         # 混合模式
    DEPENDENCY_DRIVEN = "dependency_driven"  # 依赖驱动

class LLMTaskDecompositionSpec(FunctionalPluginSpec):
    """
    LLM任务拆解插件规范
    """
    # LLM特定配置
    strategy: TaskDecompositionStrategy
    max_depth: int = 5
    min_task_size: int = 1
    enable_optimization: bool = True
    confidence_threshold: float = 0.7
    
    @classmethod
    def plugin_kind(cls) -> str:
        """返回插件类型标识"""
        return "task_decomposition"

class LLMTaskDecompositionPlugin:
    """
    基于LLM的智能任务拆解器
    通过统一的LLM Gateway访问模型服务
    """
    
    def __init__(self, spec: LLMTaskDecompositionSpec) -> None:
        self.plugin_id = spec.plugin_id
        self.strategy = spec.strategy
        self.max_depth = spec.max_depth
        self.min_task_size = spec.min_task_size
        self.enable_optimization = spec.enable_optimization
        self.confidence_threshold = spec.confidence_threshold
        
        # 使用统一的LLM Gateway
        self.llm_gateway = LLMGateway()
        
        # 调用上下文
        self.caller_context = ModelProviderCallerContext(
            source_module="llm_decomposer",
            invocation_phase="task_decomposition",
            decision_id=f"llm-{spec.plugin_id}"
        )
        
        logger.info(f"LLMTaskDecompositionPlugin initialized with strategy: {self.strategy}")
    
    def _call_llm(self, prompt: str, max_tokens: int = 2000) -> str:
        """调用LLM API进行任务拆分"""
        try:
            # 构建系统提示词
            system_message = "你是一个专业的任务管理专家，擅长将复杂任务拆解为可执行的子任务。"
            
            # 构建上下文
            context = {
                "strategy": self.strategy.value,
                "max_depth": self.max_depth,
                "min_task_size": self.min_task_size,
                "enable_optimization": self.enable_optimization,
                "confidence_threshold": self.confidence_threshold,
                "plugin_id": self.plugin_id
            }
            
            # 使用统一的LLM Gateway调用
            gateway_call = self.llm_gateway.invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=self.caller_context,
                system_prompt=system_message,
                temperature=0.7,
                max_output_tokens=max_tokens,
                metadata={
                    "decomposition_strategy": self.strategy.value,
                    "plugin_id": self.plugin_id
                }
            )
            
            # 返回JSON输出
            return json.dumps(gateway_call.output, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error calling LLM via LLM Gateway: {e}")
            return None
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """使用LLM拆解任务为子任务"""
        logger.info(f"Decomposing mission: {mission_title} using LLM strategy {self.strategy}")
        
        try:
            # 构建LLM提示词
            prompt = self._build_decomposition_prompt(mission_title, mission_content, context)
            
            # 调用LLM
            llm_response = self._call_llm(prompt)
            
            if not llm_response:
                logger.error("LLM call failed, using fallback decomposition")
                return self._fallback_decomposition(mission_title, mission_content)
            
            # 解析LLM响应
            subtasks = self._parse_llm_response(llm_response)
            
            # 启用优化时进行后处理
            if self.enable_optimization:
                subtasks = self._optimize_subtasks(subtasks)
            
            logger.info(f"Generated {len(subtasks)} subtasks for mission {mission_title}")
            return subtasks
            
        except Exception as e:
            logger.error(f"Failed to decompose mission {mission_title}: {e}")
            return self._fallback_decomposition(mission_title, mission_content)
    
    def _build_decomposition_prompt(self, mission_title: str, mission_content: str, 
                                 context: Optional[Dict[str, Any]]) -> str:
        """构建LLM拆分提示词"""
        strategy_prompts = {
            TaskDecompositionStrategy.SEQUENTIAL: """
请将任务拆分为严格的顺序执行阶段，每个阶段必须依赖前一个阶段。
按照项目管理的标准流程：分析→规划→准备→执行→验证→收尾。
""",
            TaskDecompositionStrategy.PARALLEL: """
请将任务拆分为可以并行执行的子任务。
识别可以同时进行的工作，减少总体执行时间。
""",
            TaskDecompositionStrategy.HYBRID: """
请将任务拆分为混合模式：前期顺序（分析、规划），后期并行执行。
结合顺序和并行策略的优点。
""",
            TaskDecompositionStrategy.DEPENDENCY_DRIVEN: """
请基于任务依赖关系进行拆分。
识别关键依赖路径，确保依赖关系清晰合理。
"""
        }
        
        strategy_prompt = strategy_prompts.get(self.strategy, strategy_prompts[TaskDecompositionStrategy.HYBRID])
        
        context_info = ""
        if context:
            if "max_subtasks" in context:
                context_info += f"\\n- 最大子任务数: {context['max_subtasks']}"
            if "estimated_duration_per_subtask" in context:
                context_info += f"\\n- 每个子任务预估时长: {context['estimated_duration_per_subtask']}分钟"
        
        prompt = f"""你是一个专业的任务管理专家，请将以下任务拆解为可执行的子任务。

任务标题: {mission_title}
任务内容: {mission_content}
拆分策略: {self.strategy.value}
{context_info}

{strategy_prompt}

请按照以下JSON格式返回子任务列表：
{{
    "subtasks": [
        {{
            "local_id": "unique-id",
            "title": "子任务标题",
            "task_type": "cognitive_step",
            "content": "子任务详细描述",
            "objective": "子任务目标",
            "requirements": ["需求1", "需求2"],
            "depends_on": ["id1"],
            "coordination_mode": "sequential",
            "estimated_duration": 60,
            "priority": "high"
        }}
    ]
}}

要求：
1. 每个子任务都有明确的目标和可执行的需求
2. 任务类型为cognitive_step
3. 依赖关系要合理，避免循环依赖
4. 预估时长要合理（30-240分钟之间）
5. 优先级要根据重要性和紧急性设置
6. 协调模式要符合执行方式

请只返回JSON格式的结果，不要包含其他解释。"""

        return prompt
    
    def _parse_llm_response(self, llm_response: str) -> List[Dict[str, Any]]:
        """解析LLM响应为子任务列表"""
        try:
            response_data = json.loads(llm_response)
            
            if "subtasks" in response_data:
                subtasks = response_data["subtasks"]
                
                # 验证和标准化子任务
                validated_subtasks = []
                for i, subtask in enumerate(subtasks):
                    validated_task = self._validate_and_normalize_subtask(subtask, i)
                    if validated_task:
                        validated_subtasks.append(validated_task)
                
                return validated_subtasks
            else:
                logger.warning("LLM response missing 'subtasks' field")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _validate_and_normalize_subtask(self, subtask: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """验证和标准化子任务"""
        try:
            if not subtask.get("title") or not subtask.get("content"):
                return None
            
            # 标准化任务类型
            task_type = TaskType.COGNITIVE_STEP
            
            # 标准化协调模式
            coord_mode_str = subtask.get("coordination_mode", "sequential")
            coord_mode_mapping = {
                "sequential": CoordinationMode.SEQUENTIAL,
                "parallel": CoordinationMode.PARALLEL,
                "bundle": CoordinationMode.BUNDLE
            }
            coordination_mode = coord_mode_mapping.get(coord_mode_str, CoordinationMode.SEQUENTIAL)
            
            # 标准化优先级
            priority = subtask.get("priority", "medium")
            if priority not in ["high", "medium", "low"]:
                priority = "medium"
            
            # 标准化时长
            estimated_duration = subtask.get("estimated_duration", 60)
            if not isinstance(estimated_duration, int) or estimated_duration < 30:
                estimated_duration = 60
            elif estimated_duration > 240:
                estimated_duration = 240
            
            # 构建标准化子任务
            normalized_task = {
                "local_id": subtask.get("local_id", f"subtask-{index+1}"),
                "title": subtask["title"],
                "task_type": task_type,
                "content": subtask["content"],
                "objective": subtask.get("objective", ""),
                "requirements": subtask.get("requirements", []),
                "depends_on": subtask.get("depends_on", []),
                "coordination_mode": coordination_mode,
                "estimated_duration": estimated_duration,
                "priority": priority
            }
            
            return normalized_task
            
        except Exception as e:
            logger.error(f"Error validating subtask {index}: {e}")
            return None
    
    def _optimize_subtasks(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化子任务列表"""
        for task in subtasks:
            duration = task.get("estimated_duration", 0)
            if duration < self.min_task_size * 60:
                task["estimated_duration"] = self.min_task_size * 60
        
        return subtasks
    
    def _fallback_decomposition(self, title: str, content: str) -> List[Dict[str, Any]]:
        """后备拆解方案"""
        return [
            {
                "local_id": "fallback-analysis",
                "title": f"基础分析: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"分析 {content} 的基本需求",
                "objective": "明确任务目标和范围",
                "requirements": ["需求分析", "目标确认"],
                "depends_on": [],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 30
            },
            {
                "local_id": "fallback-execution",
                "title": f"基础执行: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"执行 {content} 的主要工作",
                "objective": "完成任务的核心目标",
                "requirements": ["执行主要工作", "验证结果"],
                "depends_on": ["fallback-analysis"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 60
            }
        ]
    
    def health_check(self) -> Dict[str, Any]:
        """插件健康检查"""
        return {
            "status": "healthy",
            "plugin_id": self.plugin_id,
            "strategy": self.strategy.value,
            "llm_gateway_configured": True,  # 使用LLM Gateway，总是配置好的
            "configuration": {
                "max_depth": self.max_depth,
                "min_task_size": self.min_task_size,
                "enable_optimization": self.enable_optimization,
                "confidence_threshold": self.confidence_threshold,
                "gateway_type": "unified_llm_gateway"
            }
        }
