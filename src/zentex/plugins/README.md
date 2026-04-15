# Plugins Module / 插件模块

## 🚫 重要架构约束

**所有插件的访问和执行都必须通过 `SystemPluginService` 进行。**

直接从 `plugins.*` 导入插件工厂函数是**严格禁止**的。

```python
# ❌ 禁止（违反架构）
from plugins.nine_questions.q1_where_am_i import build_q1_where_am_i_plugin
plugin = build_q1_where_am_i_plugin()

# ✅ 正确方式
from zentex.plugins.service import (
    SystemPluginService,
    query_all_plugins_by_operational_status,
    rehydrate_registered_plugins,
)
service = SystemPluginService(db_path="plugins.db")
rehydrate_registered_plugins(service)
plugins = query_all_plugins_by_operational_status(
    service,
    feature_code="nine_questions.q1",
    operational_status="enabled",
)
feedback = await service.execute_plugin_once(
    plugin_id=plugins[0]["plugin_id"],
    task_id=task_id,
    parameters=parameters,
    trace_id=trace_id,
    originator_id=originator_id,
)
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

## Bootstrap Model / 启动模型

`SystemPluginService` 现在要区分三类动作，不再把所有语义都混在 `bootstrap()` 这个名字里：

1. `register_discovered_plugins(service)`
   - 扫描已发现插件并把缺失插件写入数据库
   - 这是**写库动作**
2. `rehydrate_registered_plugins(service)`
   - 只把数据库里已注册插件回填到运行时内存
   - 这是**非写库动作**
3. `ensure_default_plugin_relationships(service)`
   - 显式补默认关系
   - 这是**写库动作**

`service.bootstrap()` 目前仍保留，但它只是历史组合入口，内部会顺序编排上面三步。  
新架构里，外部调用方不应再把 `bootstrap()` 理解成“唯一且默认正确的初始化方式”。

### 调用建议 / Recommended Usage

- `launcher`
  - 不应调用插件模块内部动作
  - 只装配 `plugins.service` 依赖入口
- `kernel`
  - 运行时只依赖 `plugins.service` 的查询与执行能力
- `plugins` 模块自身
  - 如需扫描代码、注册插件、补默认关系，必须显式调用对应 API

## Public Query APIs / 公开查询接口

`src/zentex/plugins/service.py` 现在对外统一只保留以下查询语义：

1. `query_all_plugins_by_lifecycle(...)`
   - 查询所有插件的**生命周期**
   - 可按 `category / lifecycle_status / behavior_key / feature_code` 过滤
2. `query_all_plugins_by_operational_status(...)`
   - 查询所有插件的**运行状态**
   - 可按 `category / operational_status / behavior_key / feature_code` 过滤
3. `query_cognitive_plugin_functionals_by_lifecycle(cognitive_plugin_id, ...)`
   - 查询某个认知插件下所有功能插件的**生命周期**
4. `query_cognitive_plugin_functionals_by_operational_status(cognitive_plugin_id, ...)`
   - 查询某个认知插件下所有功能插件的**运行状态**

### 调用约束 / Call-Site Restrictions

- `web_console/plugins` 列表页允许同时调用：
  - 生命周期查询接口
  - 运行状态查询接口
- 认知插件详情页允许调用：
  - 指定认知插件的生命周期查询接口
- 其他不属于 `src/zentex/plugins`、`src/zentex/upgrade`、插件控制台链路的模块：
  - **只允许调用运行状态查询接口**
  - **禁止调用生命周期查询接口**

---

## Plugin Classification / 插件分类

### 1. **Cognitive Plugins / 认知插件**

**特征**：
- **调用权限**：只能调用**功能插件**，不能调用其他认知插件
- **固定Code**：认知插件有固定的 `feature_code`，反映其逻辑职责
- **例子**：Q1-Q9 九问插件、记忆提取器、反思生成器等
- **生命周期**：由系统管理，受强制约束（见下文）

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

## Calling Rules / 调用规则

### 外部模块调用认知插件

- 认知插件的调用点必须写死为固定能力编码，例如 `nine_questions.q1` 到 `nine_questions.q9`。
- 外部模块不允许扫描全部认知插件后自行决定调用哪个版本。
- 外部模块必须先通过 `query_all_plugins_by_operational_status(...)` 按固定 `feature_code` 查询**激活且启用**的认知插件。
- 只有**生命周期为 `ACTIVE` 且 `operational_status == "enabled"`** 的认知插件允许执行。
- 若某个认知能力没有启用版本，必须直接返回“能力不可用”，并记录重点告警；禁止回退到 `candidate / sandbox_verified / revoked / degraded` 版本。

### 认知插件内部调用功能插件

- 认知插件内部不写死具体功能插件版本。
- 必须先通过 `query_cognitive_plugin_functionals_by_operational_status(...)` 查询当前认知插件绑定的功能插件。
- 只允许执行**生命周期为 `ACTIVE` 且 `operational_status == "enabled"`** 的功能插件。
- 未启用、异常或不可用的功能插件一律不调用。
- 默认执行顺序是“先查询，再依次执行激活且启用的插件”；具体顺序由认知插件按角色、优先级或绑定顺序决定。

### 外部模块直接调用功能插件

- 如果调用方不是认知插件内部逻辑，则目标功能插件编码可以写死。
- 但调用前仍必须先通过 `query_all_plugins_by_operational_status(...)` 做状态检查。
- 只有**生命周期为 `ACTIVE` 且 `operational_status == "enabled"`** 的功能插件允许执行。
- 功能插件未启用时，不调用。

### Strictly Forbidden / 严格禁止

- 禁止外部模块直接 import `plugins.*` 下的插件实现并自行实例化。
- 禁止外部模块直接 import `zentex.plugins.service.manager`、`zentex.plugins.service.query` 等内部实现。
- 禁止外部模块用生命周期接口来判断插件是否可调用。
- 禁止调用未启用的功能插件。

---

## Plugin Lifecycle And Operational State / 插件生命周期与运行状态

### 重要口径统一 / Required Terminology

> **生命周期（Lifecycle）和状态（Operational State）不是一回事。**

- **生命周期**：描述插件版本处于治理流程的哪个阶段
  - `CANDIDATE`
  - `SANDBOX_VERIFIED`
  - `ACTIVE`
  - `DEGRADED`
  - `REVOKED`
- **状态**：描述插件当前是否真正可供业务使用
  - `启用`
  - `停用`
  - `异常`
  - `不可用`

Web 控制台必须同时展示这两个字段，禁止把生命周期直接当作状态显示。

### Operational State Rules / 运行状态规则

- 当插件 **生命周期不是 `ACTIVE`** 时，状态统一显示为 **`不可用`**
- 只有 **生命周期为 `ACTIVE`** 的插件，才允许出现以下三种运行状态：
  - `启用`
  - `停用`
  - `异常`
- 其中：
  - `启用`：生命周期为 `ACTIVE`，且实例正常运行、可被调用
  - `停用`：生命周期为 `ACTIVE`，但当前实例未运行或已停止提供服务
  - `异常`：生命周期为 `ACTIVE`，但当前健康状态异常，不能按正常能力提供服务

### Lifecycle Definitions / 生命周期定义

### Lifecycle Transitions / 生命周期转移

```
CANDIDATE ──────┐
   │            │
   └──────────> SANDBOX_VERIFIED ──> ACTIVE <──> DEGRADED
                                        │
                                        └─> REVOKED
