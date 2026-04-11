# Plugins Module / 插件模块

## 🚫 重要架构约束

**所有插件的访问和执行都必须通过 `SystemPluginService` 进行。**

直接从 `plugins.*` 导入插件工厂函数是**严格禁止**的。

```python
# ❌ 禁止（违反架构）
from plugins.nine_questions.q1_where_am_i import build_q1_where_am_i_plugin
plugin = build_q1_where_am_i_plugin()

# ✅ 正确方式
from zentex.plugins.service import SystemPluginService
service = SystemPluginService(db_path="plugins.db")
service.bootstrap()
plugins = service.query_plugins(plugin_id="q1_where_am_i", status="active")
result = await service.execute_plugin_once(plugin_id, task_id, parameters, trace_id, originator_id)
```

---

## Overview / 概述

This module provides the central governance and lifecycle management for all internal plugins in Zentex.

该模块为 Zentex 系统内的所有原生插件提供统一的注册、查询、执行和生命周期管理。

**Core Responsibility**: Register → Query → Execute → Return Results

**核心职责**：注册 → 查询 → 执行 → 返回结果

---

## Architecture Overview / 架构概览

```
┌─────────────────────────────────────────────────────┐
│           src/zentex/plugins/service.py             │
│      (Plugin Governance & Lifecycle Service)        │
└────────────┬────────────────────────────────────────┘
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
  REGISTER QUERY    EXECUTE
    │        │        │
    └────────┼────────┘
             │
         ┌───▼────┐
         │  DB    │
         │ Persist│
         └────────┘
         
Registry used:
  - In-Memory Dict: _plugin_instances (actual plugin objects)
  - Database: system_plugins table (metadata persistence)
```

---

## Plugin Registration / 插件注册

### Registration Methods / 注册方式

#### 1. **Automatic Registration (Auto-Boot)** / 自动注册（开机自动扫描）

系统启动时，`SystemPluginService.bootstrap()` 会：
1. 扫描 `src/plugins/` 目录中所有的插件工厂函数（来自 `boot_exports.py`）
2. 根据插件定义的配置和规范，自动实例化插件
3. 将未注册的插件添加到 SQLite 数据库（`system_plugins` 表）
4. 同时将实例存储在内存注册表 `_plugin_instances`

```python
# In service.py bootstrap():
self._load_and_instantiate_plugins()  # Scan and register
self._storage.upsert_plugin(...)       # Persist to DB
```

#### 2. **Manual Registration (API)** / 手动注册（调用接口）

运行时通过 API 调用 `register_plugin()` 方法动态注册新插件：

```python
service.register_plugin(
    plugin_id="custom_plugin_123",
    plugin_instance=my_plugin,
    category="functional",
    version="1.0.0",
    behavior_key=None
)
```

---

## Plugin Classification / 插件分类

### 1. **Cognitive Plugins / 认知插件**

**特征**：
- **调用权限**：只能调用**功能插件**，不能调用其他认知插件
- **固定Code**：认知插件有固定的 `feature_code`，反映其逻辑职责
- **例子**：Q1-Q9 九问插件、预测分析、决策引擎等
- **生命周期**：由系统管理，状态转移受约束

**约束**：
```
❌ 认知插件 → 认知插件（禁止）
✅ 认知插件 → 功能插件（允许）
```

### 2. **Functional Plugins / 功能插件**

**特征**：
- **调用权限**：**不能主动调用**任何其他插件（认知或功能）
  - 仅作为被调用者存在
  - 返回结果，不做编排
- **独立执行**：可被单独执行（例如通过 API）
- **例子**：执行域插件、计算模型、解析数据、环境解释、传感器等

**约束**：
```
❌ 功能插件 → 认知插件（禁止）
❌ 功能插件 → 功能插件（禁止）
✅ 功能插件 ← 认知插件（作为被调用者）
```

### 3. **Interaction Model / 交互模式**

| 调用者 | 目标 | 允许 | 说明 |
|--------|------|------|------|
| **认知插件** | 认知插件 | ❌ | 避免循环逻辑依赖 |
| **认知插件** | 功能插件 | ✅ | 认知可以编排功能 |
| **认知插件** | 独立执行 | ✅ | 认知可单独执行 |
| **功能插件** | 认知插件 | ❌ | 功能必须保持独立 |
| **功能插件** | 功能插件 | ❌ | 功能必须保持独立 |
| **功能插件** | 独立执行 | ✅ | 功能可单独执行 |
| **外部调用者** | 任意 | ✅ | 外部调用通过 service 接口 |

