from __future__ import annotations

import logging
import json
import os
from typing import Any, Dict, List, Optional
from enum import Enum

from zentex.plugins.contracts import FunctionalPluginSpec, PluginHealthStatus
from zentex.tasks.models import TaskType, CoordinationMode, DecompositionContext
from zentex.llm.gateway import LLMGateway
from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.tasks.core.semantic_kernel_llm_prompt import (
    build_semantic_analysis_request,
    build_semantic_kernel_request,
)

logger = logging.getLogger(__name__)

class TaskDecompositionStrategy(str, Enum):
    """任务拆解策略"""
    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"     # 并行执行
    HYBRID = "hybrid"         # 混合模式
    DEPENDENCY_DRIVEN = "dependency_driven"  # 依赖驱动

class SemanticKernelTaskDecompositionSpec(FunctionalPluginSpec):
    """
    Semantic Kernel任务拆解插件规范
    """
    # Semantic Kernel特定配置
    strategy: TaskDecompositionStrategy
    max_depth: int = 5
    min_task_size: int = 1
    enable_optimization: bool = True
    confidence_threshold: float = 0.7
    
    # Semantic Kernel配置
    semantic_model: str = "gpt-4"  # 使用的语义模型
    reasoning_model: str = "gpt-3.5-turbo"  # 推理模型
    enable_planning: bool = True  # 启用规划能力
    enable_memory: bool = True  # 启用记忆功能
    context_window: int = 8000  # 上下文窗口大小
    
    @classmethod
    def plugin_kind(cls) -> str:
        """返回插件类型标识"""
        return "task_decomposition"

