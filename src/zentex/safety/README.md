# Safety Module / 安全模块

## Overview / 概述

This module implements safety mechanisms and conflict resolution for the Zentex system. It provides conflict detection, resolution engines, and safety guardrails to ensure safe operation of cognitive processes.

本模块为Zentex系统实现安全机制和冲突解决。它提供冲突检测、解决引擎和安全护栏，以确保认知过程的安全运行。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.safety import (
    ConflictEngine,           # Conflict resolution engine / 冲突解决引擎
    ConflictDetectionResult,  # Detection result model / 检测结果模型
    ConflictResolution,       # Resolution model / 解决方案模型
    SafetyGuard,              # Safety guard interface / 安全护栏接口
)
```

## Core Components / 核心组件

- **ConflictEngine** (`conflict_engine.py`): Detects and resolves conflicts / 检测和解决冲突
- **SafetyGuard** (`__init__.py`): Defines safety boundaries / 定义安全边界

## Features / 功能特性

- Conflict detection / 冲突检测
- Automatic resolution / 自动解决
- Safety validation / 安全验证
- Risk assessment / 风险评估

## Usage Example / 使用示例

```python
from zentex.safety import ConflictEngine

# Use only the public interface / 仅使用公共接口
engine = ConflictEngine()
result = engine.detect_conflicts(data)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.safety` only, never from `zentex.safety.conflict_engine` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.safety` 导入，绝不能从 `zentex.safety.conflict_engine` 或其他内部路径导入。