---

## Plugin Lifecycle / 插件生命周期

### Status Transitions / 状态转移

```
CANDIDATE ──────┐
   │            │
   └──────────> SANDBOX_VERIFIED ──> ACTIVE <──> DEGRADED
                                        │           │
                                        └─> REVOKED
```

**Status Definitions**：
- **CANDIDATE**: 新发现或新注册的插件
- **SANDBOX_VERIFIED**: 通过沙箱验证（可选）
- **ACTIVE**: 生产就绪，可被调用
- **DEGRADED**: 性能下降但可用（3次连续失败自动降级）
- **REVOKED**: 被撤销或禁用

---

## Public Interface / 公共接口

### SystemPluginService Methods / 核心方法

```python
from zentex.plugins.service import SystemPluginService

service = SystemPluginService(db_path="plugins.db")

# 1. Bootstrap - 开机注册所有插件
service.bootstrap()

# 2. Query - 查询可用插件
result = service.query_plugins(category="cognitive", status="active")

# 3. Execute - 执行单个插件
feedback = await service.execute_plugin_once(
    plugin_id="my_plugin",
    task_id="task-123",
    parameters={...},
    trace_id="trace-456",
    originator_id="user-789"
)

# 4. Register - 手动注册新插件
service.register_plugin(
    plugin_id="new_plugin",
    plugin_instance=instance,
    category="functional"
)

# 5. Promote - 状态转移
service.promote_plugin(
    plugin_id="my_plugin",
    target_status=PluginLifecycleStatus.ACTIVE,
    reason="Verified in sandbox"
)
```

---

## Feature Upgrades & New Plugins / 功能升级与新插件

### 新插件创建流程 / New Plugin Development Flow

1. **在 `src/plugins/` 中创建插件**
   - 定义插件类或工厂函数
   - 指定 `feature_code`, `plugin_id`, `version`

2. **导出工厂函数到 `boot_exports.py`**
   - `boot_exports.py` 是所有插件工厂的中央导出点
   - 使用懒加载避免循环导入

3. **自动或手动注册**
   - 自动：下次启动时 `bootstrap()` 会自动注册
   - 手动：通过 API 调用 `register_plugin()`

4. **状态转移**
   - 新插件默认为 `CANDIDATE` 状态
   - 通过 `promote_plugin()` 升级到 `ACTIVE`

### 功能升级 / Existing Plugin Updates

更新现有插件的步骤：
1. 修改 `src/plugins/` 中的插件代码
2. 更新版本号
3. 如需新增行为，可能需要创建新 `feature_code`
4. 调用 `promote_plugin()` 更新状态
5. 自动降级机制会在失败时自动管理

---

## Database Schema / 数据库模式

### system_plugins Table

```sql
CREATE TABLE system_plugins (
    plugin_id TEXT PRIMARY KEY,           -- 唯一标识
    category TEXT NOT NULL,               -- "cognitive" 或 "functional"
    behavior_key TEXT,                    -- 行为分类键
    version TEXT,                         -- 版本号
    status TEXT,                          -- 生命周期状态
    spec_json TEXT,                       -- 完整规范 JSON
    source_kind TEXT,                     -- "built_in" 或 "manual_registration"
    usage_count INTEGER DEFAULT 0,        -- 执行次数
    failure_count INTEGER DEFAULT 0,      -- 失败次数
    created_at TEXT,                      -- 创建时间
    updated_at TEXT,                      -- 更新时间
    started_at TEXT,                      -- 激活时间
    stopped_at TEXT                       -- 停用时间
);
```

---

## Module Independence & Isolation / 模块独立性与隔离

**This is an independent functional module.** / **这是一个独立的功能模块。**

### Rules / 规则

1. **Public Interface Only** / 仅通过公共接口
   - 其他模块应仅导入 `SystemPluginService`
   - 不应直接访问 `storage.py`, `manager.py` 等内部文件

2. **No Direct Cross-Pillar Calls** / 禁止直接跨支柱调用
   - 插件系统与其他功能支柱的交互必须通过 `src/zentex/common` 进行
   - 避免创建架构上的耦合

