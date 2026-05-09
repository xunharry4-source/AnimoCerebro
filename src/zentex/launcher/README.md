# Launcher 模块 — 系统装配启动中心

## 概述

`launcher` 模块是新架构的**系统装配启动中心**，替代旧的 `__boot` 模块。

它只负责系统初始化、依赖装配、配置解析和应用启动，不承担任何业务逻辑或长期状态管理。

## 核心职责

#### ✅ 配置管理
- 启动配置解析
- 环境变量读取
- 配置验证与校验
- 配置版本管理

#### ✅ 依赖装配
- 构建 service 依赖图
- 注册 service 实例
- 处理依赖顺序
- 依赖冲突检测

#### ✅ 应用入口
- Web 开发态启动
- API 服务启动
- CLI 工具启动
- 后台任务启动

#### ✅ 版本管理
- 系统版本号
- 兼容性检查
- 升级流程支持

#### ✅ 启动业务
- 可选的数据初始化
- 可选的预热逻辑
- 健康检查
- 启动报告生成

## 严格禁止

| 类别 | 禁止事项 |
|---|---|
| **依赖关系** | ❌ 直接 new `kernel` 内部对象 |
| **依赖关系** | ❌ 直接引用 `zentex.__boot / __runtime / __core` |
| **实现方式** | ❌ 直接调用 `BrainRuntime` 等旧运行时对象 |
| **实现方式** | ❌ 在启动阶段执行插件模块内部工作流（如 auto-bootstrap） |
| **业务逻辑** | ❌ 承担任何九问业务逻辑 |
| **业务逻辑** | ❌ 承担任何 registry 业务规则 |
| **业务逻辑** | ❌ 维护开发态 demo 业务数据逻辑 |
| **跨模块通信** | ❌ 跨模块直接导入，仅允许 `service.py` |
| **插件管理** | ❌ 接管插件模块内部生命周期 |
| **兼容性** | ❌ 继续依赖旧 `__boot` 作为运行时包装 |

## 目录结构

```
launcher/
├── config/                      # 配置管理
│   ├── config_loader.py         # 配置加载
│   ├── config_schema.py         # 配置模式定义
│   ├── environment_parser.py    # 环境变量解析
│   ├── path_resolver.py         # 路径解析
│   └── ...
├── assembly/                    # 依赖装配
│   ├── service_registry.py      # Service 注册表
│   ├── dependency_graph.py      # 依赖图构建
│   ├── initialization_order.py  # 初始化顺序管理
│   └── ...
├── entrypoints/                 # 启动入口
│   ├── web_dev.py               # Web 开发态入口
│   ├── api_server.py            # API 服务入口
│   ├── cli_main.py              # CLI 工具入口
│   ├── background_daemon.py     # 后台守护入口
│   └── ...
├── service.py                   # ⭐ 唯一公开入口
└── __init__.py
```

## 使用规范

### ✅ 允许的调用方式

来自外部应用代码：

```python
from zentex.launcher import service as launcher_svc

# 启动 Web 应用
app = launcher_svc.start_web_dev(
    config_path="config/dev.yml",
    debug=True
)

# 启动 API 服务
api = launcher_svc.start_api_server(
    config="config/prod.yml",
    port=8000
)

# 获取系统入口
system = launcher_svc.get_system_instance()
```

### ❌ 禁止的调用方式

```python
# ❌ 直接 import 内部模块
from zentex.launcher.assembly.service_registry import ServiceRegistry
from zentex.launcher.config.config_loader import ConfigLoader

# ❌ 调用外部模块内部实现
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.__boot._bootstrap_runtime import _bootstrap_runtime

# ❌ 在 launcher 中承担业务逻辑
from zentex.kernel.cognition_flow.nine_question_executor import Q1Executor
q1 = Q1Executor()  # ❌ 业务逻辑不属于 launcher
```

### Service 入口规范

所有对 `launcher` 的调用**必须**通过 `launcher.service.py`：

```python
from zentex.launcher import service as launcher_svc

# 启动系统
app = launcher_svc.start_web(
    config_path="./config/zentex.yml",
    env="development"
)

# 获取已初始化的 service
kernel_svc = launcher_svc.get_kernel_service()
memory_svc = launcher_svc.get_memory_service()

# 系统信息
status = launcher_svc.get_system_status()
version = launcher_svc.get_version()
```

## 架构约束

### 分层依赖图

```
┌─────────────────────────────────┐
│  External Applications          │  (Web、CLI、Daemon)
└─────────────┬─────────────────┬─┘
              │                 │
              ↓                 ↓
        launcher.service    launcher.entrypoints
              ↓
        ┌─────┴────────────────┐
        ↓                      ↓
  kernel.service        foundation.service
  memory.service        plugins.service
  cognition.service     other services
```

