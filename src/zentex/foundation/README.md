# Foundation 模块 — 基础协议中心

## 概述

`foundation` 模块是新架构的**基础协议中心**，替代旧的 `__core` 模块。

它不负责执行，不负责启动，不负责业务推理；它只负责定义系统共识、稳定协议、跨模块公共数据模型和基础契约。

## 核心职责

#### ✅ 定义基础数据模型
- 服务响应统一结构 (`ServiceResponse`)
- 跨模块通信合约
- 插件契约与规范
- Session、Turn、审计模型

#### ✅ 定义系统协议
- 插件执行规范
- 感知规范
- 模拟规范
- Turn 协议

#### ✅ 定义身份契约
- 身份存储接口
- 身份服务边界
- 权限模型

#### ✅ 暴露元信息
- 版本管理
- 能力注册表
- Feature Family 定义
- 系统常量

#### ✅ 统一 Service 入口
- `foundation.service` 作为唯一公开接口
- 暴露查询接口而非实现细节

## 严格禁止

| 类别 | 禁止事项 |
|---|---|
| **依赖关系** | ❌ 依赖 `kernel` 或 `launcher` 模块 |
| **依赖关系** | ❌ 直接引用 `zentex.__core / __runtime / __boot` |
| **内容类型** | ❌ 包含任何执行逻辑 |
| **内容类型** | ❌ 包含任何启动逻辑 |
| **内容类型** | ❌ 出现运行时对象（`BrainTranscriptStore`、`CognitiveToolResult` 等） |
| **反向依赖** | ❌ 出现 `kernel` 类型的反向依赖 |
| **兼容性** | ❌ 通过兼容层包装旧 `__*` 模块 |

## 目录结构

```
foundation/
├── contracts/                    # 基础数据模型与 DTO
│   ├── service_response.py      # 统一服务响应结构
│   ├── plugin_contract.py       # 插件基础契约
│   ├── session_contract.py      # 会话协议
│   ├── turn_protocol.py         # Turn 执行协议
│   ├── audit_trail.py           # 审计模型
│   └── ...
├── specs/                       # 系统协议与规范
│   ├── plugin_spec.py           # 插件规范
│   ├── execution_spec.py        # 执行规范
│   ├── perception_spec.py       # 感知规范
│   ├── simulation_spec.py       # 模拟规范
│   └── ...
├── identity/                    # 身份模块契约
│   ├── identity_service.py      # 身份服务接口
│   ├── permission_model.py      # 权限模型
│   └── ...
├── meta/                        # 版本与元信息
│   ├── version.py               # 版本管理
│   ├── capability_registry.py   # 能力注册表
│   ├── feature_family.py        # Feature Family 定义
│   ├── constants.py             # 系统常量
│   └── ...
├── service.py                   # ⭐ 唯一公开入口
└── __init__.py
```

## 使用规范

### ✅ 允许的导入方式

```python
# 来自其他模块的导入
from zentex.foundation.service import (
    get_plugin_spec,
    get_session_protocol,
    get_turn_protocol,
    list_capabilities,
)

# 使用数据模型
from zentex.foundation.contracts import (
    ServiceResponse,
    PluginContract,
    SessionProtocol,
    TurnProtocol,
)
```

### ❌ 禁止的导入方式

```python
# ❌ 不允许直接 import 内部实现
from zentex.foundation.specs.plugin_spec import PluginSpecImpl
from zentex.foundation.contracts.service_response import _internal_helper
from zentex.foundation.meta.capability_registry import CapsRegistry
```

### Service 入口规范

所有对 `foundation` 的调用**必须**通过 `foundation.service.py`：

```python
from zentex.foundation import service as foundation_svc

# 查询协议
spec = foundation_svc.get_plugin_spec()
protocol = foundation_svc.get_session_protocol()

# 查询能力
caps = foundation_svc.list_capabilities()
version = foundation_svc.get_version()

# 获取身份服务接口
identity_service = foundation_svc.get_identity_service()
```

## 架构约束

### 分层依赖图

```
┌─────────────────────────────┐
│  foundation  (最底层)       │  ← 无依赖、最稳定
└─────────────┬───────────────┘
              │
              ├─→ kernel.service
              │
              └─→ launcher.service

依赖方向：单向向下，禁止反向依赖
```

### Service-Only 原则

- 新模块间**只能**通过 `service.py` 交互
- 禁止跨模块直接导入内部实现文件
- 所有公开 API 都应在 `service.py` 显式声明
- 禁止通过 `TYPE_CHECKING` 逐渐演化成真实依赖

## CI 检查与门禁

本模块受以下自动化检查约束（P0 级违规直接阻断合并）：

| 检查项 | 规则 | 等级 |
|---|---|---|
| 禁止旧模块依赖 | ❌ import `__core / __runtime / __boot` | P0 |
| 禁止向下依赖 | ❌ 出现 `kernel` 或 `launcher` 直接引用 | P0 |
| Service 隔离 | ❌ 跨模块非法导入（仅允许 `service.py`） | P0 |
| 反向依赖 | ❌ 出现指向 `kernel` 的 import | P0 |
| 兼容层 | ❌ 存在 `compat_*`、`legacy_*`、`bridge_*` 等包装 | P0 |

## 迁移策略

本模块是新架构的第一阶段实施：

1. **知识抽取** — 从旧 `__core` 抽取**协议知识**（不是复用旧实现）
2. **全新建设** — 建立全新的 DTO、规范、契约
3. **彻底隔离** — 禁止新 `foundation` import 任何 `__*` 模块
4. **独立验证** — 确保 `foundation` 可以独立存在和测试

## 相关文档

- 📖 [核心重构计划](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 7.1 节（`foundation` 结构）
- 📖 [服务契约规范](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 17 章（API 设计规范）
- 📖 [治理与门禁](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 16 章（CI 检查规则）

## 常见问题

**Q: 为什么不直接用旧 `__core` 的实现？**  
A: 旧 `__core` 已有反向依赖（依赖 `__runtime`），无法作为纯基础层。新 `foundation` 必须从零开始，基于纯协议设计。

**Q: `foundation` 可以包含引擎或 manager 吗？**  
A: 不可以。`foundation` 只能包含数据模型、规范定义、常量。所有引擎逻辑都应在 `kernel` 中。

**Q: 跨模块调用时如何使用 `foundation`？**  
A: 始终通过 `foundation.service` 访问，如 `foundation_svc.get_plugin_spec()`。

