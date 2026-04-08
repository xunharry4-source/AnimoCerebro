# Reflection Module / 反思模块

## Overview / 概述

This module implements metacognitive reflection capabilities for the Zentex system. It provides interfaces, models, persistence, and service layers for self-reflection, error analysis, and cognitive improvement.

本模块为Zentex系统实现元认知反思能力。它为自我反思、错误分析和认知改进提供接口、模型、持久化和服务层。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.reflection import (
    # Core interface / 核心接口
    ReflectionInterface,
    
    # Models / 模型
    ReflectionRequest,
    ReflectionResponse,
    ReflectionError,
    ReflectionType,
    
    # Service / 服务
    ReflectionService,
    
    # Persistence / 持久化
    ReflectionPersistence,
    
    # Errors / 错误
    ReflectionError,
    ReflectionValidationError,
)
```

## Core Components / 核心组件

### Interface Layer / 接口层

- **ReflectionInterface** (`interface.py`): Main reflection interface definition / 主反思接口定义

### Service Layer / 服务层

- **ReflectionService** (`service.py`): Implements reflection service logic / 实现反思服务逻辑

### Models / 模型

- **ReflectionRequest** (`models.py`): Reflection request model / 反思请求模型
- **ReflectionResponse** (`models.py`): Reflection response model / 反思响应模型
- **ReflectionType** (`models.py`): Types of reflection / 反思类型枚举

### Persistence / 持久化

- **ReflectionPersistence** (`persistence.py`): Handles reflection data persistence / 处理反思数据持久化

## Usage Example / 使用示例

```python
from zentex.reflection import ReflectionService, ReflectionInterface

# Use only the public interface / 仅使用公共接口
service = ReflectionService()
result = await service.reflect(query="What went wrong?")
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.reflection` only, never from `zentex.reflection.interface` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.reflection` 导入，绝不能从 `zentex.reflection.interface` 或其他内部路径导入。
