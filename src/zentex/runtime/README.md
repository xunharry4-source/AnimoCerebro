# Zentex Runtime

This directory contains the brain's central processing engine, responsible for the physical execution of cognition.
- **`ThinkLoop`**: The core execution engine implementing the 9-stage cognitive model.
- **`BrainRuntime`**: Top-level container managing stores and controllers.
- **`BrainSession`**: Memory-state container capable of state recovery via transcript replay.
- **`WorkingMemory`**: Attention and focus slot management.
- **`Metacognition`**: Deterministic rule engine for reasoning mode decision.

---

# Zentex 运行时目录

该目录包含大脑的中枢处理引擎，负责认知的物理执行。
- **`ThinkLoop`**: 核心执行引擎，实现标准的九阶段认知模型。
- **`BrainRuntime`**: 顶层容器，管理共享存储（Stores）与调度器（Controllers）。
- **`BrainSession`**: 状态容器，通过回放 Transcript 录像带恢复内存状态。
- **`WorkingMemory`**: 注意力管理与槽位分配。
- **`Metacognition`**: 元认知控制器，决定思考模式（如 Fast/Deep）。
