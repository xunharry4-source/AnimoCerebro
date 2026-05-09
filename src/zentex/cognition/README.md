# Cognition Module / 认知模块

## Overview / 概述

This module implements core cognitive functions including counterfactual simulation and social interaction mind processing. It provides the cognitive reasoning engine for the Zentex system.

本模块实现核心认知功能，包括反事实模拟和社交交互思维处理。它为Zentex系统提供认知推理引擎。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files (`simulation.py`, `social_mind.py`) are implementation details / 内部文件（`simulation.py`、`social_mind.py`）是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.cognition import (
    CounterfactualSimulationEngine,   # Simulation engine / 模拟引擎
    ScenarioBranch,                    # Simulation scenario / 模拟场景分支
    OutcomeComparison,                 # Outcome comparison result / 结果比较
    SimulationBundle,                  # Simulation bundle / 模拟包
    StaleSimulationResultError,        # Stale result error / 过期结果错误
    InteractionMindEngine,             # Social mind engine / 社交思维引擎
    InteractionMindModel,              # Mind model / 思维模型
    InteractionMindState,              # Mind state / 思维状态
    CommunicationFitProfile,           # Communication fit / 通信适配档案
    KnowledgeGapEstimate,              # Knowledge gap estimate / 知识差距估计
    MisunderstandingSignal,            # Misunderstanding signal / 误解信号
    InteractionMindStaleWriteError,    # Stale write error / 过期写入错误
)
```

## Core Components / 核心组件

- **CounterfactualSimulationEngine** (`simulation.py`): Performs counterfactual simulations / 执行反事实模拟
- **InteractionMindEngine** (`social_mind.py`): Manages social interaction cognition / 管理社交交互认知

## Usage Example / 使用示例

```python
from zentex.cognition import CounterfactualSimulationEngine, InteractionMindEngine

# Use only the public interface / 仅使用公共接口
sim_engine = CounterfactualSimulationEngine()
mind_engine = InteractionMindEngine()
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.cognition` only, never from `zentex.cognition.simulation` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.cognition` 导入，绝不能从 `zentex.cognition.simulation` 或其他内部路径导入。
