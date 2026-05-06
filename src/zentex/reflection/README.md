# Reflection Module / 反思模块

## Overview / 概述

`zentex.reflection` 负责系统的反思、异步反思调度、反思质量评估，以及由反思触发的 prompt 升级建议。

当前模块已经不只是“生成反思文本”，还承担：

- 异步任务化反思执行
- 反思任务监控与重试
- 9 问有效性反思
- prompt 升级合同注册与发现
- 与统一任务管理的桥接

关键文件：

- [service.py](src/zentex/reflection/service.py)
- [async_service.py](src/zentex/reflection/async_service.py)
- [llm_generator.py](src/zentex/reflection/llm_generator.py)
- [prompt_upgrade_registry.py](src/zentex/reflection/prompt_upgrade_registry.py)
- [nine_question_effectiveness.py](src/zentex/reflection/nine_question_effectiveness.py)

## Current Runtime Structure / 当前运行结构

### 1. Synchronous Reflection / 同步反思

同步反思由：

- `ReflectionService`
- `ReflectionInterface`
- `ReflectionManager`

这一层负责：

- 反思对象构建
- 持久化
- 查询与治理

### 2. Async Reflection / 异步反思

[async_service.py](src/zentex/reflection/async_service.py) 是当前异步执行主入口。

它负责：

- 提交反思任务
- worker 执行
- 重试和超时
- monitor / queue 监控
- 状态查询与取消

并且现在已经会自动同步到统一任务管理：

- 提交时同步统一任务
- 运行中同步状态
- 完成/失败/取消时同步状态

桥接点是：

- [tasks/integration/workflow_bridge.py](src/zentex/tasks/integration/workflow_bridge.py)

## LLM Prompt Layer / LLM 提问层

反思模块的 LLM 提问统一在：

- [llm_prompt.py](src/zentex/reflection/llm_prompt.py)

执行编排在：

- [llm_generator.py](src/zentex/reflection/llm_generator.py)

约束如下：

- prompt 内容只能在 `llm_prompt.py` 维护
- `llm_generator.py` 只负责调用、解析、校验
- `service.py` 不直接内联 prompt

## Prompt Upgrade Integration / Prompt 升级接入

这是近期最重要的变化之一。

### 1. Unified Prompt Contract Registry / 统一 prompt 合同注册表

[prompt_upgrade_registry.py](src/zentex/reflection/prompt_upgrade_registry.py) 现在统一发现两类合同：

- 9 问 prompt 合同
- 非 9 问模块 prompt 合同

当前 registry 可统一发现：

- `q1` 到 `q9`
- `tasks.*`
- `upgrade.*`
- `cognition.*`
- `memory.consolidation.*`

### 2. Nine Question Effectiveness / 9 问有效性反思

[nine_question_effectiveness.py](src/zentex/reflection/nine_question_effectiveness.py) 现在不再只依赖 9 问专用入口，而是走统一 registry 取 prompt upgrade contract。

这意味着：

- 反思层不再硬编码每问合同
- 同一套机制后续可以复用到非 9 问模块

## 9 问 Prompt 升级链路 / Nine-Question Prompt Upgrade Flow

当前链路是：

1. 反思发现某一问提示词有效性不足
2. 通过 registry 取到对应 `service.py` 提供的合同
3. 生成 `prompt_optimization` 类型升级请求
4. 下游 upgrade 模块只允许改目标 `llm_prompt.py`
5. 仅允许改 editable sections
6. 必须通过 guardrail 校验，不能偏离原本题意

## Persistence / 持久化

反思模块包含普通持久化与异步任务跟踪两部分。

普通反思数据：

- 由反思持久化层负责

异步任务状态：

- 由 async service 的 monitor / queue 管理
- 同时同步进 `zentex.tasks`

## Integration Contract / 集成边界

其他模块接入 reflection 时应遵守：

- 普通反思走 `ReflectionService` / `ReflectionInterface`
- 后台任务化反思走 `AsyncReflectionService`
- 不直接改内部 monitor / queue
- 不绕过 registry 手工构造 prompt 升级合同

## What Changed Recently / 最近更新

- `reflection` 异步任务已接入统一任务管理
- 状态同步覆盖提交、运行、完成、失败、取消
- 9 问反思触发的 prompt 升级已走统一 registry
- registry 已统一覆盖 9 问与非 9 问模块 prompt 合同

## Limitations / 当前限制

- `reflection` 目前接入统一任务管理的是“任务级状态”，不是把所有内部子过程都拆成独立任务
- prompt 升级触发主要完善在 9 问场景；非 9 问模块虽然已有合同，但还未全部接入自动触发策略
