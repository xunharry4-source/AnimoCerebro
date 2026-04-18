from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timezone

from zentex.plugins.contracts import (
    BasePluginSpec, FunctionalPluginSpec, PluginLifecycleStatus, 
    PluginHealthStatus, PluginLayer
)
from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistryAuditRecord
from zentex.tasks.plugins.decomposition_plugin_llm import TaskDecompositionPlugin as LLMTaskDecompositionPlugin, TaskDecompositionPluginSpec, TaskDecompositionStrategy
logger = logging.getLogger(__name__)

class TaskPluginRegistry(AbstractPluginRegistry[TaskDecompositionPluginSpec]):
    """
    任务插件注册中心
    
    负责管理任务相关的插件，包括任务拆解插件、
    任务执行插件、任务监控插件等。
    """
    
    def __init__(self) -> None:
        """初始化任务插件注册中心"""
        super().__init__(TaskDecompositionPluginSpec)
        self._plugin_instances: Dict[str, TaskDecompositionPlugin] = {}
        self._default_decomposition_plugin: Optional[str] = None
        logger.info("TaskPluginRegistry initialized")
    
    def register_decomposition_plugin(self, spec: TaskDecompositionPluginSpec) -> bool:
        """
        注册任务拆解插件
        
        Args:
            spec: 插件规范
            
        Returns:
            注册是否成功
        """
        try:
            # 注册插件规范
            registered_spec = self.register(spec)
            if not registered_spec:
                logger.error(f"Failed to register decomposition plugin: {spec.plugin_id}")
                return False
            
            # 创建插件实例
            plugin_instance = TaskDecompositionPlugin(registered_spec)
            self._plugin_instances[spec.plugin_id] = plugin_instance
            
            # 如果是第一个注册的插件，设为默认
            if self._default_decomposition_plugin is None:
                self._default_decomposition_plugin = spec.plugin_id
                logger.info(f"Set {spec.plugin_id} as default decomposition plugin")
            
            logger.info(f"Successfully registered decomposition plugin: {spec.plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register decomposition plugin {spec.plugin_id}: {e}")
            return False
    
    def get_decomposition_plugin(self, plugin_id: Optional[str] = None) -> Optional[TaskDecompositionPlugin]:
        """
        获取任务拆解插件
        
        Args:
            plugin_id: 插件ID，如果为None则返回默认插件
            
        Returns:
            插件实例
        """
        if plugin_id is None:
            plugin_id = self._default_decomposition_plugin
        
        if plugin_id is None:
            logger.warning("No default decomposition plugin available")
            return None
        
        return self._plugin_instances.get(plugin_id)
    
    def set_default_decomposition_plugin(self, plugin_id: str) -> bool:
        """
        设置默认任务拆解插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            设置是否成功
        """
        if plugin_id not in self._plugin_instances:
            logger.error(f"Plugin {plugin_id} not found")
            return False
        
        # 检查插件状态
        plugin_spec = self.get_registered_plugin(plugin_id)
        if plugin_spec.lifecycle_status != PluginLifecycleStatus.ACTIVE:
            logger.error(f"Plugin {plugin_id} is not active")
            return False
        
        self._default_decomposition_plugin = plugin_id
        logger.info(f"Set {plugin_id} as default decomposition plugin")
        return True
    
    def list_decomposition_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有任务拆解插件
        
        Returns:
            插件信息列表
        """
        plugins = []
        for plugin_id, instance in self._plugin_instances.items():
            spec = self.get_registered_plugin(plugin_id)
            if spec:
                plugins.append({
                    "plugin_id": plugin_id,
                    "version": spec.version,
                    "status": spec.lifecycle_status.value,
                    "strategy": instance.strategy.value,
                    "is_default": plugin_id == self._default_decomposition_plugin,
                    "health": instance.health_check()
                })
        
        return plugins
    
    def get_plugin_health_status(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取插件健康状态
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            健康状态信息
        """
        plugin = self._plugin_instances.get(plugin_id)
        if not plugin:
            return None
        
        return plugin.health_check()
    
    def promote_plugin_to_active(self, plugin_id: str, audit_reason: str) -> bool:
        """
        将插件提升为活跃状态
        
        Args:
            plugin_id: 插件ID
            audit_reason: 审计原因
            
        Returns:
            提升是否成功
        """
        try:
            # 首先提升到沙箱验证状态
            if plugin_id in self._plugins:
                current_spec = self._plugins[plugin_id]
                if current_spec.lifecycle_status == PluginLifecycleStatus.CANDIDATE:
                    self.promote_plugin(plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, 
                                      "Ready for sandbox verification")
            
            # 然后提升到活跃状态
            promoted = self.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, audit_reason)
            
            if promoted:
                logger.info(f"Successfully promoted plugin {plugin_id} to active")
                return True
            else:
                logger.error(f"Failed to promote plugin {plugin_id} to active")
                return False
                
        except Exception as e:
            logger.error(f"Error promoting plugin {plugin_id}: {e}")
            return False
    
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
            # 撤销插件规范
            revoked_spec = self.revoke_plugin(plugin_id, reason)
            
            # 如果是默认插件，清除默认设置
            if self._default_decomposition_plugin == plugin_id:
                self._default_decomposition_plugin = None
                # 选择新的默认插件
                active_plugins = [pid for pid, spec in self._plugins.items() 
                                if spec.lifecycle_status == PluginLifecycleStatus.ACTIVE and pid != plugin_id]
                if active_plugins:
                    self._default_decomposition_plugin = active_plugins[0]
                    logger.info(f"Set {active_plugins[0]} as new default decomposition plugin")
            
            logger.info(f"Successfully revoked plugin {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke plugin {plugin_id}: {e}")
            return False

