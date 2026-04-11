# Runtime Module / 运行时模块

## Overview / 概述

This module implements the core runtime engine for the Zentex system. It includes the think loop, session management, working memory, temporal reasoning, metacognition, and transcript recording. This is the central execution engine that orchestrates all cognitive processes.

本模块实现Zentex系统的核心运行时引擎。它包括思维循环、会话管理、工作记忆、时间推理、元认知和转录记录。这是协调所有认知过程的中央执行引擎。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface (import from specific modules) / 所有交互必须通过统一的公共接口（从特定模块导入）进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interfaces / 公共接口

This module exposes interfaces through individual files:

本模块通过各个文件暴露接口：

### Think Loop / 思维循环

```python
from zentex.runtime.think_loop import ThinkLoop, BrainTurnResult
```

### Session Management / 会话管理

```python
from zentex.runtime.session import BrainSession, SessionManager
```

### Working Memory / 工作记忆

```python
from zentex.runtime.working_memory import WorkingMemory, WorkingMemoryItem
```

### Metacognition / 元认知

```python
from zentex.runtime.metacognition import MetacognitiveMonitor, MetacognitiveState
```

### Temporal Reasoning / 时间推理

```python
from zentex.runtime.temporal import TemporalReasoner, TemporalContext
```

### Self Model / 自我模型

```python
from zentex.runtime.self_model import SelfModel, SelfModelState
```

### Transcript / 转录记录

```python
from zentex.runtime.transcript import BrainTranscriptStore, TranscriptEntry
```

### Cognitive Tools / 认知工具

```python
from zentex.runtime.cognitive_tools import CognitiveToolRegistry, ToolExecutionResult
```

### Nine Questions / 九问

```python
from zentex.runtime.nine_questions import NineQuestionsEngine, QuestionSet
```

## Core Components / 核心组件

- **ThinkLoop** (`think_loop.py`): Main cognitive processing loop / 主认知处理循环
- **BrainSession** (`session.py`): Manages brain sessions / 管理大脑会话
- **WorkingMemory** (`working_memory.py`): Working memory implementation / 工作记忆实现
- **MetacognitiveMonitor** (`metacognition.py`): Monitors cognitive processes / 监控认知过程
- **BrainTranscriptStore** (`transcript.py`): Stores execution transcripts / 存储执行转录

## Usage Example / 使用示例

```python
from zentex.runtime.think_loop import ThinkLoop
from zentex.runtime.session import BrainSession

# Use only the public interfaces / 仅使用公共接口
loop = ThinkLoop()
session = BrainSession(loop)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules should import from specific runtime submodules. The runtime is the central orchestration layer.

⚠️ **重要提示**：其他模块应从特定的运行时子模块导入。运行时是中央编排层。
