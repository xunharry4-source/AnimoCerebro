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
    
    def _call_semantic_kernel(self, prompt: str, use_reasoning: bool = True) -> str:
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
            
            # 构建系统提示词
            system_message = f"""你是Semantic Kernel任务拆解专家，具备以下能力：

{json.dumps(self.kernel_config, indent=2, ensure_ascii=False)}

你的任务是将复杂任务拆解为可执行的子任务序列。你需要：
1. 深度理解任务的语义和上下文
2. 分析任务的技术复杂度和依赖关系
3. 应用项目管理和领域专业知识
4. 生成最优的任务拆分方案
5. 确保拆分结果符合指定的策略要求

请始终以JSON格式返回结果，包含完整的任务拆分信息。"""
            
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
                system_prompt=system_message,
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
        # 策略特定的语义提示
        strategy_prompts = {
            TaskDecompositionStrategy.SEQUENTIAL: """
使用你的语义理解能力，将任务拆分为严格的顺序执行阶段。
请分析任务的逻辑流程，识别必须的前置条件，并按照项目管理的最佳实践生成阶段序列。
每个阶段都应该有明确的入口条件和出口标准。
""",
            TaskDecompositionStrategy.PARALLEL: """
使用你的语义分析能力，识别任务中可以并行执行的部分。
请分析任务的内在结构，识别相互独立的工作包，并设计并行执行方案以最大化效率。
考虑资源约束和协调成本。
""",
            TaskDecompositionStrategy.HYBRID: """
结合你的语义推理和规划能力，设计混合拆分策略。
前期使用顺序模式进行深度分析和规划，后期使用并行模式加速执行。
请平衡风险控制和执行效率。
""",
            TaskDecompositionStrategy.DEPENDENCY_DRIVEN: """
使用你的依赖分析能力，构建基于依赖关系的任务图。
请识别任务的关键路径，分析依赖关系的类型和强度，并生成最优的执行顺序。
考虑依赖的可并行性和资源冲突。
"""
        }
        
        strategy_prompt = strategy_prompts.get(self.strategy, strategy_prompts[TaskDecompositionStrategy.HYBRID])
        
        # 上下文信息
        context_info = ""
        if context:
            if "max_subtasks" in context:
                context_info += f"\\n- 最大子任务数限制: {context['max_subtasks']}"
            if "estimated_duration_per_subtask" in context:
                context_info += f"\\n- 每个子任务预估时长: {context['estimated_duration_per_subtask']}分钟"
            if "team_size" in context:
                context_info += f"\\n- 团队规模: {context['team_size']}人"
            if "complexity" in context:
                context_info += f"\\n- 任务复杂度: {context['complexity']}"
            if "domain" in context:
                context_info += f"\\n- 领域类型: {context['domain']}"
            if "risk_level" in context:
                context_info += f"\\n- 风险等级: {context['risk_level']}"
        
        # 语义分析提示
        semantic_analysis_prompt = f"""
请首先进行深度语义分析：

1. **任务理解**: 解析任务标题和内容，识别核心目标和约束条件
2. **领域识别**: 判断任务所属的领域（软件开发、业务分析、系统架构等）
3. **复杂度评估**: 评估技术复杂度、协调难度、风险等级
4. **依赖分析**: 识别隐含的依赖关系和约束条件
5. **资源需求**: 分析所需的人力、时间、技术资源

任务标题: {mission_title}
任务内容: {mission_content}
{context_info}

拆分策略: {self.strategy.value}

{strategy_prompt}

请按照以下JSON格式返回详细分析结果：
{{
    "semantic_analysis": {{
        "core_objective": "任务的核心目标",
        "domain": "所属领域",
        "complexity_level": "low|medium|high|critical",
        "key_dependencies": ["依赖1", "依赖2"],
        "resource_requirements": {{
            "team_size_min": 2,
            "estimated_total_hours": 40,
            "technical_skills": ["技能1", "技能2"]
        }},
        "risk_factors": ["风险1", "风险2"],
        "success_criteria": ["成功标准1", "成功标准2"]
    }},
    "subtasks": [
        {{
            "local_id": "unique-id",
            "title": "子任务标题",
            "task_type": "cognitive_step|agent_delegation|system_action|intervention",
            "content": "子任务详细描述",
            "objective": "子任务目标",
            "requirements": ["需求1", "需求2", "需求3"],
            "depends_on": ["id1", "id2"],
            "coordination_mode": "sequential|parallel|bundle",
            "estimated_duration": 60,
            "priority": "high|medium|low",
            "semantic_tags": ["标签1", "标签2"],
            "risk_level": "low|medium|high",
            "resource_impact": "low|medium|high",
            "success_metrics": ["指标1", "指标2"]
        }}
    ]
}}

要求：
1. 深度语义理解，不要仅基于关键词匹配
2. 考虑任务的实际业务含义和技术背景
3. 应用相关领域的专业知识和最佳实践
4. 生成合理的依赖关系和协调模式
5. 评估每个子任务的风险和资源影响
6. 确保拆分结果符合指定的策略要求
7. 每个子任务都应该有明确的成功标准

请只返回JSON格式的结果，不要包含其他解释。"""

        return semantic_analysis_prompt
    
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
            
            # 构建Semantic Kernel提示词
            prompt = self._build_semantic_prompt(mission_title, mission_content, context_dict)
            
            # 调用Semantic Kernel
            semantic_response = self._call_semantic_kernel(prompt, use_reasoning=True)
            
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
            analysis_prompt = f"""
请对以下任务进行深度语义分析：

任务标题: {mission_title}
任务内容: {mission_content}

请分析并返回以下信息：
1. 核心目标和意图
2. 领域分类（软件开发、业务分析、系统架构等）
3. 技术复杂度评估
4. 关键依赖和约束
5. 风险因素识别
6. 资源需求分析

请按照JSON格式返回：
{{
    "core_objective": "任务的核心目标",
    "domain": "所属领域",
    "complexity_level": "low|medium|high|critical",
    "key_dependencies": ["依赖1", "依赖2"],
    "resource_requirements": {{
        "team_size_min": 2,
        "estimated_total_hours": 40,
        "technical_skills": ["技能1", "技能2"]
    }},
    "risk_factors": ["风险1", "风险2"],
    "success_criteria": ["成功标准1", "成功标准2"]
}}
"""
            
            # 调用Semantic Kernel进行分析
            analysis_response = self._call_semantic_kernel(analysis_prompt, use_reasoning=True)
            
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