```

**Lifecycle Definitions**：
- **CANDIDATE**: 新发现或新注册的插件，尚未通过验证
- **SANDBOX_VERIFIED**: 通过沙箱验证，等待激活
- **ACTIVE**: 生产就绪，可被调用
- **DEGRADED**: 连续失败后自动降级，不再被调用（可手动恢复）
- **REVOKED**: 被撤销，永久停用

---

## Cognitive Plugin Always-Active Policy / 认知插件常驻激活策略

## Cognitive Plugin Always-Active Policy / 认知插件常驻激活策略

### 核心规则 / Core Rules

> **认知插件必须始终保持 ACTIVE 状态。禁止关闭、降级或撤销任何认知插件。即使在版本升级期间，也必须确保至少有一个版本处于激活状态。**

**三点不可违背的约束：**

1. ✋ **禁止关闭** — 任何关闭操作都会被拦截
   - `disable_plugin(cognitive_id, ...)` → 返回，什么都不做，记录 WARNING

2. 🔄 **升级期间必须有激活版本** — 蓝绿顺序严格遵守  
   - 新版本激活失败 → 旧版本保持不变
   - 新版本激活成功 → 旧版本才停用
   - **禁止中间状态：没有任何版本是 ACTIVE**

3. 🚨 **零存活即告警** — 如果所有版本全部离线
   - 记录 CRITICAL 日志（见下文"零存活 CRITICAL 警告"）
   - 包含具体原因、影响的功能、恢复步骤
   - 系统停止该插件的相关业务

系统在三个层次强制执行此规则：

| 保护层级 | 位置 | 作用 |
|---------|------|------|
| `promote_plugin()` | `ManagementService` | 激活时检查蓝绿顺序，确保不会出现无版本激活的中间态；激活失败则允许旧版本继续运行 |
| `disable_plugin()` | `ManagementService` | 认知插件调用直接返回，不执行任何操作 |
| `_stop_superseded_plugin()` | `ManagementService` | 停用旧版本前验证新版本已激活；如果新版本未激活，则不停用旧版本 |
| `_check_zero_survivor()` | `ManagementService` | 在停用旧版本后检查是否仍有版本激活；如无则发出 CRITICAL 告警 |

### 受保护的认知插件 ID

以下插件 ID 以及所有以 `nine-question-` 或 `nine_question_` 开头的 ID 均被列为"永久激活"（always-active）：

```
nine-question-q1-where-am-i
nine-question-q2-who-am-i
nine-question-q3-what-do-i-have
nine-question-q4-what-can-i-do
nine-question-q5-what-am-i-allowed-to-do
nine-question-q6-what-should-i-not-do
nine_question_q7_alternatives
nine_question_q8_decision
nine_question_q9_posture
memory_extractor
reflection_generator
```

### 零存活 CRITICAL 警告 / Zero-Survivor CRITICAL Warning

当某个 `behavior_key` 对应的**所有版本都失去 ACTIVE 状态**时，系统会发出 `CRITICAL` 级别日志，内容包括：

- 哪个 `behavior_key` 已离线
- 当前所有版本的状态（DEGRADED/REVOKED/CANDIDATE/etc）
- 是什么操作触发了此次状态转变（激活失败或旧版本停用）
- 哪个新版本无法激活（导致无法替换旧版本），或旧版本全部失败
- 需要采取什么行动来恢复
- 由于该认知插件离线，哪些功能被停止使用

**CRITICAL 告警的精确格式：**

```
[时间] CRITICAL — NO ACTIVE VERSION remaining for behavior_key 'xxx' after [OPERATION].

