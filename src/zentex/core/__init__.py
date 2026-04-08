"""
Zentex Core Module - Fundamental specifications, models, and base classes.

This module defines the core architecture including plugin systems, cognitive tools,
execution specifications, and fundamental data models.

本模块定义核心架构，包括插件系统、认知工具、执行规范和基础数据模型。
"""

from zentex.core.plugin_base import (
    BasePluginSpec,
    FunctionalPluginSpec,
    LogicalCognitivePluginSpec,
    PluginLifecycleStatus,
    PluginHealthStatus,
)
from zentex.core.models import (
    BrainRuntimeState,
    CognitiveToolSpec,
    LogicalCognitiveToolSpec,
)
from zentex.core.simulation_spec import SimulationDomainPlugin
from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.core.feature_family import FeatureFamily

__all__ = [
    # Plugin base classes / 插件基类
    "BasePluginSpec",
    "FunctionalPluginSpec",
    "LogicalCognitivePluginSpec",
    "PluginLifecycleStatus",
    "PluginHealthStatus",

    # Core models / 核心模型
    "BrainRuntimeState",
    "CognitiveToolSpec",
    "LogicalCognitiveToolSpec",

    # Specifications / 规范
    "SimulationDomainPlugin",
    "ModelProviderSpec",

    # Families / 家族
    "FeatureFamily",
]