3. **Clean Abstraction** / 清晰的抽象
   - 所有复杂逻辑在 manager/adapter 层
   - service.py 保持为纯粹的接口门面

### Entry Point / 导入入口

```python
# ✅ CORRECT
from zentex.plugins.service import SystemPluginService

# ❌ WRONG - Never do this
from zentex.plugins import service as svc  # 内部实现
from zentex.plugins.storage import PluginStorage  # 内部实现
```

---

## Design Principles / 设计原则

1. **Registration Authority** / 注册权限
   - 所有插件必须通过 `service.py` 进行注册和管理
   - 没有其他路径可以直接添加插件到系统

2. **Query Before Execute** / 执行前查询
   - 调用者应先通过 `query_plugins()` 获取可用插件列表
   - 然后选择性地执行特定插件

3. **Execution Isolation** / 执行隔离
   - 每次 `execute_plugin_once()` 调用是原子的
   - 不支持嵌套或并发执行（由上层调用者负责编排）

4. **Automatic Lifecycle Management** / 自动生命周期管理
   - 系统自动追踪执行统计
   - 自动降级失败插件
   - 手动升级通过 `promote_plugin()`

---

## Usage Examples / 使用示例

### 1. 如何正确调用认知插件 / How to Call Cognitive Plugins

认知插件通常由九问系统自动调用，但也可以通过 API 手动调用：

```python
import asyncio
from pathlib import Path
from zentex.plugins.service import SystemPluginService

async def call_cognitive_plugin():
    # 初始化服务
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()  # 加载所有插件
    
    # 调用认知插件（例如 Q1 "我在哪"）
    feedback = await service.execute_plugin_once(
        plugin_id="q1_where_am_i",
        task_id="task-001",
        parameters={
            "workspace_path": "/home/user/project",
            "environment": "development"
        },
        trace_id="trace-q1-001",
        originator_id="user@system"
    )
    
    # 检查执行结果
    if feedback.status == "done":
        print(f"✅ 认知插件执行成功")
        print(f"结果: {feedback.result}")
    else:
        print(f"❌ 认知插件执行失败: {feedback.error}")
        print(f"备注: {feedback.remarks}")

# 运行
asyncio.run(call_cognitive_plugin())
```

**关键点：**
- 认知插件的 `plugin_id` 格式通常是 `q<N>_<description>`
- 参数应该符合该认知插件的 `input_schema`
- 返回值是 `TaskFeedback` 对象
- 如果连续3次失败，插件自动降级为 DEGRADED 状态

---

### 2. 认知插件如何调用功能插件 / How Cognitive Plugins Call Functional Plugins

在认知插件内部，可以调用功能插件来获取底层能力：

```python
# 在认知插件的 run_tool() 或执行方法中
from zentex.plugins.service import SystemPluginService
import asyncio

class Q3WhatDoIHavePlugin:
    """Q3 认知插件：盘点系统拥有什么"""
    
    def __init__(self, plugin_service):
        self.plugin_service = plugin_service
        self.plugin_id = "q3_what_do_i_have"
    
    async def run_tool(self, context):
        """执行 Q3 逻辑"""
        
        # 第1步：查询可用的功能插件
        functional_plugins = self.plugin_service.query_plugins(
            category="functional",
            status="active"
        )
        print(f"找到 {len(functional_plugins)} 个功能插件")
        
        # 第2步：调用特定的功能插件来获取工作区信息
        inventory_result = await self.plugin_service.execute_plugin_once(
            plugin_id="host.telemetry",  # 功能插件ID
            task_id=context.get("task_id"),
            parameters={
                "metric_type": "resource",
                "include_processes": True
            },
            trace_id=context.get("trace_id"),
            originator_id=self.plugin_id,  # 关键：声明调用者是认知插件
            caller_plugin_id=self.plugin_id  # 确保约束检查通过
        )
        
        # 第3步：检查结果
        if inventory_result.status == "done":
            inventory_data = inventory_result.result
            print(f"✅ 功能插件返回数据: {inventory_data}")
            
            # 继续处理数据...
            processed_data = self._process_inventory(inventory_data)
            return {
                "assets": processed_data,
                "trace_id": context.get("trace_id")
            }
        else:
            print(f"❌ 功能插件调用失败: {inventory_result.error}")
            # 降级处理或返回备选结果
            return {"assets": [], "error": inventory_result.error}
    
    def _process_inventory(self, data):
        """处理功能插件返回的数据"""
        # 实现数据处理逻辑
        return data

# 使用示例
async def main():
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()

    feedback = await service.execute_plugin_once(
        plugin_id="q3_what_do_i_have",
        task_id="task-q3-001",
        parameters={
            "trace_id": "trace-q3-001",
        },
        trace_id="trace-q3-001",
        originator_id="example-user",
    )
    print(f"Q3 结果: {feedback.result}")

asyncio.run(main())
```