Failure Context:
  - behavior_key: q1_where_am_i
  - All versions offline:
      * v1.0: DEGRADED (failed 3+ times, last error: [error trace])
      * v2.0: CANDIDATE (activation failed: [error trace])

Trigger Event:
  [选项1] New version v2.0 failed to activate during promote_plugin()
  [选项2] All versions degraded after continuous failures
  [选项3] Attempted to stop all versions during blue-green replacement

Impact:
  - Cognitive capability 'q1_where_am_i' (Where am I?) is NOW OFFLINE
  - Feature stops: [列举依赖此插件的功能]
  - Task execution: 所有调用 q1 的任务将失败并返回 "capability unavailable"
  - System status: 需要立临调整

ACTION REQUIRED:
  1. 🔍 Check detailed logs for specific error in v2.0 or degradation reason
  2. 🔧 Option A (if v1.0 viable): 
     - service.promote_plugin('q1_v1', SANDBOX_VERIFIED, reason="Recovery")
     - service.promote_plugin('q1_v1', ACTIVE, reason="Recovery after v2.0 failure")
  3. 🚀 Option B (if v2.0 fixable):
     - Review and fix root cause of v2.0 failure
     - Reregister v2.0 as new plugin_id with corrected version
     - Attempt activation again
  4. ⚠️ Option C (emergency):
     - Deploy hotfix immediately and register new CANDIDATE version
  5. 📊 Monitor:
     - Watch for cascading failures in dependent features
     - Track cognitive task failure rates for 'q1'
     - Set up alert for plugin recovery

Reference:
  - Affected plugin_id(s): [列表]
  - Affected feature_code(s): [列表]
  - Last healthy version: [版本号]
  - Last update/change: [时间]
```

此警告同样适用于以下场景：
- 激活新版本失败，且无旧版本可用
- 所有版本连续执行失败后全部降级（不适用蓝绿）
- 手动 revoke 所有版本（管理员错误）

**防护机制：**

系统设置了多道防线防止此警告：
1. `Cognitive Plugin Always-Active Policy` 正常情况下禁止关闭认知插件
2. `disable_plugin()` 对认知插件直接返回，不执行任何操作
3. 蓝绿激活策略确保新版本必须激活成功才停用旧版本
4. 若检测到零存活，立即发出 CRITICAL 告警以便快速响应

---

## Blue-Green Activation Policy / 蓝绿激活策略

升级或替换插件时，系统采用严格的蓝绿顺序，保证旧版本**只有在新版本确认运行正常之后才会停止**。

### 核心原则

> **所有类型的插件在激活时都遵循严格的蓝绿顺序：新版本激活成功之后，才会停止旧版本。激活失败时，旧版本完全不受影响。**

### 激活流程 / Activation Flow

```
promote_plugin(X, ACTIVE)
  │
  ├── Step 1: 快照当前所有 behavior_key 相同的 ACTIVE 插件（"旧版本"列表）
  │
  ├── Step 2: 尝试实例化新插件 X
  │     │
  │     ├── 实例化失败?
  │     │     ├── 是认知插件且无旧版本?
  │     │     │     └── 记录 CRITICAL 日志（见下文"零存活 CRITICAL 警告"）
  │     │     ├── 记录 ERROR 日志（包含旧版本仍在运行的说明或无旧版本的说明）
  │     │     └── 中止，数据库和旧版本完全不变，什么都不做
  │     │
  │     └── 实例化成功 → 继续
  │
  ├── Step 3: 将 X 的状态写入数据库（ACTIVE）
  │
  └── Step 4: 逐一停用旧版本（降级为 DEGRADED）
              │
              ├── 单个旧版本停用失败 → 记录 WARNING，继续停用其余旧版本
              │
              └── 所有旧版本停用后，检查是否有版本存活
                    │
                    └── 认知插件全部离线?
                        └── 记录 CRITICAL 日志（见下文"零存活 CRITICAL 警告"）
```

### 各类插件的策略差异

| 插件类型 | 情景 | 新版本激活失败 | 旧版本状态 | 说明 |
|---------|------|--------------|---------|------|
| **认知插件** | 有旧版本在线 | 停止激活，中止 | 保持 ACTIVE 不变 | 确保常驻激活 |
| **认知插件** | 无旧版本在线 | 停止激活，中止 | 无版本存活 → CRITICAL 告警 | **禁止发生**，需要重点警告 |
| **功能插件** | 有旧版本在线 | 停止激活，中止 | 保持 ACTIVE 不变 | 兼容性保证 |
| **功能插件** | 无旧版本在线 | 停止激活，中止 | 保持无激活状态 | 允许无版本激活 |

### 认知插件激活失败处理 / Cognitive Plugin Activation Failure Handling

**场景 1：有激活版本，新版本激活失败**
```
当前状态: Cognitive Plugin "q1" v1.0 (ACTIVE) 在线 + v2.0 新激活失败
行为: 
  1. 停止激活 v2.0
  2. 什么都不做
  3. v1.0 继续运行（ACTIVE 不变）
  4. 记录 ERROR 日志: "Failed to activate v2.0; v1.0 remains ACTIVE"
