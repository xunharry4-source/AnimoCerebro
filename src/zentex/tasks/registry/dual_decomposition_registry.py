from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timezone

from zentex.plugins.contracts import (
    BasePluginSpec, FunctionalPluginSpec, PluginLifecycleStatus, 
    PluginHealthStatus, PluginLayer
)
from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistryAuditRecord

# 导入两种拆分器
from zentex.tasks.simple_llm_decomposer import LLMTaskDecompositionPlugin, LLMTaskDecompositionSpec, TaskDecompositionStrategy
from zentex.tasks.semantic_kernel_decomposer import (
    SemanticKernelTaskDecompositionPlugin, SemanticKernelTaskDecompositionSpec
)

logger = logging.getLogger(__name__)

class DualDecompositionPluginRegistry(AbstractPluginRegistry):
    """
    双重任务拆解插件注册中心
    
    支持同时管理LLM和Semantic Kernel两种任务拆解方式，
    提供灵活的拆解策略选择和切换。
    """
    
    def __init__(self) -> None:
        """初始化双重拆解插件注册中心"""
        super().__init__(BasePluginSpec)
        self._llm_plugins: Dict[str, LLMTaskDecompositionPlugin] = {}
        self._semantic_kernel_plugins: Dict[str, SemanticKernelTaskDecompositionPlugin] = {}
        self._default_llm_plugin: Optional[str] = None
        self._default_semantic_plugin: Optional[str] = None
        self._default_decomposition_type: str = "llm"  # 默认使用LLM
        
        logger.info("DualDecompositionPluginRegistry initialized")
    
    def register_llm_plugin(self, spec: LLMTaskDecompositionSpec) -> bool:
        """
        注册LLM任务拆解插件
        
        Args:
            spec: LLM插件规范
            
        Returns:
            注册是否成功
        """
        try:
            # 创建插件实例
            plugin_instance = LLMTaskDecompositionPlugin(spec)
            
            # 注册LLM插件
            self._llm_plugins[spec.plugin_id] = plugin_instance
            
            # 如果是第一个注册的LLM插件，设为默认
            if self._default_llm_plugin is None:
                self._default_llm_plugin = spec.plugin_id
                logger.info(f"Set {spec.plugin_id} as default LLM decomposition plugin")
            
            logger.info(f"Successfully registered LLM plugin: {spec.plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register LLM plugin {spec.plugin_id}: {e}")
            return False
    
    def register_semantic_kernel_plugin(self, spec: SemanticKernelTaskDecompositionSpec) -> bool:
        """
        注册Semantic Kernel任务拆解插件
        
        Args:
            spec: Semantic Kernel插件规范
            
        Returns:
            注册是否成功
        """
        try:
            # 创建插件实例
            plugin_instance = SemanticKernelTaskDecompositionPlugin(spec)
            
            # 注册Semantic Kernel插件
            self._semantic_kernel_plugins[spec.plugin_id] = plugin_instance
            
            # 如果是第一个注册的Semantic Kernel插件，设为默认
            if self._default_semantic_plugin is None:
                self._default_semantic_plugin = spec.plugin_id
                logger.info(f"Set {spec.plugin_id} as default Semantic Kernel decomposition plugin")
            
            logger.info(f"Successfully registered Semantic Kernel plugin: {spec.plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register Semantic Kernel plugin {spec.plugin_id}: {e}")
            return False
    
    def get_llm_plugin(self, plugin_id: Optional[str] = None) -> Optional[LLMTaskDecompositionPlugin]:
        """
        获取LLM任务拆解插件
        
        Args:
            plugin_id: 插件ID，如果为None则返回默认插件
            
        Returns:
            LLM插件实例
        """
        if plugin_id is None:
            plugin_id = self._default_llm_plugin
        
        if plugin_id is None:
            logger.warning("No default LLM decomposition plugin available")
            return None
        
        return self._llm_plugins.get(plugin_id)
    
    def get_semantic_kernel_plugin(self, plugin_id: Optional[str] = None) -> Optional[SemanticKernelTaskDecompositionPlugin]:
        """
        获取Semantic Kernel任务拆解插件
        
        Args:
            plugin_id: 插件ID，如果为None则返回默认插件
            
        Returns:
            Semantic Kernel插件实例
        """
        if plugin_id is None:
            plugin_id = self._default_semantic_plugin
        
        if plugin_id is None:
            logger.warning("No default Semantic Kernel decomposition plugin available")
            return None
        
        return self._semantic_kernel_plugins.get(plugin_id)
    
    def set_default_llm_plugin(self, plugin_id: str) -> bool:
        """
        设置默认LLM任务拆解插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            设置是否成功
        """
        if plugin_id not in self._llm_plugins:
            logger.error(f"LLM plugin {plugin_id} is not registered")
            return False
        
        self._default_llm_plugin = plugin_id
        logger.info(f"Set {plugin_id} as default LLM decomposition plugin")
        return True
    
    def set_default_semantic_kernel_plugin(self, plugin_id: str) -> bool:
        """
        设置默认Semantic Kernel任务拆解插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            设置是否成功
        """
        if plugin_id not in self._semantic_kernel_plugins:
            logger.error(f"Semantic Kernel plugin {plugin_id} is not registered")
            return False
        
        self._default_semantic_plugin = plugin_id
        logger.info(f"Set {plugin_id} as default Semantic Kernel decomposition plugin")
        return True
    
    def set_default_decomposition_type(self, decomposition_type: str) -> bool:
        """
        设置默认拆解类型
        
        Args:
            decomposition_type: 拆解类型 ("llm" 或 "semantic_kernel")
            
        Returns:
            设置是否成功
        """
        if decomposition_type in ["llm", "semantic_kernel"]:
            self._default_decomposition_type = decomposition_type
            logger.info(f"Set default decomposition type to: {decomposition_type}")
            return True
        else:
            logger.error(f"Invalid decomposition type: {decomposition_type}")
            return False
    
    def get_default_decomposition_type(self) -> str:
        """获取默认拆解类型"""
        return self._default_decomposition_type
    
    def list_llm_plugins(self) -> List[Dict[str, Any]]:
        """列出所有LLM插件"""
        plugins = []
        for plugin_id, instance in self._llm_plugins.items():
            plugins.append({
                "plugin_id": plugin_id,
                "type": "llm",
                "strategy": instance.strategy.value,
                "health": instance.health_check(),
                "is_default": plugin_id == self._default_llm_plugin
            })
        return plugins
    
    def list_semantic_kernel_plugins(self) -> List[Dict[str, Any]]:
        """列出所有Semantic Kernel插件"""
        plugins = []
        for plugin_id, instance in self._semantic_kernel_plugins.items():
            plugins.append({
                "plugin_id": plugin_id,
                "type": "semantic_kernel",
                "strategy": instance.strategy.value,
                "health": instance.health_check(),
                "is_default": plugin_id == self._default_semantic_plugin
            })
        return plugins
    
    def list_all_plugins(self) -> List[Dict[str, Any]]:
        """列出所有插件（LLM + Semantic Kernel）"""
        return self.list_llm_plugins() + self.list_semantic_kernel_plugins()
    
    def get_available_llm_strategies(self) -> List[str]:
        """获取可用的LLM拆解策略"""
        return list(set(instance.strategy.value for instance in self._llm_plugins.values()))
    
    def get_available_semantic_kernel_strategies(self) -> List[str]:
        """获取可用的Semantic Kernel拆解策略"""
        return list(set(instance.strategy.value for instance in self._semantic_kernel_plugins.values()))
    
    def get_all_available_strategies(self) -> Dict[str, List[str]]:
        """获取所有可用策略"""
        return {
            "llm": self.get_available_llm_strategies(),
            "semantic_kernel": self.get_available_semantic_kernel_strategies()
        }