### 启动链路规则

```
launcher.service.start_web()
  1. 加载配置
  2. 创建 service 依赖图
  3. 初始化所有 service（通过 service API，不接管内部）
  4. 验证系统就绪
  5. 启动应用入口
  6. 返回运行中的系统
```

**关键约束**：
- 第 3 步中，`launcher` 只能初始化 `plugins.service` 的依赖入口
- `launcher` 不能调用 `plugins` 模块内部的 bootstrap、registry、binding 等方法
- 所有其他模块的初始化由它们自己的 `service.py` 负责

## CI 检查与门禁

本模块受以下自动化检查约束（P0 级违规直接阻断合并）：

| 检查项 | 规则 | 等级 |
|---|---|---|
| 禁止旧模块 | ❌ import `__boot / __runtime / __core` | P0 |
| 禁止越权 | ❌ 直接 new `kernel` 内部对象 | P0 |
| 禁止越权 | ❌ 直接调用插件模块内部工作流 | P0 |
| 禁止越权 | ❌ 承担业务逻辑（九问、registry、业务规则） | P0 |
| 禁止内部导入 | ❌ 跨模块直接导入，仅允许 `service.py` | P0 |
| 禁止兼容层 | ❌ 存在 `compat_*`、`legacy_*` 等包装 | P0 |
| 禁止版本混乱 | ❌ 同时并存多条启动链路 | P1 |

## 启动流程示例

### 标准 Web 开发环境启动

```python
# 文件: src/zentex/launcher/entrypoints/web_dev.py

from zentex.launcher import service as launcher_svc

if __name__ == "__main__":
    # launcher.service 负责一切装配
    app = launcher_svc.start_web_dev(
        config_path="config/dev.yml",
        debug=True,
        trace_id="startup_xyz"
    )
    
    # 启动应用
    app.run(host="127.0.0.1", port=5000)
```

### launcher.service 内部逻辑

```python
# 文件: src/zentex/launcher/service.py

def start_web_dev(config_path: str, debug: bool, trace_id: str):
    """
    启动 Web 开发环境
    
    1. 加载配置
    2. 初始化所有 service
    3. 验证系统就绪
    4. 创建应用入口
    5. 返回应用
    """
    
    # Step 1: 配置加载
    config = _load_config(config_path)
    
    # Step 2: 依赖装配 (不接管内部生命周期)
    services = {
        "foundation": foundation.service,  # 已初始化
        "kernel": kernel.service,          # 已初始化
        "memory": memory.service,          # 已初始化
        "cognition": cognition.service,    # 已初始化
        "plugins": plugins.service,        # 仅装配入口，不执行内部工作
        "safety": safety.service,          # 已初始化
        "environment": environment.service,# 已初始化
    }
    
    # Step 3: 系统验证
    _verify_system_ready(services, trace_id)
    
    # Step 4: 创建应用
    app = _create_web_app(config, services)
    
    return app
```

## 迁移策略

本模块是新架构的第三阶段实施：

1. **启动链冻结** — 只有一条启动链路 (`launcher.service`)
2. **配置集中** — 所有启动配置由 `launcher` 统一管理
3. **依赖透明** — 依赖装配过程清晰可追踪
4. **业务隔离** — `launcher` 绝不承担业务规则
5. **版本清晰** — 启动后即进入 `kernel` 业务执行阶段

## 相关文档

- 📖 [核心重构计划](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 7.3 节（`launcher` 结构）
- 📖 [启动流程](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 8.1 节（目标启动流程）
- 📖 [治理与门禁](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 16 章（CI 检查规则）
- 📖 [插件 service 规范](../../docs/CORE_RUNTIME_BOOT_REFACTOR_PLAN_ZH.md) — 第 17.2.5 节

## 常见问题

**Q: launcher 能承担九问初始化吗？**  
A: 不能。冷启动九问是 `kernel` 的业务逻辑，不属于系统启动。`launcher` 只负责让 `kernel` 等 service 就位。

**Q: launcher 能直接管理插件的生命周期吗？**  
A: 不能。`launcher` 只能装配 `plugins.service` 的依赖入口。插件的注册、绑定、启用等内部工作由 `plugins` 模块自己负责。

**Q: 多个启动入口（Web、API、CLI）如何处理？**  
A: 所有入口都应调用 `launcher.service.start_xxx()` 方法，统一依赖装配过程，确保只有一条链路。

**Q: 启动阶段遇到错误如何回滚？**  
A: `launcher.service` 应提供明确的错误处理和回滚逻辑。如果某个 service 初始化失败，应清理已装配的资源后回滚。

