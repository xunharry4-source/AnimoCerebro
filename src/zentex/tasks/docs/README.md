# Tasks Module / 任务模块

## Overview / 概述

This module implements task decomposition, management, and execution for the Zentex system. It provides interfaces for breaking down complex tasks, managing task hierarchies, and coordinating task execution with support for both LLM-based and rule-based decomposition strategies.

本模块为Zentex系统实现任务分解、管理和执行。它提供分解复杂任务、管理任务层次结构以及协调任务执行的接口，支持基于LLM和基于规则的分解策略。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.tasks import (
    # Core interface / 核心接口
    TaskServiceInterface,
    
    # Service / 服务
    TaskService,
    
    # Models / 模型
    TaskDefinition,
    TaskResult,
    TaskStatus,
    TaskDecomposition,
    
    # Decomposers / 分解器
    LLMDecomposer,
    SimpleLLMDecomposer,
    SemanticKernelDecomposer,
    
    # Registry / 注册表
    DecompositionPluginRegistry,
    DualDecompositionRegistry,
    
    # Persistence / 持久化
    TaskPersistence,
    
    # Errors / 错误
    TaskError,
    TaskDecompositionError,
)
```

## Core Components / 核心组件

### Service Layer / 服务层

- **TaskService** (`service.py`): Main task service implementation / 主任务服务实现
- **TaskServiceInterface** (`interface.py`): Task service interface definition / 任务服务接口定义

### Task Decomposition / 任务分解

- **LLMDecomposer** (`llm_decomposer.py`): LLM-based task decomposition / 基于LLM的任务分解
- **SimpleLLMDecomposer** (`simple_llm_decomposer.py`): Simplified LLM decomposer / 简化版LLM分解器
- **SemanticKernelDecomposer** (`semantic_kernel_decomposer.py`): Semantic kernel-based decomposition / 基于语义核的分解

### Plugin Registry / 插件注册表

- **DecompositionPluginRegistry** (`plugin_registry.py`): Registers decomposition plugins / 注册分解插件
- **DualDecompositionRegistry** (`dual_decomposition_registry.py`): Dual strategy registry / 双策略注册表

### Models / 模型

- **TaskDefinition** (`models.py`): Task definition model / 任务定义模型
- **TaskResult** (`models.py`): Task result model / 任务结果模型
- **TaskDecomposition** (`models.py`): Decomposition result / 分解结果

## Usage Example / 使用示例

```python
from zentex.tasks import TaskService, TaskDefinition

# Use only the public interface / 仅使用公共接口
service = TaskService()
task = TaskDefinition(name="Analyze data", description="...")
result = await service.execute(task)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.tasks` only, never from `zentex.tasks.service` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.tasks` 导入，绝不能从 `zentex.tasks.service` 或其他内部路径导入。
