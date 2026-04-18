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
- **G16Pipeline** (`g16_pipeline.py`): G16 learning pipeline — delegates ALL input preprocessing to `llm_prompt.py` / G16学习管道 — 所有输入预处理委托给 `llm_prompt.py`
- **DspyAdapter** (`dspy_adapter.py`): DSPy framework adapter / DSPy框架适配器
- **LearningSandbox** (`sandbox.py`): Sandboxed learning environment / 沙盒学习环境
- **llm_prompt.py**: **唯一负责组装 LLM / DSPy 输入和内容预处理的文件。**
  - `build_g16_distillation_inputs()` — 预处理 `doc_url` + `feedback_history`，输出直接传入 `ToolDistillationModule`。
  - `build_g16_critic_inputs()` — 预处理 critic 的四个输入字段，截断过长 schema / test_cases。
  - `summarise_feedback_for_next_attempt()` — 将多轮沙箱反馈合并为精简的历史记录，防止 feedback 无限累积膨胀。
  - 所有字符截断规则（doc_url 上限 2048、feedback 保留最近 5 条、schema 上限 2000）集中在此文件维护。

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

## LLM Prompt 分离约定 / LLM Prompt Separation Contract

本模块采用"提问与执行分离"原则：

| 文件 | 职责 | 禁止事项 |
|------|------|---------|
| `llm_prompt.py` | 预处理 doc_url / feedback / schema / test_cases，生成 DSPy 输入 dict | 禁止调用 LLM 或 DSPy |
| `g16_pipeline.py` | 编排 Voyager 循环、调用 DSPy module、写 transcript | 禁止内联字符串截断或 prompt 拼接 |
| `engine.py` | 学习方向路由、预算检查 | 禁止直接构建 LLM 输入 |

**任何需要修改发给 LLM/DSPy 的输入内容、截断上限、feedback 保留策略，只改 `llm_prompt.py`，不改其他文件。**