**约束验证：**
- ✅ 认知插件→功能插件：**允许** ✅
- ❌ 认知插件→认知插件：**禁止** ❌
- ❌ 功能插件→任何插件：**禁止** ❌

**自动状态管理：**
- 如果功能插件调用失败，失败次数会被记录
- 连续失败3次后，功能插件自动转为 DEGRADED 状态
- 认知插件应该检查 `feedback.status` 并实现降级逻辑

---

### 3. 如何单独调用功能插件 / How to Call Functional Plugins Directly

功能插件可以由外部系统直接调用（不通过认知插件）：

```python
import asyncio
from zentex.plugins.service import SystemPluginService

async def call_functional_plugin_directly():
    """
    直接调用功能插件示例
    场景：某个外部服务需要快速获取系统信息
    """
    
    # 初始化服务
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()
    
    # 第1步：查询所有可用的功能插件
    print("=== 查询功能插件 ===")
    functional_plugins = service.query_plugins(
        category="functional",
        status="active"
    )
    
    for plugin_info in functional_plugins:
        print(f"  - {plugin_info['plugin_id']}: {plugin_info.get('description', 'N/A')}")
    
    # 第2步：直接调用特定的功能插件
    print("\n=== 调用执行域插件 ===")
    
    result = await service.execute_plugin_once(
        plugin_id="execution.system",  # 功能插件
        task_id="external-task-001",
        parameters={
            "action_type": "list_directory",
            "path": "/tmp",
            "recursive": False
        },
        trace_id="trace-external-001",
        originator_id="external_system",
        caller_plugin_id=None  # 注意：这里不需要指定调用者，因为是外部调用
    )
    
    # 第3步：处理结果
    print("\n=== 执行结果 ===")
    if result.status == "done":
        print(f"✅ 功能插件执行成功")
        print(f"执行时间: {result.result.get('execution_time_ms', 'N/A')}ms")
        print(f"数据: {result.result.get('data', {})}")
    elif result.status == "failed":
        print(f"❌ 执行失败: {result.error}")
        print(f"详情: {result.remarks}")
    else:
        print(f"⚠️  状态: {result.status}")

# 其他常见的功能插件调用示例
async def examples_of_common_functional_plugins():
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()
    
    # 例1：获取主机遥测数据
    telemetry = await service.execute_plugin_once(
        plugin_id="host.telemetry",
        task_id="get-telemetry",
        parameters={"metric_type": "resource"},
        trace_id="trace-telemetry",
        originator_id="monitoring_system"
    )
    print(f"系统资源: {telemetry.result if telemetry.status == 'done' else telemetry.error}")
    
    # 例2：访问文件系统
    files = await service.execute_plugin_once(
        plugin_id="execution.system",
        task_id="list-files",
        parameters={
            "action_type": "list_directory",
            "path": "/home"
        },
        trace_id="trace-files",
        originator_id="file_manager"
    )
    print(f"文件列表: {files.result if files.status == 'done' else files.error}")
    
    # 例3：调用模型提供者
    model_output = await service.execute_plugin_once(
        plugin_id="core.model_provider",
        task_id="inference",
        parameters={
            "prompt": "What is 2+2?",
            "temperature": 0.7
        },
        trace_id="trace-model",
        originator_id="inference_service"
    )
    print(f"模型输出: {model_output.result if model_output.status == 'done' else model_output.error}")

# 运行示例
asyncio.run(call_functional_plugin_directly())
# asyncio.run(examples_of_common_functional_plugins())
```

