from __future__ import annotations

import logging
import json
import requests
import os
from typing import Any, Dict, List, Optional
from enum import Enum

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus
from zentex.tasks.models import TaskType, CoordinationMode

logger = logging.getLogger(__name__)

class TaskDecompositionStrategy(str, Enum):
    """任务拆解策略"""
    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"     # 并行执行
    HYBRID = "hybrid"         # 混合模式
    DEPENDENCY_DRIVEN = "dependency_driven"  # 依赖驱动

class TaskDecompositionPluginSpec(FunctionalPluginSpec):
    """
    任务拆解插件规范
    
    负责将大型任务拆解为可执行的子任务序列，
    支持多种拆解策略和智能优化。
    """
    
    # 插件特定配置
    strategy: TaskDecompositionStrategy
    max_depth: int = 5  # 最大拆解深度
    min_task_size: int = 1  # 最小任务粒度（小时）
    enable_optimization: bool = True  # 是否启用优化
    confidence_threshold: float = 0.7  # 置信度阈值
    
    @classmethod
    def plugin_kind(cls) -> str:
        """返回插件类型标识"""
        return "task_decomposition"

class TaskDecompositionPlugin:
    """
    任务拆解插件实现
    
    基于LLM的智能任务拆解器，
    支持多种策略和智能优化。
    """
    
    def __init__(self, spec: TaskDecompositionPluginSpec) -> None:
        """
        初始化任务拆解插件
        
        Args:
            spec: 插件规范
        """
        self.plugin_id = spec.plugin_id
        self.strategy = spec.strategy
        self.max_depth = spec.max_depth
        self.min_task_size = spec.min_task_size
        self.enable_optimization = spec.enable_optimization
        self.confidence_threshold = spec.confidence_threshold
        
        # LLM配置
        self.llm_api_key = os.getenv("OPENAI_API_KEY", "your-api-key-here")
        self.llm_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.llm_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        logger.info(f"TaskDecompositionPlugin initialized with strategy: {self.strategy}")
    
    def _call_llm(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        调用LLM API进行任务拆分
        
        Args:
            prompt: 拆分提示词
            max_tokens: 最大token数
            
        Returns:
            LLM响应内容
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.llm_model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的任务管理专家，擅长将复杂任务拆解为可执行的子任务。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.llm_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM API call failed: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        使用LLM拆解任务为子任务
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            context: 上下文信息
            
        Returns:
            子任务列表
        """
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
            # 返回基础的子任务结构
            return self._fallback_decomposition(mission_title, mission_content)
    
    def _build_decomposition_prompt(self, mission_title: str, mission_content: str, 
                                 context: Optional[Dict[str, Any]]) -> str:
        """
        构建LLM拆分提示词
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            context: 上下文信息
            
        Returns:
            LLM提示词
        """
        # 策略特定的提示词
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
        
        # 上下文信息
        context_info = ""
        if context:
            if "max_subtasks" in context:
                context_info += f"\n- 最大子任务数: {context['max_subtasks']}"
            if "estimated_duration_per_subtask" in context:
                context_info += f"\n- 每个子任务预估时长: {context['estimated_duration_per_subtask']}分钟"
            if "team_size" in context:
                context_info += f"\n- 团队规模: {context['team_size']}人"
            if "complexity" in context:
                context_info += f"\n- 复杂度: {context['complexity']}"
        
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
            "task_type": "cognitive_step|agent_delegation|system_action|intervention",
            "content": "子任务详细描述",
            "objective": "子任务目标",
            "requirements": ["需求1", "需求2", "需求3"],
            "depends_on": ["id1", "id2"],
            "coordination_mode": "sequential|parallel|bundle",
            "estimated_duration": 60,
            "priority": "high|medium|low"
        }}
    ]
}}

要求：
1. 每个子任务都有明确的目标和可执行的需求
2. 任务类型要符合实际工作性质
3. 依赖关系要合理，避免循环依赖
4. 预估时长要合理（30-240分钟之间）
5. 优先级要根据重要性和紧急性设置
6. 协调模式要符合执行方式

请只返回JSON格式的结果，不要包含其他解释。"""

        return prompt
    
    def _parse_llm_response(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        解析LLM响应为子任务列表
        
        Args:
            llm_response: LLM响应文本
            
        Returns:
            子任务列表
        """
        try:
            # 尝试解析JSON
            response_data = json.loads(llm_response)
            
            if "subtasks" in response_data:
                subtasks = response_data["subtasks"]
                
                # 验证和标准化子任务
                validated_subtasks = []
                for i, subtask in enumerate(subtasks):
                    validated_task = self._validate_and_normalize_subtask(subtask, i)
                    if validated_task:
                        validated_subtasks.append(validiated_task)
                
                return validated_subtasks
            else:
                logger.warning("LLM response missing 'subtasks' field")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"LLM response: {llm_response}")
            return []
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _validate_and_normalize_subtask(self, subtask: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """
        验证和标准化子任务
        
        Args:
            subtask: 原始子任务数据
            index: 子任务索引
            
        Returns:
            验证后的子任务或None
        """
        try:
            # 必需字段验证
            if not subtask.get("title"):
                logger.warning(f"Subtask {index} missing title")
                return None
            
            if not subtask.get("content"):
                logger.warning(f"Subtask {index} missing content")
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
    
    def _decompose_sequential(self, title: str, content: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """顺序拆解策略"""
        subtasks = [
            {
                "local_id": "phase-1-analysis",
                "title": f"分析阶段: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"深入分析 {content} 的需求、约束和可行性",
                "objective": "明确任务范围、识别关键依赖、评估风险",
                "requirements": [
                    "收集和分析需求文档",
                    "识别技术约束和限制",
                    "评估资源和时间需求",
                    "制定初步计划"
                ],
                "depends_on": [],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 60,  # 1小时
                "priority": "high"
            },
            {
                "local_id": "phase-2-planning",
                "title": f"规划阶段: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"制定 {content} 的详细执行计划",
                "objective": "创建可执行的任务分解和时间表",
                "requirements": [
                    "基于分析结果制定详细计划",
                    "分配资源和责任人",
                    "设置里程碑和检查点",
                    "制定风险应对策略"
                ],
                "depends_on": ["phase-1-analysis"],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 45,
                "priority": "high"
            },
            {
                "local_id": "phase-3-preparation",
                "title": f"准备阶段: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"准备 {content} 执行所需的环境和资源",
                "objective": "确保执行环境和资源就绪",
                "requirements": [
                    "准备开发/执行环境",
                    "配置必要的工具和服务",
                    "获取所需权限和访问凭证",
                    "验证环境可用性"
                ],
                "depends_on": ["phase-2-planning"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 30,
                "priority": "medium"
            },
            {
                "local_id": "phase-4-execution",
                "title": f"执行阶段: {title}",
                "task_type": TaskType.AGENT_DELEGATION,
                "content": f"执行 {content} 的核心工作",
                "objective": "完成任务的核心目标和交付物",
                "requirements": [
                    "按照计划执行核心任务",
                    "处理执行中的问题和异常",
                    "确保质量和进度要求",
                    "记录执行过程和结果"
                ],
                "depends_on": ["phase-3-preparation"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 120,
                "priority": "high"
            },
            {
                "local_id": "phase-5-validation",
                "title": f"验证阶段: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"验证 {content} 的执行结果和质量",
                "objective": "确保任务结果符合预期和质量标准",
                "requirements": [
                    "执行质量检查和测试",
                    "验证功能完整性和正确性",
                    "收集用户反馈和评估",
                    "生成验证报告"
                ],
                "depends_on": ["phase-4-execution"],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 60,
                "priority": "medium"
            },
            {
                "local_id": "phase-6-finalization",
                "title": f"收尾阶段: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"完成 {content} 的收尾工作和文档整理",
                "objective": "整理交付物、归档文档、总结经验",
                "requirements": [
                    "整理和交付最终成果",
                    "编写完整文档和说明",
                    "归档相关资料和记录",
                    "总结经验教训"
                ],
                "depends_on": ["phase-5-validation"],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 30,
                "priority": "low"
            }
        ]
        
        return subtasks
    
    def _decompose_parallel(self, title: str, content: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行拆解策略"""
        subtasks = [
            {
                "local_id": "parallel-research",
                "title": f"并行研究: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"并行研究 {content} 的各个方面",
                "objective": "快速收集和分析多维度信息",
                "requirements": [
                    "技术可行性研究",
                    "市场和竞品分析",
                    "资源和成本评估",
                    "风险和合规检查"
                ],
                "depends_on": [],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 90,
                "priority": "high"
            },
            {
                "local_id": "parallel-design",
                "title": f"并行设计: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"并行设计 {content} 的解决方案",
                "objective": "创建多个备选设计方案",
                "requirements": [
                    "架构设计",
                    "界面设计",
                    "流程设计",
                    "安全设计"
                ],
                "depends_on": [],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 120,
                "priority": "high"
            },
            {
                "local_id": "parallel-implementation",
                "title": f"并行实现: {title}",
                "task_type": TaskType.AGENT_DELEGATION,
                "content": f"并行实现 {content} 的各个组件",
                "objective": "高效实现多个功能模块",
                "requirements": [
                    "核心功能开发",
                    "辅助功能开发",
                    "集成接口开发",
                    "测试用例开发"
                ],
                "depends_on": ["parallel-research", "parallel-design"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 180,
                "priority": "high"
            },
            {
                "local_id": "parallel-integration",
                "title": f"并行集成: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"集成 {content} 的所有并行组件",
                "objective": "将并行开发的组件整合为完整系统",
                "requirements": [
                    "组件集成测试",
                    "系统集成验证",
                    "性能优化调整",
                    "部署准备"
                ],
                "depends_on": ["parallel-implementation"],
                "coordination_mode": CoordinationMode.BUNDLE,
                "estimated_duration": 60,
                "priority": "medium"
            }
        ]
        
        return subtasks
    
    def _decompose_hybrid(self, title: str, content: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """混合拆解策略"""
        # 结合顺序和并行策略的优点
        sequential_core = self._decompose_sequential(title, content, context)
        parallel_support = self._decompose_parallel(title, content, context)
        
        # 重新组织为混合模式
        hybrid_tasks = [
            # 串行的核心阶段
            sequential_core[0],  # 分析阶段
            sequential_core[1],  # 规划阶段
            
            # 并行的执行阶段
            {
                "local_id": "hybrid-parallel-execution",
                "title": f"混合并行执行: {title}",
                "task_type": TaskType.AGENT_DELEGATION,
                "content": f"并行执行 {content} 的主要工作流",
                "objective": "通过并行执行提高效率",
                "requirements": [
                    "并行开发核心功能",
                    "并行处理支持任务",
                    "持续集成和验证",
                    "进度同步和协调"
                ],
                "depends_on": ["phase-2-planning"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 150,
                "priority": "high"
            },
            
            # 串行的收尾阶段
            sequential_core[4],  # 验证阶段
            sequential_core[5],  # 收尾阶段
        ]
        
        return hybrid_tasks
    
    def _decompose_dependency_driven(self, title: str, content: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """依赖驱动拆解策略"""
        # 基于任务依赖关系的智能拆解
        subtasks = [
            {
                "local_id": "dependency-discovery",
                "title": f"依赖发现: {title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"识别和分析 {content} 的所有依赖关系",
                "objective": "建立完整的依赖图谱",
                "requirements": [
                    "识别技术依赖",
                    "分析业务依赖",
                    "确定资源依赖",
                    "评估时间依赖"
                ],
                "depends_on": [],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 45,
                "priority": "critical"
            },
            {
                "local_id": "dependency-resolution",
                "title": f"依赖解析: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"解决 {content} 的关键依赖",
                "objective": "确保所有必要依赖可用",
                "requirements": [
                    "解决阻塞依赖",
                    "准备依赖资源",
                    "建立依赖接口",
                    "验证依赖可用性"
                ],
                "depends_on": ["dependency-discovery"],
                "coordination_mode": CoordinationMode.PARALLEL,
                "estimated_duration": 60,
                "priority": "critical"
            },
            {
                "local_id": "core-execution",
                "title": f"核心执行: {title}",
                "task_type": TaskType.AGENT_DELEGATION,
                "content": f"在依赖满足后执行 {content} 的核心任务",
                "objective": "完成主要目标和交付物",
                "requirements": [
                    "执行核心功能",
                    "处理依赖变更",
                    "维护依赖关系",
                    "确保交付质量"
                ],
                "depends_on": ["dependency-resolution"],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 120,
                "priority": "high"
            },
            {
                "local_id": "dependency-validation",
                "title": f"依赖验证: {title}",
                "task_type": TaskType.SYSTEM_ACTION,
                "content": f"验证 {content} 执行后的依赖状态",
                "objective": "确保依赖关系正确维护",
                "requirements": [
                    "验证依赖完整性",
                    "检查依赖一致性",
                    "更新依赖文档",
                    "报告依赖状态"
                ],
                "depends_on": ["core-execution"],
                "coordination_mode": CoordinationMode.SEQUENTIAL,
                "estimated_duration": 30,
                "priority": "medium"
            }
        ]
        
        return subtasks
    
    def _optimize_subtasks(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化子任务序列"""
        # 1. 合并相似任务
        optimized = self._merge_similar_tasks(subtasks)
        
        # 2. 优化依赖关系
        optimized = self._optimize_dependencies(optimized)
        
        # 3. 调整任务粒度
        optimized = self._adjust_task_granularity(optimized)
        
        # 4. 优化资源分配
        optimized = self._optimize_resource_allocation(optimized)
        
        return optimized
    
    def _merge_similar_tasks(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并相似任务"""
        # 简化实现：合并连续的相同类型任务
        merged = []
        i = 0
        while i < len(subtasks):
            current = subtasks[i].copy()
            
            # 检查是否可以与下一个任务合并
            while i + 1 < len(subtasks):
                next_task = subtasks[i + 1]
                if (current["task_type"] == next_task["task_type"] and 
                    current["coordination_mode"] == CoordinationMode.PARALLEL and
                    next_task["coordination_mode"] == CoordinationMode.PARALLEL):
                    
                    # 合并任务
                    current["title"] += f" + {next_task['title']}"
                    current["requirements"].extend(next_task["requirements"])
                    current["estimated_duration"] += next_task.get("estimated_duration", 0)
                    i += 1
                else:
                    break
            
            merged.append(current)
            i += 1
        
        return merged
    
    def _optimize_dependencies(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化依赖关系"""
        # 简化实现：移除不必要的依赖
        for task in subtasks:
            # 如果任务没有真正的依赖，清空依赖列表
            if not task.get("depends_on") or len(task["depends_on"]) == 0:
                task["depends_on"] = []
        
        return subtasks
    
    def _adjust_task_granularity(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """调整任务粒度"""
        # 确保任务粒度合理
        for task in subtasks:
            duration = task.get("estimated_duration", 0)
            if duration < self.min_task_size * 60:  # 转换为分钟
                task["estimated_duration"] = self.min_task_size * 60
                task["remarks"] = f"调整最小任务时长为 {self.min_task_size} 小时"
        
        return subtasks
    
    def _optimize_resource_allocation(self, subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化资源分配"""
        # 简化实现：调整优先级以平衡负载
        high_priority_count = sum(1 for task in subtasks if task.get("priority") == "high")
        
        if high_priority_count > len(subtasks) // 2:
            # 如果高优先级任务过多，降低部分任务优先级
            for task in subtasks:
                if task.get("priority") == "high" and task.get("estimated_duration", 0) < 60:
                    task["priority"] = "medium"
        
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
                "task_type": TaskType.AGENT_DELEGATION,
                "content": f"执行 {content} 的主要工作",
                "objective": "完成任务核心目标",
                "requirements": ["核心执行", "结果验证"],
                "depends_on": ["fallback-analysis"],
                "coordination_mode": CoordinationMode.SEQUNTIAL,
                "estimated_duration": 60
            }
        ]
    
    def get_decomposition_quality(self, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        评估拆解质量
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            质量评估结果
        """
        total_tasks = len(subtasks)
        if total_tasks == 0:
            return {"score": 0.0, "issues": ["No subtasks generated"]}
        
        # 评估指标
        metrics = {
            "task_count": total_tasks,
            "avg_duration": sum(task.get("estimated_duration", 0) for task in subtasks) / total_tasks,
            "dependency_complexity": sum(len(task.get("depends_on", [])) for task in subtasks) / total_tasks,
            "coordination_diversity": len(set(task.get("coordination_mode") for task in subtasks)),
            "type_diversity": len(set(task.get("task_type") for task in subtasks))
        }
        
        # 计算质量分数
        score = 0.0
        issues = []
        
        # 任务数量合理性 (3-10个任务最佳)
        if 3 <= total_tasks <= 10:
            score += 0.3
        elif total_tasks > 10:
            issues.append("Too many subtasks, consider merging")
        else:
            issues.append("Too few subtasks, consider decomposition")
        
        # 平均时长合理性 (30-180分钟最佳)
        if 30 <= metrics["avg_duration"] <= 180:
            score += 0.3
        else:
            issues.append("Task duration may be too short or too long")
        
        # 依赖复杂度 (平均1-2个依赖最佳)
        if 0.5 <= metrics["dependency_complexity"] <= 2.0:
            score += 0.2
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
        
        return {
            "score": score,
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
            "configuration": {
                "max_depth": self.max_depth,
                "min_task_size": self.min_task_size,
                "enable_optimization": self.enable_optimization,
                "confidence_threshold": self.confidence_threshold
            },
            "last_check": "2024-01-01T00:00:00Z"  # 实际实现中应该是当前时间
        }
