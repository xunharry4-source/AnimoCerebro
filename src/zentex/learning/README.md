# Learning Module / 学习模块

## Overview / 概述

This module implements the learning engine and adaptive capabilities of the Zentex system. It includes DSPy integration, G16 pipeline processing, sandboxed learning environments, and budget management.

本模块实现Zentex系统的学习引擎和自适应能力。它包括DSPy集成、G16管道处理、沙盒学习环境和预算管理。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface (import from specific modules) / 所有交互必须通过统一的公共接口（从特定模块导入）进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interfaces / 公共接口

This module exposes interfaces through individual files:

本模块通过各个文件暴露接口：

### Learning Engine / 学习引擎

```python
from zentex.learning.engine import LearningEngine, LearningResult
```

### G16 Pipeline / G16管道

```python
from zentex.learning.g16_pipeline import G16Pipeline, G16LearningResult
from zentex.learning.g16_models import G16Input, G16Output
from zentex.learning.g16_dspy_signatures import G16Signature
```

### DSPy Adapter / DSPy适配器

```python
from zentex.learning.dspy_adapter import DspyAdapter
```

### Sandbox / 沙盒

```python
from zentex.learning.sandbox import LearningSandbox, SandboxResult
```

### Budget Management / 预算管理

```python
from zentex.learning.budget import LearningBudget, BudgetTracker
```

### Learning Directions / 学习方向

```python
from zentex.learning.directions import LearningDirection, DirectionManager
```

## Core Components / 核心组件

- **LearningEngine** (`engine.py`): Main learning engine / 主学习引擎
- **G16Pipeline** (`g16_pipeline.py`): G16 learning pipeline / G16学习管道
- **DspyAdapter** (`dspy_adapter.py`): DSPy framework adapter / DSPy框架适配器
- **LearningSandbox** (`sandbox.py`): Sandboxed learning environment / 沙盒学习环境

## Usage Example / 使用示例

```python
from zentex.learning.engine import LearningEngine
from zentex.learning.g16_pipeline import G16Pipeline

# Use only the public interfaces / 仅使用公共接口
engine = LearningEngine()
pipeline = G16Pipeline()
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules should import from specific learning submodules, not directly from file paths when possible.

⚠️ **重要提示**：其他模块应从特定的学习子模块导入，尽可能不直接从文件路径导入。