**适用场景：**
- 外部工具需要调用某个功能插件
- 测试或调试单个功能插件
- 性能监控需要快速调用特定功能
- 某个工作流需要独立执行功能插件

**错误处理和自动状态更新：**
```python
async def robust_plugin_call():
    """鲁棒的插件调用，包含错误处理"""
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()
    
    MAX_RETRIES = 2
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            result = await service.execute_plugin_once(
                plugin_id="unreliable_plugin",
                task_id="task-retry",
                parameters={"retry": retry_count},
                trace_id="trace-retry",
                originator_id="retry_handler"
            )
            
            if result.status == "done":
                print(f"✅ 成功")
                return result.result
            
            elif result.status == "failed":
                print(f"❌ 失败: {result.error}")
                
                # 检查插件状态是否已自动降级
                plugin_info = service.query_plugins(
                    category="functional"
                )
                for p in plugin_info:
                    if p['plugin_id'] == "unreliable_plugin":
                        print(f"插件当前状态: {p['status']}")
                        if p['status'] == "degraded":
                            print("⚠️  插件已自动降级，不再重试")
                            return None
                
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    print(f"重试 {retry_count}/{MAX_RETRIES}...")
                    
        except Exception as e:
            print(f"❌ 异常: {e}")
            retry_count += 1
    
    print("❌ 已达到最大重试次数")
    return None

asyncio.run(robust_plugin_call())
```

---

## Error Handling & Status Auto-Update / 错误处理与状态自动更新

### 自动状态更新流程 / Automatic Status Update Flow

```
调用插件
  │
  ├─ 执行失败 ─ 记录失败次数 ─ 第3次失败?
  │                              │
  │                              No: 继续运行（ACTIVE）
  │                              │
  │                              Yes: 自动降级
  │                                    │
  │                                    降级到 DEGRADED
  │                                    记录日志
  │                                    更新数据库
  │
  └─ 执行成功 ─ 重置失败次数 ─ 保持 ACTIVE
```

### 查看插件状态 / Checking Plugin Status

```python
# 查询特定插件的当前状态
plugin_info = service.query_plugins(category="functional")
for p in plugin_info:
    if p['plugin_id'] == "my_plugin":
        print(f"状态: {p['status']}")           # ACTIVE, DEGRADED, REVOKED
        print(f"使用次数: {p['usage_count']}")
        print(f"失败次数: {p['failure_count']}")
        print(f"最后执行: {p['last_executed_at']}")
```

### 手动恢复或升级插件 / Manual Plugin Status Management

```python
# 将降级的插件恢复为 ACTIVE
service.promote_plugin(
    plugin_id="recovered_plugin",
    target_status=PluginLifecycleStatus.ACTIVE,
    reason="Manual recovery after fix"
)

# 撤销不可靠的插件
service.promote_plugin(
    plugin_id="broken_plugin",
    target_status=PluginLifecycleStatus.REVOKED,
    reason="Permanently disabled due to security issue"
)
```

---

## Plugin Call Failure Handling / 插件调用失败处理

### 调用失败类型与自动状态更新 / Failure Types and Auto Status Updates

| 失败类型 | 触发条件 | 自动状态更新 | 说明 |
|---------|---------|------------|------|
| **plugin_not_found** | 插件未注册 | ❌ 否 | 插件不存在，无状态可更新 |
| **plugin_not_active** | 插件状态非ACTIVE | ❌ 否 | 插件已被降级/撤销，表示已停用 |
| **plugin_not_instantiated** | 插件在内存中不存在 | ⚠️ 告警 | 系统错误，需要检查bootstrap()调用 |
| **execution_error** | 插件实际执行失败 | ✅ 是 | 记录失败次数，3次后自动降级为DEGRADED |
| **hierarchy_violation** | 调用约束违反 | ❌ 否 | 调用链不符合规则，目标插件保持ACTIVE |

### 实现自动状态更新的机制 / Automatic Status Update Mechanism

系统在以下情况下**自动更新插件状态**：

```python
# 情况1：连续执行失败 → 自动降级
# 失败次数: 1 → ACTIVE（继续运行）
# 失败次数: 2 → ACTIVE（继续运行）  
# 失败次数: 3 → DEGRADED（自动降级，停止调用）

# 情况2：执行成功 → 重置失败次数
# 成功后失败次数重置为0，状态保持ACTIVE

# 情况3：手动升级 → 恢复到ACTIVE
# 通过promote_plugin()手动恢复
```