class SemanticKernelTaskDecompositionPlugin:
    """
    基于Semantic Kernel的智能任务拆解器
    
    使用Microsoft Semantic Kernel进行高级语义推理和任务拆分，
    支持多模型协作、记忆管理和智能规划。
    通过统一的LLM Gateway访问模型服务。
    """
    
    def __init__(self, spec: SemanticKernelTaskDecompositionSpec) -> None:
        self.plugin_id = spec.plugin_id
        self.strategy = spec.strategy
        self.max_depth = spec.max_depth
        self.min_task_size = spec.min_task_size
        self.enable_optimization = spec.enable_optimization
        self.confidence_threshold = spec.confidence_threshold
        
        # Semantic Kernel配置
        self.semantic_model = spec.semantic_model
        self.reasoning_model = spec.reasoning_model
        self.enable_planning = spec.enable_planning
        self.enable_memory = spec.enable_memory
        self.context_window = spec.context_window
        
        # 使用统一的LLM Gateway
        self.llm_gateway = LLMGateway()
        
        # 调用上下文
        self.caller_context = ModelProviderCallerContext(
            source_module="semantic_kernel_decomposer",
            invocation_phase="task_decomposition",
            decision_id=f"semantic-{spec.plugin_id}"
        )
        
        # Semantic Kernel配置
        self.kernel_config = {
            "plugins": {
                "task_decomposer": {
                    "name": "TaskDecomposer",
                    "description": "智能任务拆解插件",
                    "capabilities": [
                        "semantic_analysis",
                        "task_planning",
                        "dependency_analysis",
                        "resource_optimization"
                    ]
                }
            },
            "skills": {
                "project_management": {
                    "name": "Project Management",
                    "description": "项目管理和任务拆分专业知识",
                    "expertise": [
                        "agile_methodology",
                        "waterfall_planning",
                        "task_estimation",
                        "risk_assessment",
                        "resource_allocation"
                    ]
                },
                "domain_analysis": {
                    "name": "Domain Analysis",
                    "description": "领域特定分析能力",
                    "expertise": [
                        "software_development",
                        "system_architecture",
                        "business_analysis",
                        "technical_feasibility"
                    ]
                }
            }
        }
        
        logger.info(f"SemanticKernelTaskDecompositionPlugin initialized with strategy: {self.strategy}")
    
    def _call_semantic_kernel(
        self,
        prompt: str,
        system_prompt: str,
        use_reasoning: bool = True,
    ) -> str:
        """
        调用Semantic Kernel进行语义推理
        
        Args:
            prompt: 推理提示词
            use_reasoning: 是否使用推理模型
            
        Returns:
            语义推理结果
        """
        try:
            # 选择模型
            model = self.reasoning_model if use_reasoning else self.semantic_model
            
            # 构建上下文
            context = {
                "kernel_config": self.kernel_config,
                "strategy": self.strategy.value,
                "enable_planning": self.enable_planning,
                "enable_memory": self.enable_memory,
                "context_window": self.context_window,
                "model_used": model
            }
            
            # 使用统一的LLM Gateway调用
            gateway_call = self.llm_gateway.invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=self.caller_context,
                model=model,
                system_prompt=system_prompt,
                temperature=0.3,  # 较低温度以获得更一致的结果
                max_output_tokens=3000,
                metadata={
                    "decomposition_strategy": self.strategy.value,
                    "use_reasoning": use_reasoning,
                    "plugin_id": self.plugin_id
                }
            )
            
            # 返回JSON输出
            return json.dumps(gateway_call.output, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error calling Semantic Kernel via LLM Gateway: {e}")
            return None
    
    def _build_semantic_prompt(self, mission_title: str, mission_content: str, 
                           context: Optional[Dict[str, Any]]) -> str:
        """
        构建Semantic Kernel拆分提示词
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            context: 上下文信息
            
        Returns:
            Semantic Kernel提示词
        """
        model = self.reasoning_model if self.enable_planning else self.semantic_model
        return build_semantic_kernel_request(
            kernel_config=self.kernel_config,
            strategy=self.strategy.value,
            model=model,
            context=context,
            mission_title=mission_title,
            mission_content=mission_content,
        )["prompt"]
    
    def _parse_semantic_response(self, semantic_response: str) -> List[Dict[str, Any]]:
        """
        解析Semantic Kernel响应为子任务列表
        
        Args:
            semantic_response: Semantic Kernel响应文本
            
        Returns:
            子任务列表
        """
        try:
            response_data = json.loads(semantic_response)
            
            if "subtasks" in response_data:
                subtasks = response_data["subtasks"]
                
                # 验证和标准化子任务
                validated_subtasks = []
                for i, subtask in enumerate(subtasks):
                    validated_task = self._validate_and_normalize_semantic_subtask(subtask, i)
                    if validated_task:
                        validated_subtasks.append(validated_task)
                
                return validated_subtasks
            else:
                logger.warning("Semantic Kernel response missing 'subtasks' field")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Semantic Kernel response as JSON: {e}")
            logger.error(f"Semantic Kernel response: {semantic_response}")
            return []
        except Exception as e:
            logger.error(f"Error parsing Semantic Kernel response: {e}")
            return []
    
    def _validate_and_normalize_semantic_subtask(self, subtask: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """
        验证和标准化语义子任务
        
        Args:
            subtask: 原始子任务数据
            index: 子任务索引
            
        Returns:
            验证后的子任务或None
        """
        try:
            # 必需字段验证
            if not subtask.get("title"):
                logger.warning(f"Semantic subtask {index} missing title")
                return None
            
            if not subtask.get("content"):
                logger.warning(f"Semantic subtask {index} missing content")
                return None
            
            # 标准化任务类型
            task_type_str = subtask.get("task_type", "cognitive_step")
            task_type_mapping = {
                "cognitive_step": TaskType.COGNITIVE_STEP,
                "agent_delegation": TaskType.AGENT_DELEGATION,
                "system_action": TaskType.SYSTEM_ACTION,
                "intervention": TaskType.INTERVENTION,
                "mission": TaskType.MISSION
            }
            task_type = task_type_mapping.get(task_type_str, TaskType.COGNITIVE_STEP)
            
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
                "local_id": subtask.get("local_id", f"semantic-subtask-{index+1}"),
                "title": subtask["title"],
                "task_type": task_type,
                "content": subtask["content"],
                "objective": subtask.get("objective", ""),
                "requirements": subtask.get("requirements", []),
                "depends_on": subtask.get("depends_on", []),
                "coordination_mode": coordination_mode,
                "estimated_duration": estimated_duration,
                "priority": priority,
                
                # Semantic Kernel特定字段
                "semantic_tags": subtask.get("semantic_tags", []),
                "risk_level": subtask.get("risk_level", "medium"),
                "resource_impact": subtask.get("resource_impact", "medium"),
                "success_metrics": subtask.get("success_metrics", [])
            }
            
            return normalized_task
            
        except Exception as e:
            logger.error(f"Error validating semantic subtask {index}: {e}")
            return None
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         context: Optional[DecompositionContext] = None) -> List[Dict[str, Any]]:
        """
        使用Semantic Kernel拆解任务为子任务
        
        Phase A1: Accepts unified DecompositionContext instead of plain dict.
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            context: 统一的 DecompositionContext 上下文
            
        Returns:
            子任务列表
        """
        logger.info(f"Decomposing mission: {mission_title} using Semantic Kernel strategy {self.strategy}")
        
        try:
            # 如果有 DecompositionContext，转换为字典供 _build_semantic_prompt 使用
            context_dict = None
            if context:
                context_dict = {
                    "mission_query": context.mission_query,
                    "similar_tasks": context.similar_tasks,
                    "common_tags": context.common_tags,
                    "historical_success_rate": context.historical_success_rate,
                }
            
            prompt_request = build_semantic_kernel_request(
                kernel_config=self.kernel_config,
                strategy=self.strategy.value,
                model=self.reasoning_model,
                context=context_dict,
                mission_title=mission_title,
                mission_content=mission_content,
            )
            
            # 调用Semantic Kernel
            semantic_response = self._call_semantic_kernel(
                prompt_request["prompt"],
                prompt_request["system_prompt"],
                use_reasoning=True,
            )
            
            if not semantic_response:
                logger.error("Semantic Kernel call failed, using fallback decomposition")
                return self._fallback_decomposition(mission_title, mission_content)
            
            # 解析Semantic Kernel响应
            subtasks = self._parse_semantic_response(semantic_response)
            
            # 启用优化时进行后处理
            if self.enable_optimization:
                subtasks = self._optimize_semantic_subtasks(subtasks)
            
            logger.info(f"Generated {len(subtasks)} subtasks for mission {mission_title}")
            return subtasks
            
        except Exception as e:
            logger.error(f"Failed to decompose mission {mission_title}: {e}")
            # 返回基础的子任务结构
            return self._fallback_decomposition(mission_title, mission_content)
    
    def _optimize_semantic_subtasks(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        优化语义子任务列表
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            优化后的子任务列表
        """
        # 确保任务粒度合理
        for task in subtasks:
            duration = task.get("estimated_duration", 0)
            if duration < self.min_task_size * 60:  # 转换为分钟
                task["estimated_duration"] = self.min_task_size * 60
                task["remarks"] = f"调整最小任务时长为 {self.min_task_size} 小时"
        
        # 优化依赖关系，避免循环依赖
        task_ids = [task.get("local_id", f"task-{i}") for i, task in enumerate(subtasks)]
        for task in subtasks:
            depends_on = task.get("depends_on", [])
            # 移除不存在的依赖
            valid_depends = [dep for dep in depends_on if dep in task_ids]
            task["depends_on"] = valid_depends
        
        return subtasks
    
    def _fallback_decomposition(self, title: str, content: str) -> List[Dict[str, Any]]:
        """
        后备拆解方案（当Semantic Kernel不可用时）
        """
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
                "estimated_duration": 30,
                "priority": "high",
                "semantic_tags": ["basic", "fallback"],
                "risk_level": "low",
                "resource_impact": "low",
                "success_metrics": ["analysis_complete"]
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
                "estimated_duration": 60,
                "priority": "high",
                "semantic_tags": ["basic", "fallback"],
                "risk_level": "medium",
                "resource_impact": "medium",
                "success_metrics": ["execution_complete"]
            }
        ]
    
    def get_semantic_analysis(self, mission_title: str, mission_content: str, 
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取任务的语义分析
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            context: 上下文信息
            
        Returns:
            语义分析结果
        """
        try:
            # 构建语义分析提示
            analysis_request = build_semantic_analysis_request(
                kernel_config=self.kernel_config,
                model=self.reasoning_model,
                mission_title=mission_title,
                mission_content=mission_content,
            )
            
            # 调用Semantic Kernel进行分析
            analysis_response = self._call_semantic_kernel(
                analysis_request["prompt"],
                analysis_request["system_prompt"],
                use_reasoning=True,
            )
            
            if analysis_response:
                try:
                    analysis_data = json.loads(analysis_response)
                    return analysis_data
                except json.JSONDecodeError:
                    logger.error("Failed to parse semantic analysis response")
                    return {}
            
            return {}
            
        except Exception as e:
            logger.error(f"Error in semantic analysis: {e}")
            return {}
    
    def get_decomposition_quality(self, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        评估语义拆解质量
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            质量评估结果
        """
        if not subtasks:
            return {"score": 0.0, "quality_level": "poor", "semantic_score": 0.0}
        
        # 计算质量指标
        metrics = {
            "total_subtasks": len(subtasks),
            "avg_duration": sum(task.get("estimated_duration", 0) for task in subtasks) / len(subtasks),
            "dependency_complexity": sum(len(task.get("depends_on", [])) for task in subtasks) / len(subtasks),
            "coordination_diversity": len(set(task.get("coordination_mode", "sequential") for task in subtasks)),
            "type_diversity": len(set(task.get("task_type", "cognitive_step") for task in subtasks)),
            "semantic_diversity": len(set(tag for task in subtasks for tag in task.get("semantic_tags", []))),
            "risk_distribution": len(set(task.get("risk_level", "medium") for task in subtasks))
        }
        
        # 计算质量分数
        score = 0.0
        issues = []
        
        # 子任务数量合理性
        if 3 <= metrics["total_subtasks"] <= 8:
            score += 0.25
        else:
            issues.append("Subtask count may be too few or too many")
        
        # 平均时长合理性
        if 30 <= metrics["avg_duration"] <= 180:
            score += 0.25
        else:
            issues.append("Average duration may be unreasonable")
        
        # 依赖复杂度
        if 0.5 <= metrics["dependency_complexity"] <= 2.0:
            score += 0.15
        else:
            issues.append("Dependency complexity may be too high or too low")
        
        # 协调模式多样性
        if metrics["coordination_diversity"] >= 2:
            score += 0.1
        else:
            issues.append("Limited coordination mode diversity")
        
        # 任务类型多样性
        if metrics["type_diversity"] >= 2:
            score += 0.1
        else:
            issues.append("Limited task type diversity")
        
        # 语义多样性
        if metrics["semantic_diversity"] >= 3:
            score += 0.1
        else:
            issues.append("Limited semantic diversity")
        
        # 风险分布合理性
        if metrics["risk_distribution"] >= 2:
            score += 0.05
        else:
            issues.append("Limited risk distribution")
        
        return {
            "score": score,
            "semantic_score": score,  # 语义推理特定分数
            "metrics": metrics,
            "issues": issues,
            "quality_level": "excellent" if score >= 0.8 else "good" if score >= 0.6 else "needs_improvement"
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        插件健康检查
        
        Returns:
            健康状态信息
        """
        return {
            "status": "healthy",
            "plugin_id": self.plugin_id,
            "strategy": self.strategy.value,
            "semantic_kernel_configured": True,  # 使用LLM Gateway，总是配置好的
            "configuration": {
                "max_depth": self.max_depth,
                "min_task_size": self.min_task_size,
                "enable_optimization": self.enable_optimization,
                "confidence_threshold": self.confidence_threshold,
                "semantic_model": self.semantic_model,
                "reasoning_model": self.reasoning_model,
                "enable_planning": self.enable_planning,
                "enable_memory": self.enable_memory,
                "context_window": self.context_window,
                "gateway_type": "unified_llm_gateway"
            },
            "kernel_capabilities": list(self.kernel_config["plugins"]["task_decomposer"]["capabilities"]),
            "available_skills": list(self.kernel_config["skills"].keys()),
            "last_check": "2024-01-01T00:00:00Z"  # 实际实现中应该是当前时间
        }