# 预定义的任务拆解插件规范 - LLM版本
DEFAULT_SEQUENTIAL_DECOMPOSITION_SPEC = TaskDecompositionPluginSpec(
    plugin_id="llm-sequential-decomposer",
    version="1.0.0",
    feature_code="task_decomposition.sequential",
    name="LLM Sequential Task Decomposer",
    description="基于LLM的顺序任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.SEQUENTIAL,
    max_depth=5,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

DEFAULT_PARALLEL_DECOMPOSITION_SPEC = TaskDecompositionPluginSpec(
    plugin_id="llm-parallel-decomposer",
    version="1.0.0",
    feature_code="task_decomposition.parallel",
    name="LLM Parallel Task Decomposer",
    description="基于LLM的并行任务拆解插件",
    author="Zentex Team",
    strategy=TaskDecompositionStrategy.PARALLEL,
    max_depth=4,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

DEFAULT_HYBRID_DECOMPOSITION_SPEC = TaskDecompositionPluginSpec(
    plugin_id="default-hybrid-decomposer",
    version="1.0.0",
    feature_code="task_decomposition.hybrid",
    plugin_layer=PluginLayer.FUNCTIONAL,
    is_concurrency_safe=True,
    lifecycle_status=PluginLifecycleStatus.ACTIVE,
    health_status=PluginHealthStatus.HEALTHY,
    rollback_conditions=[
        "Hybrid strategy fails to balance efficiency and coordination",
        "Sequential and parallel phases conflict",
        "Quality score below threshold"
    ],
    revocation_reasons=[],
    strategy="hybrid",
    max_depth=6,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.75
)

def create_default_task_plugin_registry() -> TaskPluginRegistry:
    """
    创建默认的任务插件注册中心
    
    Returns:
        配置好的任务插件注册中心
    """
    registry = TaskPluginRegistry()
    
    # 注册默认的拆解插件
    default_plugins = [
        DEFAULT_SEQUENTIAL_DECOMPOSITION_SPEC,
        DEFAULT_PARALLEL_DECOMPOSITION_SPEC,
        DEFAULT_HYBRID_DECOMPOSITION_SPEC
    ]
    
    for spec in default_plugins:
        success = registry.register_decomposition_plugin(spec)
        if success:
            logger.info(f"Registered default plugin: {spec.plugin_id}")
        else:
            logger.error(f"Failed to register default plugin: {spec.plugin_id}")
    
    return registry

class TaskPluginManager:
    """
    任务插件管理器
    
    提供统一的插件管理接口，简化插件的使用和管理。
    """
    
    def __init__(self, registry: Optional[TaskPluginRegistry] = None) -> None:
        """
        初始化插件管理器
        
        Args:
            registry: 插件注册中心，如果为None则创建默认注册中心
        """
        self.registry = registry or create_default_task_plugin_registry()
        logger.info("TaskPluginManager initialized")
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         strategy: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        使用指定策略拆解任务
        
        Args:
            mission_title: 任务标题
            mission_content: 任务内容
            strategy: 拆解策略，如果为None则使用默认策略
            context: 上下文信息
            
        Returns:
            子任务列表
        """
        plugin = self.registry.get_decomposition_plugin()
        if not plugin:
            logger.error("No decomposition plugin available")
            return []
        
        # 如果指定了策略，尝试获取对应的插件
        if strategy:
            for plugin_id, instance in self.registry._plugin_instances.items():
                if instance.strategy.value == strategy:
                    plugin = instance
                    break
        
        try:
            subtasks = plugin.decompose_mission(mission_title, mission_content, context)
            
            # 评估拆解质量
            quality = plugin.get_decomposition_quality(subtasks)
            logger.info(f"Decomposition quality score: {quality['score']:.2f}")
            
            if quality['score'] < plugin.confidence_threshold:
                logger.warning(f"Decomposition quality below threshold: {quality['issues']}")
            
            return subtasks
            
        except Exception as e:
            logger.error(f"Failed to decompose mission: {e}")
            return []
    
    def get_available_strategies(self) -> List[str]:
        """
        获取可用的拆解策略
        
        Returns:
            策略列表
        """
        strategies = []
        for instance in self.registry._plugin_instances.values():
            strategies.append(instance.strategy.value)
        return list(set(strategies))
    
    def get_plugin_info(self, plugin_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取插件信息
        
        Args:
            plugin_id: 插件ID，如果为None则返回默认插件信息
            
        Returns:
            插件信息
        """
        if plugin_id is None:
            plugin_id = self.registry._default_decomposition_plugin
        
        if plugin_id is None:
            return None
        
        instance = self.registry._plugin_instances.get(plugin_id)
        if not instance:
            return None
        
        spec = self.registry.get_registered_plugin(plugin_id)
        if not spec:
            return None
        
        return {
            "plugin_id": plugin_id,
            "version": spec.version,
            "feature_code": spec.feature_code,
            "status": spec.lifecycle_status.value,
            "strategy": instance.strategy.value,
            "configuration": {
                "max_depth": instance.max_depth,
                "min_task_size": instance.min_task_size,
                "enable_optimization": instance.enable_optimization,
                "confidence_threshold": instance.confidence_threshold
            },
            "health": instance.health_check(),
            "is_default": plugin_id == self.registry._default_decomposition_plugin
        }
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有插件
        
        Returns:
            插件列表
        """
        return self.registry.list_decomposition_plugins()
    
    def set_default_strategy(self, strategy: str) -> bool:
        """
        设置默认拆解策略
        
        Args:
            strategy: 策略名称
            
        Returns:
            设置是否成功
        """
        # 查找对应策略的插件
        for plugin_id, instance in self.registry._plugin_instances.items():
            if instance.strategy.value == strategy:
                return self.registry.set_default_decomposition_plugin(plugin_id)
        
        logger.error(f"No plugin found for strategy: {strategy}")
        return False
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        获取注册中心统计信息
        
        Returns:
            统计信息
        """
        total_plugins = len(self.registry._plugins)
        active_plugins = len([spec for spec in self.registry._plugins.values() 
                            if spec.lifecycle_status == PluginLifecycleStatus.ACTIVE])
        
        return {
            "total_plugins": total_plugins,
            "active_plugins": active_plugins,
            "default_plugin": self.registry._default_decomposition_plugin,
            "available_strategies": self.get_available_strategies(),
            "audit_records_count": len(self.registry.get_audit_records())
        }