**代码示例：查看自动更新的状态**

```python
import asyncio
from zentex.plugins.service import SystemPluginService

async def monitor_plugin_status():
    """监控插件的自动状态更新"""
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()
    
    plugin_id = "unreliable_plugin"
    
    # 进行多次调用，观察状态变化
    for attempt in range(5):
        result = await service.execute_plugin_once(
            plugin_id=plugin_id,
            task_id=f"attempt-{attempt}",
            parameters={},
            trace_id=f"trace-{attempt}",
            originator_id="monitor"
        )
        
        # 查询当前状态
        plugin_info = service.query_plugins()
        for p in plugin_info:
            if p['plugin_id'] == plugin_id:
                status = p['status']
                failures = p.get('failure_count', 0)
                print(f"尝试 {attempt+1}: 状态={status}, 失败次数={failures}")
                
                # 当状态变为DEGRADED时停止调用
                if status == "degraded":
                    print(f"⚠️  插件已自动降级，不再继续调用")
                    return
        
        print(f"  结果: {result.status} - {result.error if result.status == 'failed' else 'OK'}")

asyncio.run(monitor_plugin_status())
```

**数据库中的状态跟踪**

```sql
-- 查看插件的执行统计和状态
SELECT 
    plugin_id,
    status,
    usage_count,
    failure_count,
    last_executed_at,
    updated_at
FROM system_plugins
WHERE category = 'functional'
ORDER BY updated_at DESC;
```

### 调用失败时的最佳实践 / Best Practices When Calls Fail

```python
async def resilient_plugin_invocation():
    """具有弹性的插件调用实现"""
    service = SystemPluginService(db_path="plugins.db")
    service.bootstrap()
    
    plugin_id = "target_plugin"
    
    # 1. 始终先检查插件状态
    plugin_info = service.query_plugins(category="functional")
    target_plugin = next((p for p in plugin_info if p['plugin_id'] == plugin_id), None)
    
    if not target_plugin:
        print(f"❌ 插件 {plugin_id} 不存在")
        return None
    
    if target_plugin['status'] != 'active':
        print(f"❌ 插件 {plugin_id} 当前状态为 {target_plugin['status']}")
        # 检查是否是自动降级
        if target_plugin['status'] == 'degraded':
            print(f"⚠️  失败次数: {target_plugin.get('failure_count', 0)}")
            print(f"可尝试手动恢复: service.promote_plugin(..., PluginLifecycleStatus.ACTIVE)")
        return None
    
    # 2. 尝试调用
    try:
        result = await service.execute_plugin_once(
            plugin_id=plugin_id,
            task_id="resilient-call",
            parameters={"data": "test"},
            trace_id="trace-resilient",
            originator_id="resilience_handler"
        )
        
        # 3. 检查结果
        if result.status == "done":
            print(f"✅ 执行成功: {result.result}")
            return result.result
        
        elif result.status == "failed":
            print(f"❌ 执行失败: {result.error}")
            print(f"详情: {result.remarks}")
            
            # 4. 再次检查状态（可能已自动降级）
            updated_plugin = service.query_plugins()
            for p in updated_plugin:
                if p['plugin_id'] == plugin_id:
                    print(f"当前状态: {p['status']}")
                    if p['status'] == "degraded":
                        print("💡 建议: 联系管理员检查插件实现")
        
        return None
        
    except Exception as e:
        print(f"❌ 调用异常: {e}")
        return None

asyncio.run(resilient_plugin_invocation())
```

### 日志中的状态更新记录 / Status Update Logs

系统会在以下事件记录日志：

```
# 自动降级日志
[Plugins] Auto-degrading <plugin_id> after 3 failures
[Plugins] Failed to auto-degrade <plugin_id>: <error>

# 执行日志
[Plugins] Call allowed: cognitive → functional
[Plugins] CONSTRAINT VIOLATION: <caller> → <target>
[Plugins] Execution error in <plugin_id>: <exception>
```

检查日志可以跟踪插件的状态变化：

```python
import logging

# 启用DEBUG日志查看详细的状态更新
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('zentex.plugins')

# 现在所有插件系统的日志都会被打印
# 包括状态自动降级、执行失败等事件
```
