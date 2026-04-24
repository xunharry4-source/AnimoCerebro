# Kernel 模块 — 认知执行内核

## 概述

`kernel` 模块是新架构的**认知执行内核**，替代旧的 `__runtime` 模块。

它是系统业务逻辑的中心执行器，负责管理会话、编排认知流程、协调外部模块能力、维护运行态状态和审计链。

## 核心职责

#### ✅ 会话管理
- Session 创建与生命周期
- Session 状态持久化
- Session 快照与恢复
- 多租户与多用户隔离

#### ✅ Turn 执行编排
- Turn 协议执行
- 九阶段流程控制
- 状态转移与校验
- 异常处理与回滚

#### ✅ 九问认知编排
- Q1-Q9 按序执行
- 冷启动协调
- 状态维护与转录
- 结果收集与聚合

#### ✅ 工作记忆管理
- Working Memory 增删改查
- 记忆生命周期
- 访问控制与隐私

#### ✅ 状态与审计
- 运行态状态持久化
- 完整审计链记录
- Trace ID 传播
- 上下文还原

#### ✅ 外部模块编排
- 通过 `service.py` 调用外部能力
- 隔离外部依赖细节
- 统一错误处理与重试

## 严格禁止

| 类别 | 禁止事项 |
|---|---|
| **依赖关系** | ❌ 直接导入外部模块内部实现（如 `cognition.xxxxx`） |
| **依赖关系** | ❌ 直接引用 `zentex.__runtime` 或旧 `__core` |
| **实现方式** | ❌ 直接实例化外部模块具体类 |
| **实现方式** | ❌ 在 `ThinkLoop` 中绕过 `plugins.service` 直接调插件 |
| **实现方式** | ❌ 在 `service.py` 内部转调旧 `__runtime` |
| **跨模块通信** | ❌ 绕过 `foundation.service` 获取协议 |
| **跨模块通信** | ❌ 跨模块直接导入，仅允许 `service.py` |
| **兼容性** | ❌ 保留旧 `__runtime` 模块作为运行时依赖 |

## 目录结构

```
kernel/
├── session_domain/              # 会话管理域
│   ├── session.py               # Session 模型
│   ├── session_lifecycle.py     # 生命周期管理
│   ├── session_store.py         # 持久化接口
│   └── ...
├── state_domain/                # 状态管理域
│   ├── working_memory.py        # 工作记忆
│   ├── transcript.py            # 执行转录
│   ├── audit_log.py             # 审计日志
│   ├── state_snapshot.py        # 状态快照
│   └── ...
├── flow_domain/                 # 流程执行域
│   ├── think_loop.py            # 九阶段执行器
│   ├── phase_executor.py        # 各阶段具体实现
│   ├── turn_manager.py          # Turn 管理
│   ├── turn_result.py           # Turn 结果模型
│   └── ...
├── cognition_flow/              # 认知编排域
│   ├── router.py                # 请求路由
│   ├── startup_coordinator.py   # 冷启动协调
│   ├── nine_question_executor.py# 九问执行
│   ├── models.py                # 域模型
│   └── ...
├── service.py                   # ⭐ 唯一公开入口
└── __init__.py
```

## 使用规范

### ✅ 允许的调用方式

来自 `launcher` 或 `foundation`：

```python
from zentex.kernel import service as kernel_svc
from zentex.foundation.service import get_session_protocol

# 创建 session
session = kernel_svc.create_session(user_id="user123")

# 执行 turn
turn_result = kernel_svc.execute_turn(
    session_id=session.id,
    user_input="...",
    trace_id="trace-xyz"
)

# 访问状态
state = kernel_svc.get_session_state(session_id=session.id)
```

### ❌ 禁止的调用方式

```python
# ❌ 直接 import 内部模块
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.kernel.session_domain.session import Session

# ❌ 调用外部模块内部实现
from zentex.cognition.xxx import CognitionEngine
from zentex.__runtime.xxxx import BrainRuntime

# ❌ 在 kernel 内部直接实例化外部对象
engine = CognitionEngine()  # ❌ 应通过 cognition.service
```

### Service 入口规范

所有对 `kernel` 的调用**必须**通过 `kernel.service.py`：

```python
from zentex.kernel import service as kernel_svc

# 会话管理
session = kernel_svc.create_session(...)
kernel_svc.close_session(session_id)
state = kernel_svc.get_session_state(session_id)

# Turn 执行
result = kernel_svc.execute_turn(session_id, user_input, trace_id)

# 九问编排
kernel_svc.ensure_nine_questions_bootstrap(session_id)
kernel_svc.answer_nine_question(session_id, question_id)

# 状态访问
memory = kernel_svc.get_working_memory(session_id)
transcript = kernel_svc.get_transcript(session_id)
audit = kernel_svc.get_audit_log(session_id)
```

## 架构约束

### 分层依赖图