结果: 认知功能不中断 ✅
```

**场景 2：无激活版本，激活唯一版本失败（严重故障）**
```
当前状态: Cognitive Plugin "q1" 没有任何 ACTIVE 版本（可能全部 DEGRADED/REVOKED）
新激活: 新版本 v2.0 尝试激活，但实例化失败
行为:
  1. 停止激活 v2.0
  2. 什么都不做
  3. 记录 CRITICAL 日志:
     ┌─────────────────────────────────────────────────────────────┐
     │ CRITICAL — NO ACTIVE VERSION remaining for behavior_key     │
     │ 'nine_question_q1' after activation attempt.                │
     │                                                               │
     │ Failed to activate v2.0: [error details]                   │
     │ No previous active version to fall back to.                 │
     │                                                               │
     │ This cognitive capability is NOW OFFLINE.                   │
     │ Plugin Status: Behavior 'nine_question_q1'                  │
     │   - v1.0: DEGRADED (failed 3+ times)                        │
     │   - v2.0: CANDIDATE (activation failed)                     │
     │                                                               │
     │ ACTION REQUIRED:                                             │
     │   1. Review error logs of v2.0 activation                   │
     │   2. If v1.0 is viable, restore via promote_plugin()       │
     │   3. Issue hotfix if v2.0 is irreparable                    │
     │   4. Monitor cognitive task execution for 'q1'              │
     │      (should fail gracefully with "capability unavailable") │
     └─────────────────────────────────────────────────────────────┘
结果: 认知功能离线，触发应急程序 🚨
```

### 功能插件激活失败处理 / Functional Plugin Activation Failure Handling

**场景 1：有激活版本，新版本激活失败**
```
当前状态: Functional Plugin "executor" v1.0 (ACTIVE) 在线 + v2.0 新激活失败
行为:
  1. 停止激活 v2.0
  2. 什么都不做
  3. v1.0 继续运行（ACTIVE 不变）
  4. 记录 ERROR 日志: "Failed to activate v2.0; v1.0 remains ACTIVE"
结果: 功能继续提供 ✅
```

**场景 2：无激活版本，激活新版本失败**
```
当前状态: Functional Plugin "executor" 没有任何 ACTIVE 版本（可能全部 DEGRADED）
新激活: 新版本 v2.0 尝试激活，但实例化失败
行为:
  1. 停止激活 v2.0
  2. 什么都不做
  3. 记录 ERROR 日志: "Failed to activate v2.0; no fallback version"
  4. 不记录 CRITICAL（允许功能插件无激活状态）
结果: 功能暂时不可用，允许手动恢复 ⚠️
```

### 新版本激活成功，旧版本停用流程 / Old Version Stopping After New Activation Success

**只有当新版本成功激活后，系统才会停用旧版本：**

```
New Version v2.0 promote_plugin(ACTIVE) SUCCESS
  │
  ├── Step A: 写入数据库（v2.0 status → ACTIVE）- 提交
  │
  ├── Step B: 在内存中激活 v2.0 实例
  │
  └── Step C: 停用旧版本（不可逆）
        │
        ├── 查询 behavior_key 相同的所有 v1.0 实例
        ├── 逐一降级为 DEGRADED
        ├── 从内存中卸载（如适用）
        │
        └── 检查此 behavior_key 是否仍有 ACTIVE 版本
             │
             └── 认知插件 + 全部离线?
                 └── 记录 CRITICAL 告警（如上所述）
```

**关键保证：**
- ✅ v2.0 必须首先完全激活（包括数据库写入和内存加载）
- ✅ 只有 v2.0 确认运行无误后，v1.0 才会被降级
- ✅ v1.0 停用过程中如果失败，不影响 v2.0 运行
- ✅ 如果 v2.0 激活失败，v1.0 保持完全不变

---

## Plugin Registration / 插件注册

### Registration Methods / 注册方式

#### 1. **Explicit Discovery Registration** / 显式发现并注册

当插件模块需要把代码中已发现的插件写入数据库时，应显式调用：

```python
from zentex.plugins.service import SystemPluginService, register_discovered_plugins

service = SystemPluginService(db_path="plugins.db")
result = register_discovered_plugins(service)
```

这一步会：
1. 扫描 `src/plugins/` 中可发现的插件单元
2. 实例化缺失插件
3. 将未注册插件写入 SQLite 数据库

这属于**插件模块自己的写库动作**，不应由 `launcher` 隐式触发。

#### 2. **Runtime Rehydration** / 运行时回填

当调用方只需要把数据库中已注册插件加载进运行时内存时，应调用：

```python
from zentex.plugins.service import SystemPluginService, rehydrate_registered_plugins

service = SystemPluginService(db_path="plugins.db")
result = rehydrate_registered_plugins(service)
```

这一步只会：
1. 读取数据库里的已注册插件
2. 按需实例化到内存
3. 同步运行时状态缓存

这一步**不会注册新插件，不会写入绑定关系**。

#### 3. **Default Relationship Seeding** / 默认关系补种

如果插件模块需要补默认绑定关系，应显式调用：

```python
from zentex.plugins.service import SystemPluginService, ensure_default_plugin_relationships

service = SystemPluginService(db_path="plugins.db")
result = ensure_default_plugin_relationships(service)
```

这一步属于**显式写库动作**，必须与运行时回填区分。

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

## Public Interface / 公共接口

### SystemPluginService Methods / 核心方法

```python
from zentex.plugins.service import (
    SystemPluginService,
    query_all_plugins_by_operational_status,
    rehydrate_registered_plugins,
)