# 预定义的LLM插件规范
DEFAULT_LLM_SEQUENTIAL_DECOMPOSITION_SPEC = LLMTaskDecompositionSpec(
    plugin_id="default-llm-sequential-decomposer",
    version="1.0.0",
    feature_code="llm.task_decomposition.sequential",
    name="Default LLM Sequential Task Decomposer",
    description="基于LLM的顺序任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.SEQUENTIAL,
    max_depth=5,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

DEFAULT_LLM_PARALLEL_DECOMPOSITION_SPEC = LLMTaskDecompositionSpec(
    plugin_id="default-llm-parallel-decomposer",
    version="1.0.0",
    feature_code="llm.task_decomposition.parallel",
    name="Default LLM Parallel Task Decomposer",
    description="基于LLM的并行任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.PARALLEL,
    max_depth=3,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

DEFAULT_LLM_HYBRID_DECOMPOSITION_SPEC = LLMTaskDecompositionSpec(
    plugin_id="default-llm-hybrid-decomposer",
    version="1.0.0",
    feature_code="llm.task_decomposition.hybrid",
    name="Default LLM Hybrid Task Decomposer",
    description="基于LLM的混合任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.HYBRID,
    max_depth=4,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

# 预定义的Semantic Kernel插件规范
DEFAULT_SEMANTIC_SEQUENTIAL_DECOMPOSITION_SPEC = SemanticKernelTaskDecompositionSpec(
    plugin_id="default-semantic-sequential-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.sequential",
    name="Default Semantic Sequential Task Decomposer",
    description="基于Semantic Kernel的顺序任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.SEQUENTIAL,
    max_depth=5,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8,
    semantic_model="gpt-4",
    reasoning_model="gpt-3.5-turbo",
    enable_planning=True,
    enable_memory=True,
    context_window=8000
)

DEFAULT_SEMANTIC_HYBRID_DECOMPOSITION_SPEC = SemanticKernelTaskDecompositionSpec(
    plugin_id="default-semantic-hybrid-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.hybrid",
    name="Default Semantic Hybrid Task Decomposer",
    description="基于Semantic Kernel的混合任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.HYBRID,
    max_depth=4,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8,
    semantic_model="gpt-4",
    reasoning_model="gpt-3.5-turbo",
    enable_planning=True,
    enable_memory=True,
    context_window=8000
)

def create_default_dual_decomposition_registry() -> DualDecompositionPluginRegistry:
    """
    创建默认的双重拆解插件注册中心
    
    Returns:
        配置好的双重拆解插件注册中心
    """
    registry = DualDecompositionPluginRegistry()
    
    # 注册默认LLM插件
    llm_plugins = [
        DEFAULT_LLM_SEQUENTIAL_DECOMPOSITION_SPEC,
        DEFAULT_LLM_PARALLEL_DECOMPOSITION_SPEC,
        DEFAULT_LLM_HYBRID_DECOMPOSITION_SPEC
    ]
    
    for spec in llm_plugins:
        success = registry.register_llm_plugin(spec)
        if success:
            logger.info(f"Registered default LLM plugin: {spec.plugin_id}")
        else:
            logger.error(f"Failed to register default LLM plugin: {spec.plugin_id}")
    
    # 注册默认Semantic Kernel插件
    semantic_plugins = [
        DEFAULT_SEMANTIC_SEQUENTIAL_DECOMPOSITION_SPEC,
        DEFAULT_SEMANTIC_HYBRID_DECOMPOSITION_SPEC
    ]
    
    for spec in semantic_plugins:
        success = registry.register_semantic_kernel_plugin(spec)
        if success:
            logger.info(f"Registered default Semantic Kernel plugin: {spec.plugin_id}")
        else:
            logger.error(f"Failed to register default Semantic Kernel plugin: {spec.plugin_id}")
    
    return registry

class DualDecompositionPluginManager:
    """
    双重任务拆解插件管理器
    
    提供统一的接口来管理LLM和Semantic Kernel两种拆解方式，
    支持动态切换和对比分析。
    """
    
    def __init__(self, registry: Optional[DualDecompositionPluginRegistry] = None) -> None:
        """
        初始化双重拆解插件管理器
        
        Args:
            registry: 插件注册中心，如果为None则创建默认注册中心
        """
        self.registry = registry or create_default_dual_decomposition_registry()
        logger.info("DualDecompositionPluginManager initialized")
    
    def decompose_with_llm(self, mission_title: str, mission_content: str, 
                          strategy: Optional[str] = None, 
                          context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        使用LLM拆解任务
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            strategy: 拆解策略
            context: 上下文信息
            
        Returns:
            子任务列表
        """
        plugin = self.registry.get_llm_plugin()
        
        if not plugin:
            logger.error("No LLM decomposition plugin available")
            return []
        
        return plugin.decompose_mission(mission_title, mission_content, context)
    
    def decompose_with_semantic_kernel(self, mission_title: str, mission_content: str, 
                                   strategy: Optional[str] = None, 
                                   context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        使用Semantic Kernel拆解任务
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            strategy: 拆解策略
            context: 上下文信息
            
        Returns:
            子任务列表
        """
        plugin = self.registry.get_semantic_kernel_plugin()
        
        if not plugin:
            logger.error("No Semantic Kernel decomposition plugin available")
            return []
        
        return plugin.decompose_mission(mission_title, mission_content, context)
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         decomposition_type: Optional[str] = None,
                         strategy: Optional[str] = None, 
                         context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        统一的任务拆解接口
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            decomposition_type: 拆解类型 ("llm", "semantic_kernel", 或None使用默认)
            strategy: 拆解策略
            context: 上下文信息
            
        Returns:
            包含拆解结果和元数据的字典
        """
        # 确定拆解类型
        if decomposition_type is None:
            decomposition_type = self.registry.get_default_decomposition_type()
        
        if decomposition_type == "llm":
            subtasks = self.decompose_with_llm(mission_title, mission_content, strategy, context)
            return {
                "success": len(subtasks) > 0,
                "decomposition_type": "llm",
                "subtasks": subtasks,
                "plugin_used": self.registry._default_llm_plugin,
                "strategy": strategy,
                "metadata": {
                    "model": "LLM",
                    "reasoning": "Large Language Model",
                    "capabilities": ["text_understanding", "task_planning"]
                }
            }
        elif decomposition_type == "semantic_kernel":
            subtasks = self.decompose_with_semantic_kernel(mission_title, mission_content, strategy, context)
            return {
                "success": len(subtasks) > 0,
                "decomposition_type": "semantic_kernel",
                "subtasks": subtasks,
                "plugin_used": self.registry._default_semantic_plugin,
                "strategy": strategy,
                "metadata": {
                    "model": "Semantic Kernel",
                    "reasoning": "Multi-model semantic reasoning",
                    "capabilities": ["deep_semantic_understanding", "domain_expertise", "memory_management"]
                }
            }
        else:
            return {
                "success": False,
                "error": f"Unknown decomposition type: {decomposition_type}",
                "decomposition_type": decomposition_type,
                "subtasks": []
            }
    
    def compare_decomposition_methods(self, mission_title: str, mission_content: str, 
                                 strategy: Optional[str] = None, 
                                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        对比LLM和Semantic Kernel两种拆解方法
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            strategy: 拆解策略
            context: 上下文信息
            
        Returns:
            对比结果
        """
        # LLM拆分
        llm_result = self.decompose_with_llm(mission_title, mission_content, strategy, context)
        
        # Semantic Kernel拆分
        semantic_result = self.decompose_with_semantic_kernel(mission_title, mission_content, strategy, context)
        
        # 生成对比分析
        comparison = {
            "mission_title": mission_title,
            "llm_decomposition": {
                "success": len(llm_result) > 0,
                "subtask_count": len(llm_result),
                "subtasks": llm_result,
                "characteristics": {
                    "reasoning_depth": "medium",
                    "semantic_understanding": "basic",
                    "domain_expertise": "general",
                    "planning_capability": "basic"
                }
            },
            "semantic_kernel_decomposition": {
                "success": len(semantic_result) > 0,
                "subtask_count": len(semantic_result),
                "subtasks": semantic_result,
                "characteristics": {
                    "reasoning_depth": "deep",
                    "semantic_understanding": "advanced",
                    "domain_expertise": "specialized",
                    "planning_capability": "advanced"
                }
            },
            "comparison_metrics": {
                "subtask_count_difference": len(semantic_result) - len(llm_result),
                "llm_avg_duration": sum(st.get("estimated_duration", 0) for st in llm_result) / len(llm_result) if llm_result else 0,
                "semantic_avg_duration": sum(st.get("estimated_duration", 0) for st in semantic_result) / len(semantic_result) if semantic_result else 0,
                "llm_has_semantic_tags": any(st.get("semantic_tags") for st in llm_result),
                "semantic_has_semantic_tags": any(st.get("semantic_tags") for st in semantic_result),
                "llm_risk_diversity": len(set(st.get("risk_level", "medium") for st in llm_result)),
                "semantic_risk_diversity": len(set(st.get("risk_level", "medium") for st in semantic_result))
            }
        }
        
        return comparison
    
    def get_available_strategies(self, decomposition_type: Optional[str] = None) -> Dict[str, List[str]]:
        """
        获取可用策略
        
        Args:
            decomposition_type: 拆解类型，如果为None则返回所有类型
            
        Returns:
            按类型分组的可用策略
        """
        if decomposition_type == "llm":
            return {"llm": self.registry.get_available_llm_strategies()}
        elif decomposition_type == "semantic_kernel":
            return {"semantic_kernel": self.registry.get_available_semantic_kernel_strategies()}
        else:
            return self.registry.get_all_available_strategies()
    
    def set_default_decomposition_type(self, decomposition_type: str) -> bool:
        """设置默认拆解类型"""
        return self.registry.set_default_decomposition_type(decomposition_type)
    
    def get_default_decomposition_type(self) -> str:
        """获取默认拆解类型"""
        return self.registry.get_default_decomposition_type()
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息"""
        llm_plugins = len(self.registry._llm_plugins)
        semantic_plugins = len(self.registry._semantic_kernel_plugins)
        
        return {
            "total_plugins": llm_plugins + semantic_plugins,
            "llm_plugins": llm_plugins,
            "semantic_kernel_plugins": semantic_plugins,
            "default_decomposition_type": self.registry.get_default_decomposition_type(),
            "default_llm_plugin": self.registry._default_llm_plugin,
            "default_semantic_plugin": self.registry._default_semantic_plugin,
            "available_strategies": self.registry.get_all_available_strategies()
        }
