from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timezone

from zentex.core.plugin_base import (
    BasePluginSpec, FunctionalPluginSpec, PluginLifecycleStatus, 
    PluginHealthStatus, PluginLayer
)
from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistryAuditRecord
from zentex.tasks.semantic_kernel_decomposer import (
    SemanticKernelTaskDecompositionPlugin, SemanticKernelTaskDecompositionSpec, TaskDecompositionStrategy
)

logger = logging.getLogger(__name__)

class SemanticKernelPluginRegistry(AbstractPluginRegistry[SemanticKernelTaskDecompositionSpec]):
    """
    Semantic Kernel任务插件注册中心
    
    负责管理基于Semantic Kernel的任务相关插件，
    包括智能任务拆解、语义分析、规划推理等。
    """
    
    def __init__(self) -> None:
        """初始化Semantic Kernel插件注册中心"""
        super().__init__(SemanticKernelTaskDecompositionSpec)
        self._plugin_instances: Dict[str, SemanticKernelTaskDecompositionPlugin] = {}
        self._default_decomposition_plugin: Optional[str] = None
        logger.info("SemanticKernelPluginRegistry initialized")
    
    def register_decomposition_plugin(self, spec: SemanticKernelTaskDecompositionSpec) -> bool:
        """
        注册Semantic Kernel任务拆解插件
        
        Args:
            spec: 插件规范
            
        Returns:
            注册是否成功
        """
        try:
            # 验证插件规范
            if not self._validate_semantic_spec(spec):
                logger.error(f"Invalid Semantic Kernel plugin spec: {spec.plugin_id}")
                return False
            
            # 创建插件实例
            plugin_instance = SemanticKernelTaskDecompositionPlugin(spec)
            
            # 注册插件
            self._plugins[spec.plugin_id] = spec
            self._plugin_instances[spec.plugin_id] = plugin_instance
            
            # 如果是第一个注册的插件，设为默认
            if self._default_decomposition_plugin is None:
                self._default_decomposition_plugin = spec.plugin_id
                logger.info(f"Set {spec.plugin_id} as default Semantic Kernel decomposition plugin")
            
            logger.info(f"Successfully registered Semantic Kernel plugin: {spec.plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register Semantic Kernel plugin {spec.plugin_id}: {e}")
            return False
    
    def get_decomposition_plugin(self, plugin_id: Optional[str] = None) -> Optional[SemanticKernelTaskDecompositionPlugin]:
        """
        获取Semantic Kernel任务拆解插件
        
        Args:
            plugin_id: 插件ID，如果为None则返回默认插件
            
        Returns:
            插件实例
        """
        if plugin_id is None:
            plugin_id = self._default_decomposition_plugin
        
        if plugin_id is None:
            logger.warning("No default Semantic Kernel decomposition plugin available")
            return None
        
        return self._plugin_instances.get(plugin_id)
    
    def set_default_decomposition_plugin(self, plugin_id: str) -> bool:
        """
        设置默认Semantic Kernel任务拆解插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            设置是否成功
        """
        if plugin_id not in self._plugins:
            logger.error(f"Semantic Kernel plugin {plugin_id} is not registered")
            return False
        
        if self._plugins[plugin_id].status != PluginLifecycleStatus.ACTIVE:
            logger.error(f"Semantic Kernel plugin {plugin_id} is not active")
            return False
        
        self._default_decomposition_plugin = plugin_id
        logger.info(f"Set {plugin_id} as default Semantic Kernel decomposition plugin")
        return True
    
    def list_decomposition_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有Semantic Kernel任务拆解插件
        
        Returns:
            插件信息列表
        """
        plugins = []
        for plugin_id, spec in self._plugins.items():
            instance = self._plugin_instances.get(plugin_id)
            if instance:
                plugins.append({
                    "plugin_id": plugin_id,
                    "name": spec.name,
                    "version": spec.version,
                    "description": spec.description,
                    "author": spec.author,
                    "status": spec.status.value,
                    "strategy": instance.strategy.value,
                    "is_default": plugin_id == self._default_decomposition_plugin,
                    "health": instance.health_check()
                })
        
        return plugins
    
    def get_semantic_analysis_plugin(self) -> Optional[SemanticKernelTaskDecompositionPlugin]:
        """
        获取语义分析插件
        
        Returns:
            语义分析插件实例
        """
        return self.get_decomposition_plugin()
    
    def revoke_plugin(self, plugin_id: str, reason: str) -> bool:
        """
        撤销插件
        
        Args:
            plugin_id: 插件ID
            reason: 撤销原因
            
        Returns:
            撤销是否成功
        """
        try:
            if plugin_id not in self._plugins:
                logger.error(f"Semantic Kernel plugin {plugin_id} is not registered")
                return False
            
            # 更新插件状态
            spec = self._plugins[plugin_id]
            spec.status = PluginLifecycleStatus.REVOKED
            spec.revoked_at = datetime.now(timezone.utc)
            spec.revocation_reason = reason
            
            # 移除插件实例
            if plugin_id in self._plugin_instances:
                del self._plugin_instances[plugin_id]
            
            # 如果是默认插件，清除默认设置
            if self._default_decomposition_plugin == plugin_id:
                self._default_decomposition_plugin = None
                # 选择新的默认插件
                active_plugins = [pid for pid, spec in self._plugins.items() 
                                if spec.status == PluginLifecycleStatus.ACTIVE and pid != plugin_id]
                if active_plugins:
                    self._default_decomposition_plugin = active_plugins[0]
                    logger.info(f"Set {active_plugins[0]} as new default Semantic Kernel decomposition plugin")
            
            logger.info(f"Successfully revoked Semantic Kernel plugin {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke Semantic Kernel plugin {plugin_id}: {e}")
            return False
    
    def _validate_semantic_spec(self, spec: SemanticKernelTaskDecompositionSpec) -> bool:
        """
        验证Semantic Kernel插件规范
        
        Args:
            spec: 插件规范
            
        Returns:
            验证是否通过
        """
        try:
            # 基本字段验证
            if not spec.plugin_id or not spec.plugin_id.strip():
                logger.error("Plugin ID is required")
                return False
            
            if not spec.feature_code or not spec.feature_code.strip():
                logger.error("Feature code is required")
                return False
            
            # Semantic Kernel特定验证
            if not hasattr(spec, 'strategy'):
                logger.error("Strategy is required for Semantic Kernel plugin")
                return False
            
            if not hasattr(spec, 'semantic_model'):
                logger.error("Semantic model is required for Semantic Kernel plugin")
                return False
            
            if not hasattr(spec, 'reasoning_model'):
                logger.error("Reasoning model is required for Semantic Kernel plugin")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating Semantic Kernel spec: {e}")
            return False

# 预定义的Semantic Kernel任务拆解插件规范
DEFAULT_SEMANTIC_SEQUENTIAL_DECOMPOSITION_SPEC = SemanticKernelTaskDecompositionSpec(
    plugin_id="semantic-kernel-sequential-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.sequential",
    name="Semantic Kernel Sequential Task Decomposer",
    description="基于Semantic Kernel的智能顺序任务拆解插件",
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

DEFAULT_SEMANTIC_PARALLEL_DECOMPOSITION_SPEC = SemanticKernelTaskDecompositionSpec(
    plugin_id="semantic-kernel-parallel-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.parallel",
    name="Semantic Kernel Parallel Task Decomposer",
    description="基于Semantic Kernel的智能并行任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.PARALLEL,
    max_depth=3,
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
    plugin_id="semantic-kernel-hybrid-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.hybrid",
    name="Semantic Kernel Hybrid Task Decomposer",
    description="基于Semantic Kernel的智能混合任务拆解插件",
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

DEFAULT_SEMANTIC_DEPENDENCY_DECOMPOSITION_SPEC = SemanticKernelTaskDecompositionSpec(
    plugin_id="semantic-kernel-dependency-decomposer",
    version="1.0.0",
    feature_code="semantic_kernel.task_decomposition.dependency",
    name="Semantic Kernel Dependency-Driven Task Decomposer",
    description="基于Semantic Kernel的智能依赖驱动任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.DEPENDENCY_DRIVEN,
    max_depth=6,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8,
    semantic_model="gpt-4",
    reasoning_model="gpt-3.5-turbo",
    enable_planning=True,
    enable_memory=True,
    context_window=8000
)

def create_default_semantic_kernel_plugin_registry() -> SemanticKernelPluginRegistry:
    """
    创建默认的Semantic Kernel插件注册中心
    
    Returns:
        配置好的Semantic Kernel插件注册中心
    """
    registry = SemanticKernelPluginRegistry()
    
    # 注册默认的Semantic Kernel拆解插件
    default_plugins = [
        DEFAULT_SEMANTIC_SEQUENTIAL_DECOMPOSITION_SPEC,
        DEFAULT_SEMANTIC_PARALLEL_DECOMPOSITION_SPEC,
        DEFAULT_SEMANTIC_HYBRID_DECOMPOSITION_SPEC,
        DEFAULT_SEMANTIC_DEPENDENCY_DECOMPOSITION_SPEC
    ]
    
    for spec in default_plugins:
        success = registry.register_decomposition_plugin(spec)
        if success:
            logger.info(f"Registered default Semantic Kernel plugin: {spec.plugin_id}")
        else:
            logger.error(f"Failed to register default Semantic Kernel plugin: {spec.plugin_id}")
    
    return registry

class SemanticKernelPluginManager:
    """
    Semantic Kernel任务插件管理器
    
    提供统一的Semantic Kernel插件管理接口，
    支持高级语义推理和智能任务拆分。
    """
    
    def __init__(self, registry: Optional[SemanticKernelPluginRegistry] = None) -> None:
        """
        初始化Semantic Kernel插件管理器
        
        Args:
            registry: 插件注册中心，如果为None则创建默认注册中心
        """
        self.registry = registry or create_default_semantic_kernel_plugin_registry()
        logger.info("SemanticKernelPluginManager initialized")
    
    def decompose_mission_with_semantics(self, mission_title: str, mission_content: str, 
                                       strategy: Optional[str] = None, 
                                       context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        使用Semantic Kernel拆解任务
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            strategy: 拆解策略，如果为None则使用默认策略
            context: 上下文信息
            
        Returns:
            子任务列表
        """
        # 获取默认插件
        plugin = self.registry.get_decomposition_plugin()
        
        if not plugin:
            logger.error("No Semantic Kernel decomposition plugin available")
            return []
        
        # 使用Semantic Kernel进行拆分
        return plugin.decompose_mission(mission_title, mission_content, context)
    
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
        plugin = self.registry.get_decomposition_plugin()
        
        if not plugin:
            logger.error("No Semantic Kernel plugin available for analysis")
            return {}
        
        return plugin.get_semantic_analysis(mission_title, mission_content, context)
    
    def get_available_semantic_strategies(self) -> List[str]:
        """获取可用的Semantic Kernel拆解策略"""
        return list(set(instance.strategy.value for instance in self.registry._plugin_instances.values()))
    
    def get_semantic_plugin_info(self, plugin_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取Semantic Kernel插件信息"""
        if plugin_id is None:
            plugin_id = self.registry._default_decomposition_plugin
        
        if plugin_id is None:
            return None
        
        spec = self.registry._plugins.get(plugin_id)
        if not spec:
            return None
        
        instance = self.registry._plugin_instances.get(plugin_id)
        if not instance:
            return None
        
        return {
            "plugin_id": plugin_id,
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "author": spec.author,
            "status": spec.status.value,
            "strategy": instance.strategy.value,
            "semantic_model": instance.semantic_model,
            "reasoning_model": instance.reasoning_model,
            "enable_planning": instance.enable_planning,
            "enable_memory": instance.enable_memory,
            "health": instance.health_check(),
            "is_default": plugin_id == self.registry._default_decomposition_plugin
        }
    
    def list_semantic_plugins(self) -> List[Dict[str, Any]]:
        """列出所有Semantic Kernel插件"""
        return self.registry.list_decomposition_plugins()
    
    def set_default_semantic_strategy(self, strategy: str) -> bool:
        """设置默认Semantic Kernel策略"""
        # 查找对应策略的插件
        for plugin_id, instance in self.registry._plugin_instances.items():
            if instance.strategy.value == strategy:
                return self.registry.set_default_decomposition_plugin(plugin_id)
        
        logger.error(f"No Semantic Kernel plugin found for strategy: {strategy}")
        return False
    
    def get_semantic_registry_stats(self) -> Dict[str, Any]:
        """获取Semantic Kernel注册中心统计信息"""
        total_plugins = len(self.registry._plugins)
        active_plugins = len([spec for spec in self.registry._plugins.values() 
                             if spec.status == PluginLifecycleStatus.ACTIVE])
        
        return {
            "total_plugins": total_plugins,
            "active_plugins": active_plugins,
            "default_plugin": self.registry._default_decomposition_plugin,
            "available_strategies": self.get_available_semantic_strategies(),
            "audit_records_count": len(self.registry.get_audit_records()),
            "semantic_kernel_enabled": True
        }