service = SystemPluginService(db_path="plugins.db")

# 1. Rehydrate - 回填数据库中已注册插件到运行时
rehydrate_registered_plugins(service)

# 2. Query - 查询可用插件
result = query_all_plugins_by_operational_status(
    service,
    category="cognitive",
    operational_status="enabled",
)

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

# 5. Promote - 状态转移（遵守蓝绿激活策略）
service.promote_plugin(
    plugin_id="my_plugin",
    target_status=PluginLifecycleStatus.ACTIVE,
    reason="Verified in sandbox"
)

# 6. Enable / Disable - 手动开关功能插件
service.enable_plugin("my_functional_plugin")
service.disable_plugin("my_functional_plugin", reason="Scheduled maintenance")
# ⚠️ 认知插件调用 disable_plugin() 会被直接忽略并记录 WARNING

# 7. Batch Disable - 批量关闭功能插件
disabled = service.batch_disable(category="functional", reason="Emergency shutdown")

# 8. Activate All Functional - 一键激活所有功能插件
result = service.activate_all_functional(reason="Manual bulk activation")
# result = {
#   "activated": [...],        # 本次新激活的插件
#   "already_active": [...],   # 原本已激活的插件
#   "skipped_cognitive": [...],# 跳过的认知插件
#   "failed": {...},           # 激活失败的插件及原因
# }
```

### 组合入口 `bootstrap()` 说明

```python
service.bootstrap()
```

`bootstrap()` 当前仍可用，但它是历史组合入口，等价于按顺序执行：

1. `register_discovered_plugins(service)`
2. `rehydrate_registered_plugins(service)`
3. `ensure_default_plugin_relationships(service)`

因此：

- 如果你需要显式控制“是否写库”，不要直接用 `bootstrap()`
- 如果你只是要运行时加载已注册插件，优先使用 `rehydrate_registered_plugins(service)`
- 如果你要做插件治理动作，显式调用对应 API

### activate_all_functional 详细说明

```python
result = service.activate_all_functional(reason="My reason")

