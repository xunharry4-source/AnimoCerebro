# Core Module / 核心模块

## Overview / 概述

This module contains the fundamental specifications, models, and base classes for the Zentex system. It defines the core architecture including plugin systems, cognitive tools, execution specifications, and data models.

本模块包含Zentex系统的基本规范、模型和基类。它定义了核心架构，包括插件系统、认知工具、执行规范和数据模型。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.core import (
    # Plugin base classes / 插件基类
    BasePluginSpec,
    FunctionalPluginSpec,
    LogicalCognitivePluginSpec,
    PluginLifecycleStatus,
    PluginHealthStatus,
    
    # Core models / 核心模型
    BrainRuntimeState,
    CognitiveToolSpec,
    LogicalCognitiveToolSpec,
    
    # Specifications / 规范
    ExecutionSpec,
    SensoryAdapterSpec,
    SimulationDomainPlugin,
    ModelProviderSpec,
    
    # Runtime and families / 运行时和家族
    PluginFamily,
    PluginRuntime,
    FeatureFamily,
    
    # Configuration / 配置
    Config,
)
```

## Core Components / 核心组件

### Plugin System / 插件系统

- **BasePluginSpec** (`plugin_base.py`): Abstract base for all plugins / 所有插件的抽象基类
- **FunctionalPluginSpec** (`plugin_base.py`): Functional plugin specification / 功能性插件规范
- **LogicalCognitivePluginSpec** (`plugin_base.py`): Logical cognitive plugin spec / 逻辑认知插件规范
- **PluginRuntime** (`plugin_runtime.py`): Plugin runtime management / 插件运行时管理

### Specifications / 规范

- **CognitiveToolSpec** (`models.py`): Cognitive tool specification / 认知工具规范
- **ExecutionSpec** (`execution_spec.py`): Execution specification / 执行规范
- **SensoryAdapterSpec** (`sensory_spec.py`): Sensory adapter specification / 感官适配器规范
- **SimulationDomainPlugin** (`simulation_spec.py`): Simulation domain plugin / 模拟域插件
- **ModelProviderSpec** (`model_provider_spec.py`): Model provider specification / 模型提供商规范

### Models / 模型

- **BrainRuntimeState** (`models.py`): Brain runtime state representation / 大脑运行时状态表示
- **PluginFamily** (`plugin_family.py`): Plugin family grouping / 插件家族分组
- **FeatureFamily** (`feature_family.py`): Feature family grouping / 特性家族分组

## Usage Example / 使用示例

```python
from zentex.core import BasePluginSpec, CognitiveToolSpec, PluginRuntime

# Use only the public interface / 仅使用公共接口
class MyPlugin(BasePluginSpec):
    pass

runtime = PluginRuntime()
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.core` only, never from `zentex.core.plugin_base` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.core` 导入，绝不能从 `zentex.core.plugin_base` 或其他内部路径导入。