```
┌──────────────────────────────────┐
│  launcher                        │
└─────────┬──────────────────┬─────┘
          │                  │
          ↓                  ↓
    kernel.service    foundation.service
          ↓                  ↑
    ┌─────────────────────────┘
    │
    ├─→ environment.service
    ├─→ cognition.service
    ├─→ plugins.service (特殊：认知插件调用链)
    ├─→ memory.service
    └─→ safety.service
```

### 外部模块调用边界

`kernel` 和外部模块的交互**必须**通过 `service.py`：

| 外部模块 | 调用方式 | 权限 |
|---|---|---|
| `environment` | `environment.service.get_workspace_state()` | ✅ 允许 |
| `cognition` | `cognition.service.infer(...)` | ✅ 允许 |
| `memory` | `memory.service.recall(...)` | ✅ 允许 |
| `safety` | `safety.service.check_conflict(...)` | ✅ 允许 |
| `plugins` | `plugins.service.execute_cognitive_plugin(...)` | ✅ 允许（认知插件） |
| 内部实现 | `from zentex.cognition.xxx import YYY` | ❌ 禁止 |

### 插件调用规范（特殊约束）

```
kernel
    ├─→ execute_cognitive_plugin(Q1-Q9)
    │       ├─→ Q1 执行
    │       ├─→ Q1 可调用绑定的功能插件
    │       ├─→ 功能插件结果汇入 Q1
    │       └─→ Q1 结果返回至 kernel
    │
    └─→ execute_cognitive_plugin(Memory Extractor)
            ├─→ 执行记忆提取
            └─→ 返回提取结果

关键规则：
- kernel 只能直接执行认知插件（Q1-Q9 + 其他认知）
- 功能插件只能被认知插件通过 plugins.service 调用
- 功能插件结果不能绕过认知插件直接落入 kernel 状态
```

## CI 检查与门禁

本模块受以下自动化检查约束（P0 级违规直接阻断合并）：

| 检查项 | 规则 | 等级 |
|---|---|---|
| 禁止旧模块 | ❌ import `__runtime` 或 `__core` | P0 |
| 禁止内部导入 | ❌ 跨模块直接导入，仅允许 `service.py` | P0 |
| 禁止直接实例化 | ❌ 直接 new 外部模块引擎（如 `CognitionEngine()`） | P0 |
| 禁止越权调用 | ❌ 直接调功能插件或绕过 `plugins.service` | P0 |
| 禁止反向依赖 | ❌ 在 `foundation` 中出现 `kernel` 引用 | P0 |
| 禁止兼容层 | ❌ 存在 `compat_*`、`legacy_*`、`bridge_*` 等包装 | P0 |

## 运行流程

### 典型 Turn 执行链

```
1. launcher.service.start_turn(session_id, input, trace_id)
   ↓
2. kernel.service.execute_turn(...)
   ↓
3. kernel.think_loop.execute_nine_phases(...)
   ├─→ Phase 1: Observe
   │   └─→ environment.service.get_state()
   │
   ├─→ Phase 2-10: Reasoning & Decision
   │   ├─→ cognition.service.infer(...)
   │   ├─→ memory.service.recall(...)
   │   ├─→ safety.service.check_conflict(...)
   │   └─→ plugins.service.execute_cognitive_plugin(Q1-Q9)
   │
   └─→ Phase 11: Consolidate
       └─→ memory.service.store(...)
   ↓
4. kernel.service.commit_turn_result(...)
   ↓
5. Return TurnResult with trace_id
```

## 迁移策略

本模块是新架构的第二阶段实施：

1. **依赖隔离** — 从直接导入改成统一 `service.py` 调用
2. **流程重构** — 不复用旧 `__runtime` 实现，基于新协议重写
3. **边界清晰** — 禁止 `ThinkLoop` 跨模块直接导入
4. **冷启动收口** — 九问冷启动统一收口到 `kernel.cognition_flow.startup_coordinator`

## 相关文档

- 📖 [核心重构计划](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 7.2 节（`kernel` 结构）
- 📖 [服务契约规范](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 17 章（API 设计规范）
- 📖 [治理与门禁](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 16 章（CI 检查规则）
- 📖 [插件调用规范](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 17.2.6 节

## 常见问题

**Q: kernel 能直接访问外部模块的具体类吗？**  
A: 不能。必须通过 `xxxx.service` 访问。如果需要特定功能，应先在外部模块 `service.py` 中添加相应 API。

**Q: 功能插件可以直接被 kernel 调用吗？**  
A: 不可以。只有认知插件（Q1-Q9 等）可以被 kernel 直接调用。功能插件只能被认知插件通过 `plugins.service` 调用。

**Q: kernel 内部能直接持有外部模块的引擎对象吗？**  
A: 不能。所有外部能力都应通过 `service.py` 动态调用，kernel 不应持有外部对象的引用。