# 查看激活结果
print(f"新激活: {result['activated']}")
print(f"原本已激活: {result['already_active']}")
print(f"跳过（认知插件）: {result['skipped_cognitive']}")
print(f"失败: {result['failed']}")  # dict: {plugin_id: error_message}
```

**行为说明：**
- 跳过所有 `category == "cognitive"` 的插件以及所有 always-active 认知插件
- 对每个非 ACTIVE 功能插件执行 `SANDBOX_VERIFIED → ACTIVE` 晋升
- 遵守蓝绿策略：单个插件激活失败不影响其他插件
- 失败信息汇总在返回值 `failed` 字典中，不抛出异常

---

## Feature Upgrades & New Plugins / 功能升级与新插件

### 新插件创建流程 / New Plugin Development Flow

1. **在 `src/plugins/` 中创建插件**
   - 定义插件类或工厂函数
   - 指定 `feature_code`, `plugin_id`, `version`, `behavior_key`

2. **导出工厂函数到 `boot_exports.py`**
   - `boot_exports.py` 是所有插件工厂的中央导出点
   - 使用懒加载避免循环导入

3. **显式注册或手动注册**
   - 显式发现注册：调用 `register_discovered_plugins(service)`
   - 手动注册：通过 API 调用 `register_plugin()` 后再调用 `promote_plugin()`

4. **状态转移**
   - 新插件默认为 `CANDIDATE` 状态
   - 通过 `promote_plugin()` 升级到 `ACTIVE`（遵守蓝绿策略）

### 功能插件升级 / Upgrading a Functional Plugin

更新现有功能插件的步骤：
1. 修改 `src/plugins/` 中的插件代码，更新版本号
2. 注册新版本（同 `behavior_key`，新 `plugin_id` 或新 `version`）
3. 调用 `promote_plugin(new_id, ACTIVE, ...)`
4. 蓝绿策略确保：新版本激活成功后，旧版本自动降级；新版本失败则旧版本继续运行

### 认知插件升级 / Upgrading a Cognitive Plugin

> ⚠️ **认知插件升级期间，旧版本绝对不能停止，直到新版本被确认激活。**

1. 用新 `plugin_id` 注册新版本（相同 `behavior_key`）
2. 调用 `promote_plugin(new_id, ACTIVE, ...)`
3. 系统自动按蓝绿顺序：先激活新版本，再停用旧版本
4. 若新版本实例化失败：旧版本保持不变，系统记录 CRITICAL 日志

---

## Database Schema / 数据库模式

### system_plugins Table

```sql
CREATE TABLE system_plugins (
    plugin_id TEXT PRIMARY KEY,           -- 唯一标识
    category TEXT NOT NULL,               -- "cognitive" 或 "functional"
    behavior_key TEXT,                    -- 行为分类键（用于蓝绿冲突检测）
    version TEXT,                         -- 版本号
    lifecycle_status TEXT,                -- 生命周期：candidate / sandbox_verified / active / degraded / revoked
    operational_status TEXT,              -- 运行状态：enabled / stopped / abnormal / unavailable
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
   - 不应直接访问 `storage.py`, `manager.py`, `manage.py` 等内部文件

2. **No Direct Cross-Pillar Calls** / 禁止直接跨支柱调用
   - 插件系统与其他功能支柱的交互必须通过 `src/zentex/common` 进行
   - 避免创建架构上的耦合

3. **Clean Abstraction** / 清晰的抽象
   - 所有复杂逻辑在 manager/adapter 层
   - `service.py` 保持为纯粹的接口门面

### Entry Point / 导入入口

```python
# ✅ CORRECT
from zentex.plugins.service import SystemPluginService

# ❌ WRONG - Never do this
from zentex.plugins import service as svc  # 内部实现
from zentex.plugins.storage import PluginStorage  # 内部实现
from zentex.plugins.service.manage import ManagementService  # 内部实现
```

---

## Design Principles / 设计原则

1. **Registration Authority** / 注册权限
   - 所有插件必须通过 `service.py` 进行注册和管理
   - 没有其他路径可以直接添加插件到系统

2. **Query Before Execute** / 执行前查询
   - 调用者应先通过 `query_all_plugins_by_operational_status()` 获取可用插件列表
   - 然后选择性地执行特定插件

3. **Execution Isolation** / 执行隔离
   - 每次 `execute_plugin_once()` 调用是原子的
   - 不支持嵌套或并发执行（由上层调用者负责编排）

4. **Automatic Lifecycle Management** / 自动生命周期管理
   - 系统自动追踪执行统计
   - 连续失败3次后自动降级功能插件
   - 手动升级通过 `promote_plugin()`

5. **Cognitive Plugins Are Immutable in Status** / 认知插件状态不可降级
   - 认知插件的状态只能向 ACTIVE / SANDBOX_VERIFIED 方向转移
   - 任何降级、撤销或禁用操作均被系统拦截并记录警告

6. **Blue-Green Safety** / 蓝绿安全
   - 任何插件激活操作不会先停旧版本
   - 新版本实例化失败时，旧版本完全不受影响
   - 零存活检测在停用旧版本后立即触发 CRITICAL 告警

---

## Usage Examples / 使用示例

### 1. 如何正确调用认知插件 / How to Call Cognitive Plugins

认知插件通常由九问系统自动调用，但也可以通过 API 手动调用：

```python
import asyncio
from zentex.plugins.service import (
    SystemPluginService,
    query_all_plugins_by_operational_status,
    rehydrate_registered_plugins,
)

async def call_cognitive_plugin():
    service = SystemPluginService(db_path="plugins.db")
    rehydrate_registered_plugins(service)

    rows = query_all_plugins_by_operational_status(
        service,
        category="cognitive",
        feature_code="nine_questions.q1",
        operational_status="enabled",
        limit=20,
    )
    if not rows:
        raise RuntimeError("nine_questions.q1 capability unavailable")

    feedback = await service.execute_plugin_once(
        plugin_id=rows[0]["plugin_id"],
        task_id="task-001",
        parameters={
            "workspace_path": "/home/user/project",
            "environment": "development"
        },
        trace_id="trace-q1-001",
        originator_id="user@system"
    )

    if feedback.status == "done":
        print(f"结果: {feedback.result}")
    else:
        print(f"失败: {feedback.error}")

asyncio.run(call_cognitive_plugin())
```

---

### 2. 认知插件如何调用功能插件 / How Cognitive Plugins Call Functional Plugins

```python
from zentex.plugins.service import query_cognitive_plugin_functionals_by_operational_status

class Q3WhatDoIHavePlugin:
    def __init__(self, plugin_service):
        self.plugin_service = plugin_service
        self.plugin_id = "nine-question-q3-what-do-i-have"

    async def run_tool(self, context):
        # 查询当前认知插件下启用中的功能插件
        functional_plugins = query_cognitive_plugin_functionals_by_operational_status(
            self.plugin_service,
            cognitive_plugin_id=self.plugin_id,
            operational_status="enabled",
            limit=200,
        )

        assets = []
        for functional in functional_plugins:
            result = await self.plugin_service.execute_plugin_once(
                plugin_id=functional["plugin_id"],
                task_id=context.get("task_id"),
                parameters=context,
                trace_id=context.get("trace_id"),
                originator_id=self.plugin_id,
                caller_plugin_id=self.plugin_id,
            )
            if result.status == "done":
                assets.append(result.result)
        return {"assets": assets}
```

---

### 3. 一键激活所有功能插件 / Activate All Functional Plugins

```python
from zentex.plugins.service import SystemPluginService, rehydrate_registered_plugins

service = SystemPluginService(db_path="plugins.db")
rehydrate_registered_plugins(service)

result = service.activate_all_functional(reason="Post-deploy bulk activation")

print(f"新激活: {result['activated']}")
print(f"已激活（跳过）: {result['already_active']}")
print(f"跳过认知插件: {result['skipped_cognitive']}")
if result['failed']:
    for pid, err in result['failed'].items():
        print(f"失败 {pid}: {err}")
```

---

### 4. 安全升级功能插件 / Safe Functional Plugin Upgrade

```python
from zentex.plugins.service import SystemPluginService, rehydrate_registered_plugins
from zentex.core.plugin_base import PluginLifecycleStatus

service = SystemPluginService(db_path="plugins.db")
rehydrate_registered_plugins(service)

# 注册新版本（旧版本仍在运行）
service.register_plugin(
    plugin_id="my_plugin_v2",
    plugin_instance=new_plugin_instance,
    category="functional",
    version="2.0.0",
    behavior_key="my_behavior"  # 与旧版本相同的 behavior_key
)

# 激活新版本（蓝绿策略自动处理旧版本）
service.promote_plugin(
    plugin_id="my_plugin_v2",
    target_status=PluginLifecycleStatus.SANDBOX_VERIFIED,
    reason="Sandbox checks passed"
)
service.promote_plugin(
    plugin_id="my_plugin_v2",
    target_status=PluginLifecycleStatus.ACTIVE,
    reason="Ready for production"
)
# → 如果激活成功：my_plugin_v1 自动降级为 DEGRADED
# → 如果激活失败：my_plugin_v1 完全不受影响
```

---

### 5. 认知插件升级与激活失败处理 / Cognitive Plugin Upgrade with Failure Handling

**场景：升级认知插件时新版本激活失败**

```python
from zentex.plugins.service import SystemPluginService
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.plugins.service import query_all_plugins_by_operational_status
from zentex.plugins.service import rehydrate_registered_plugins
import logging

logger = logging.getLogger(__name__)
service = SystemPluginService(db_path="plugins.db")
rehydrate_registered_plugins(service)

# 查看当前状态
current_q1 = query_all_plugins_by_operational_status(
    service,
    category="cognitive",
    feature_code="nine_questions.q1",
    operational_status="enabled",
)
print(f"当前 Q1 版本: {current_q1}")  # 可能是 v1.0 ACTIVE

# 尝试升级到新版本 v2.0
service.register_plugin(
    plugin_id="nine-question-q1-where-am-i-v2",
    plugin_instance=new_q1_v2,
    category="cognitive",
    version="2.0.0",
    behavior_key="nine_question_q1"  # 与旧版本相同
)

try:
    # 尝试激活 v2.0
    service.promote_plugin(
        plugin_id="nine-question-q1-where-am-i-v2",
        target_status=PluginLifecycleStatus.ACTIVE,
        reason="Upgrade q1 to v2.0"
    )
    logger.info("✅ Q1 升级成功，v1.0 已自动降级")
    
except Exception as e:
    # 激活失败的情况
    logger.error(f"❌ Q1 v2.0 激活失败: {e}")
    
    # 检查 v1.0 是否仍然 ACTIVE
    fallback_q1 = query_all_plugins_by_operational_status(
        service,
        category="cognitive",
        feature_code="nine_questions.q1",
        operational_status="enabled",
    )
    if fallback_q1:
        logger.warning(f"⚠️  Q1 v1.0 仍然运行中，认知功能不中断")
    else:
        # 这不应该发生（违反常驻激活策略）
        # 系统应该发出 CRITICAL 日志
        logger.critical(
            "🚨 Q1 无任何激活版本！认知功能已离线。\n"
            "需要立即采取行动恢复。"
        )
        # → 在系统日志中应该看到 CRITICAL 告警（见下文）
```

**预期的系统行为：**
- ❌ v2.0 实例化失败 → 激活中止
- ✅ v1.0 继续运行 ACTIVE → 认知功能不中断
- ⚠️ ERROR 日志：记录 v2.0 失败原因，说明 v1.0 仍在运行
- ❌ 不停用 v1.0（激活尚未成功）

---

### 6. 处理零存活 CRITICAL 告警 / Handling Zero-Survivor CRITICAL Alert

**场景：新版本激活失败，且无旧版本可用（极端情况）**

```python
# 假设系统日志中出现了 CRITICAL 告警：
# [CRITICAL] NO ACTIVE VERSION remaining for behavior_key 'nine_question_q1' 
#            after activation failure of v2.0

# 恢复步骤：

from zentex.plugins.service import (
    SystemPluginService,
    query_all_plugins_by_lifecycle,
    query_all_plugins_by_operational_status,
    rehydrate_registered_plugins,
)
from zentex.core.plugin_base import PluginLifecycleStatus

service = SystemPluginService(db_path="plugins.db")
rehydrate_registered_plugins(service)

# Step 1: 检查所有版本的当前状态
all_q1_versions = query_all_plugins_by_lifecycle(
    service,
    category="cognitive",
    feature_code="nine_questions.q1",
    limit=50,
)
for plugin in all_q1_versions:
    print(f"{plugin['plugin_id']}: {plugin['lifecycle_status']}")
    # 输出例：
    # nine-question-q1-where-am-i: DEGRADED (failed 3+ times)
    # nine-question-q1-where-am-i-v2: CANDIDATE (activation failed)

# Step 2: 选择恢复策略

# 选项 A：如果 v1.0 可以修复
if all_q1_versions[0]["lifecycle_status"] == "degraded":
    logger.info("尝试恢复 v1.0...")
    service.promote_plugin(
        plugin_id="nine-question-q1-where-am-i",
        target_status=PluginLifecycleStatus.SANDBOX_VERIFIED,
        reason="Recovery: v2.0 failed, restoring v1.0"
    )
    service.promote_plugin(
        plugin_id="nine-question-q1-where-am-i",
        target_status=PluginLifecycleStatus.ACTIVE,
        reason="Recovery: v1.0 restored as fallback"
    )
    logger.info("✅ Q1 恢复成功，v1.0 重新激活")

# 选项 B：如果需要紧急热修复
else:
    logger.critical(
        "🚨 两个版本都无法激活！需要立即部署热修复。\n"
        "新建 v2.1 hotfix 版本并激活。"
    )
    # 部署 v2.1 hotfix
    service.register_plugin(
        plugin_id="nine-question-q1-where-am-i-v2-hotfix",
        plugin_instance=hotfix_q1_v2_1,
        category="cognitive",
        version="2.1.0",
        behavior_key="nine_question_q1"
    )
    service.promote_plugin(
        plugin_id="nine-question-q1-where-am-i-v2-hotfix",
        target_status=PluginLifecycleStatus.ACTIVE,
        reason="Hotfix: v2.0 broken, deploying v2.1"
    )
    logger.info("✅ Q1 v2.1 hotfix 已激活")

# Step 3: 验证恢复
recovered_q1 = query_all_plugins_by_operational_status(
    service,
    category="cognitive",
    feature_code="nine_questions.q1",
    operational_status="enabled",
)
if recovered_q1:
    logger.info(f"✅ 验证成功：{recovered_q1[0]['plugin_id']} 现在启用")
else:
    logger.critical("🚨 恢复失败！Q1 仍无激活版本，需要人工干预")

# Step 4: 通知监控和告警系统
# 发送恢复通知，降低警报级别
notify_monitoring_system(
    event="cognitive_plugin_recovered",
    behavior_key="nine_question_q1",
    active_version=recovered_q1[0].version,
    timestamp=datetime.now()
)
```

**关键点：**
- 📍 CRITICAL 告警中包含所有版本状态和具体错误信息
- 🔍 检查所有版本（DEGRADED、CANDIDATE、REVOKED）
- 🏥 优先尝试恢复已知可运行的版本（Option A）
- 🚀 如无可用版本，立即部署新的 hotfix 版本
- ✅ 验证恢复成功后通知监控系统
- ⏰ 同时启动根本原因分析（为什么会出现零存活）

---

## Error Handling & Status Auto-Update / 错误处理与状态自动更新

### 自动状态更新流程

```
调用插件
  │
  ├─ 执行失败 ─ 记录失败次数 ─ 第3次失败?
  │                              │
  │                              No: 继续运行（ACTIVE）
  │                              │
  │                              Yes: 自动降级为 DEGRADED
  │
  └─ 执行成功 ─ 重置失败次数 ─ 保持 ACTIVE
```

### 调用失败类型

| 失败类型 | 触发条件 | 自动状态更新 |
|---------|---------|------------|
| **plugin_not_found** | 插件未注册 | ❌ 否 |
| **plugin_not_active** | 插件状态非 ACTIVE | ❌ 否 |
| **plugin_not_instantiated** | 插件在内存中不存在 | ⚠️ 告警 |
| **execution_error** | 插件实际执行失败 | ✅ 是（3次后 DEGRADED）|
| **hierarchy_violation** | 调用约束违反 | ❌ 否 |

### 手动恢复或升级插件

```python
# 将降级的功能插件恢复为 ACTIVE
service.promote_plugin(
    plugin_id="recovered_plugin",
    target_status=PluginLifecycleStatus.ACTIVE,
    reason="Manual recovery after fix"
)

# 撤销不可靠的功能插件
service.promote_plugin(
    plugin_id="broken_plugin",
    target_status=PluginLifecycleStatus.REVOKED,
    reason="Permanently disabled due to security issue"
)

# ❌ 以下操作对认知插件无效（会被系统拦截）
service.disable_plugin("nine-question-q1-where-am-i")      # 被忽略 + WARNING
service.promote_plugin("nine-question-q1-where-am-i",
    PluginLifecycleStatus.DEGRADED, reason="test")          # 被拦截 + WARNING
```

### 日志中的关键事件

```
# 认知插件保护
WARNING  [Plugins] Blocked attempt to set nine-question-q1-... → degraded.
         Core cognitive plugins must always remain ACTIVE.

# 蓝绿激活失败（有备用）
ERROR    [Plugins] Activation of my_plugin_v2 aborted — instantiation failed.
         Currently active version(s) [my_plugin_v1] will remain running. Error: ...

# 蓝绿激活失败（无备用 + 认知插件）
CRITICAL [Plugins] CRITICAL — Cognitive plugin nine-question-q1-... failed to activate
         and NO fallback version is currently ACTIVE. The cognitive capability
         'q1_where_am_i' is OFFLINE. ACTION REQUIRED: ...

# 零存活告警
CRITICAL [Plugins] CRITICAL — NO ACTIVE VERSION REMAINING for behavior_key 'xxx'
         after stopping yyy (superseded by zzz). The cognitive capability is OFFLINE.
         ACTION REQUIRED: manually re-activate a plugin with behavior_key 'xxx'.

# 蓝绿成功替换
INFO     [Plugins] my_plugin_v2 activated. Reason: ...
INFO     [Plugins] Superseded plugin my_plugin_v1 → DEGRADED (replaced by my_plugin_v2).

# 批量激活
INFO     [Plugins] activate_all_functional complete — activated=5, already_active=3,
         skipped_cognitive=11, failed=0
```

```sql
-- 查看所有插件状态
SELECT plugin_id, category, behavior_key, status, failure_count, updated_at
FROM system_plugins
ORDER BY category, status, updated_at DESC;

-- 查找无存活版本的 behavior_key（健康检查）
SELECT behavior_key, COUNT(*) as total,
       SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_count
FROM system_plugins
WHERE behavior_key IS NOT NULL
GROUP BY behavior_key
HAVING active_count = 0;
```
