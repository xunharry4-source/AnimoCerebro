# Zentex 任务管理 API 参考

## 概述

本文档提供了 Zentex 任务管理模块的完整 API 参考。所有 API 都通过 `TaskServiceInterface` 统一接口提供。

## 基础信息

- **基础URL**: 无（本地接口调用）
- **认证**: 通过调用方上下文管理
- **格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

所有 API 响应都遵循统一格式：

```json
{
    "success": boolean,
    "data": any,
    "error": string,
    "error_code": string,
    "message": string
}
```

## 任务管理 API

### 任务创建

#### `POST /create_task`

创建新任务。

**请求体**:
```json
{
    "title": "string",              // 必需，任务标题
    "task_type": "string",         // 必需，任务类型
    "originator_id": "string",     // 必需，创建者ID
    "priority": "string",          // 可选，优先级 (critical/high/medium/low)
    "deadline": "string",          // 可选，截止时间 (ISO 8601)
    "estimated_duration": "number", // 可选，预估时长(分钟)
    "tags": ["string"],            // 可选，标签列表
    "remarks": "string",           // 可选，备注信息
    "metadata": {}                 // 可选，扩展元数据
}
```

**响应示例**:
```json
{
    "success": true,
    "task": {
        "task_id": "abc123",
        "title": "数据分析任务",
        "task_type": "cognitive_step",
        "status": "todo",
        "priority": "high",
        "created_at": "2024-01-01T10:00:00Z",
        // ... 其他字段
    },
    "message": "Task abc123 created successfully"
}
```

**错误代码**:
- `MISSING_FIELD`: 缺少必需字段
- `INVALID_TASK_TYPE`: 无效的任务类型
- `CREATION_FAILED`: 创建失败

### 任务查询

#### `GET /get_task/{task_id}`

获取指定任务的详细信息。

**路径参数**:
- `task_id`: 任务ID

**响应示例**:
```json
{
    "success": true,
    "task": {
        "task_id": "abc123",
        "title": "数据分析任务",
        // ... 完整任务信息
    }
}
```

**错误代码**:
- `NOT_FOUND`: 任务不存在
- `RETRIEVAL_FAILED`: 检索失败

#### `GET /list_tasks`

列出任务，支持过滤。

**查询参数**:
```json
{
    "status": "string",            // 可选，任务状态过滤
    "priority": "string",          // 可选，优先级过滤
    "tags": ["string"],            // 可选，标签过滤
    "parent_task_id": "string",    // 可选，父任务过滤
    "overdue_only": boolean        // 可选，仅过期任务
}
```

**响应示例**:
```json
{
    "success": true,
    "tasks": [
        {
            "task_id": "abc123",
            "title": "数据分析任务",
            // ... 任务信息
        }
    ],
    "count": 1
}
```

### 任务状态管理

#### `PUT /update_task_status/{task_id}`

更新任务状态。

**路径参数**:
- `task_id`: 任务ID

**请求体**:
```json
{
    "status": "string",      // 必需，新状态
    "remarks": "string"      // 可选，备注信息
}
```

**有效状态**:
- `todo`: 待处理
- `in_progress`: 进行中
- `blocked`: 阻塞
- `waiting_confirmation`: 等待确认
- `suspended`: 已挂起
- `done`: 已完成
- `failed`: 失败
- `archived`: 已归档

**错误代码**:
- `INVALID_STATUS`: 无效状态
- `INVALID_STATE_TRANSITION`: 非法状态转换
- `UPDATE_FAILED`: 更新失败

#### `PUT /claim_task/{task_id}`

认领任务。

**路径参数**:
- `task_id`: 任务ID

**请求体**:
```json
{
    "handler_id": "string"   // 必需，处理者ID
}
```

**错误代码**:
- `CLAIM_FAILED`: 认领失败
- `DEPENDENCY_NOT_MET`: 依赖未满足

## 优先级管理 API

### `PUT /set_task_priority/{task_id}`

设置任务优先级。

**请求体**:
```json
{
    "priority": "string"     // 必需，优先级 (critical/high/medium/low)
}
```

### `PUT /set_task_deadline/{task_id}`

设置任务截止时间。

**请求体**:
```json
{
    "deadline": "string"     // 必需，截止时间 (ISO 8601)
}
```

### `GET /get_overdue_tasks`

获取所有过期任务。

**响应示例**:
```json
{
    "success": true,
    "tasks": [...],
    "count": 5
}
```

## 挂起恢复 API

### `PUT /suspend_task/{task_id}`

挂起任务。

**请求体**:
```json
{
    "reason": "string",                    // 必需，挂起原因
    "recovery_conditions": ["string"],     // 可选，恢复条件
    "auto_resume_at": "string"             // 可选，自动恢复时间
}
```

### `PUT /resume_task/{task_id}`

恢复挂起的任务。

**请求体**:
```json
{
    "remarks": "string"      // 可选，备注信息
}
```

### `GET /get_suspended_tasks`

获取所有挂起任务。

**响应示例**:
```json
{
    "success": true,
    "suspended_tasks": [...],
    "count": 3
}
```

### `POST /check_auto_resume`

检查并执行自动恢复。

**响应示例**:
```json
{
    "success": true,
    "resumed_tasks": [...],
    "count": 2,
    "message": "Auto-resumed 2 tasks"
}
```

## 依赖管理 API

### `PUT /add_dependency/{task_id}`

添加任务依赖。

**请求体**:
```json
{
    "dependency_id": "string"  // 必需，依赖任务ID
}
```

### `PUT /remove_dependency/{task_id}`

移除任务依赖。

**请求体**:
```json
{
    "dependency_id": "string"  // 必需，依赖任务ID
}
```

### `GET /get_dependency_tree/{task_id}`

获取任务依赖树。

**查询参数**:
- `max_depth`: 最大深度 (默认: 5)

**响应示例**:
```json
{
    "success": true,
    "dependency_tree": {
        "task_id": "abc123",
        "title": "主任务",
        "dependencies": [...]
    }
}
```

### `GET /can_execute_task/{task_id}`

检查任务是否可执行。

**响应示例**:
```json
{
    "success": true,
    "can_execute": true,
    "reason": "All dependencies satisfied",
    "dependencies_satisfied": true,
    "unsatisfied_dependencies": []
}
```

### `GET /get_ready_tasks`

获取准备就绪的任务。

**响应示例**:
```json
{
    "success": true,
    "ready_tasks": [...],
    "count": 8
}
```

## 批量操作 API

### `PUT /bulk_update_status`

批量更新任务状态。

**请求体**:
```json
{
    "task_ids": ["string"],   // 必需，任务ID列表
    "status": "string",       // 必需，新状态
    "remarks": "string"       // 可选，备注信息
}
```

**响应示例**:
```json
{
    "success": true,
    "results": {
        "success": [
            {"task_id": "abc123", "previous_status": "todo", "new_status": "done"}
        ],
        "failed": [
            {"task_id": "def456", "error": "Invalid state transition"}
        ]
    },
    "success_count": 1,
    "failed_count": 1
}
```

### `PUT /bulk_suspend`

批量挂起任务。

**请求体**:
```json
{
    "task_ids": ["string"],           // 必需，任务ID列表
    "reason": "string",               // 必需，挂起原因
    "recovery_conditions": ["string"] // 可选，恢复条件
}
```

### `PUT /bulk_resume`

批量恢复任务。

**请求体**:
```json
{
    "task_ids": ["string"],   // 必需，任务ID列表
    "remarks": "string"       // 可选，备注信息
}
```

### `PUT /bulk_archive_completed`

批量归档已完成任务。

**请求体**:
```json
{
    "older_than_days": 7      // 可选，归档多少天前的任务 (默认: 7)
}
```

## 干预操作 API

### `POST /intervene_task/{task_id}`

对任务进行干预操作。

**请求体**:
```json
{
    "action": "string",           // 必需，干预动作
    "idempotency_key": "string",  // 必需，幂等键
    "remarks": "string",          // 可选，备注信息
    "operator_id": "string"       // 可选，操作者ID (默认: "web-console-operator")
}
```

**有效动作**:
- `pause`: 暂停
- `resume`: 恢复
- `approve`: 批准
- `reject`: 拒绝
- `suspend`: 挂起
- `archive`: 归档

## 统计监控 API

### `GET /get_task_statistics`

获取任务统计信息。

**响应示例**:
```json
{
    "success": true,
    "statistics": {
        "total_tasks": 100,
        "by_status": {
            "todo": 20,
            "in_progress": 15,
            "done": 60,
            "failed": 5
        },
        "by_priority": {
            "critical": 10,
            "high": 30,
            "medium": 40,
            "low": 20
        },
        "overdue_count": 3,
        "suspended_count": 2,
        "ready_to_execute": 18
    }
}
```

### `GET /get_persistence_stats`

获取持久化统计信息。

**响应示例**:
```json
{
    "success": true,
    "persistence_stats": {
        "storage_path": "/data/tasks",
        "tasks_file_exists": true,
        "backup_count": 5,
        "tasks_size_bytes": 1024000
    }
}
```

### `POST /save_state`

手动保存当前状态。

**响应示例**:
```json
{
    "success": true,
    "message": "State saved successfully"
}
```

## 清理操作 API

### `POST /cleanup_failed_tasks`

清理失败任务。

**请求体**:
```json
{
    "force": boolean          // 可选，是否强制删除 (默认: false)
}
```

## 插件系统 API

### `GET /get_available_strategies`

获取可用的任务拆解策略。

**响应示例**:
```json
{
    "success": true,
    "strategies": ["sequential", "parallel", "hybrid", "dependency_driven"]
}
```

### `GET /get_plugin_info/{plugin_id}`

获取插件信息。

**响应示例**:
```json
{
    "success": true,
    "plugin": {
        "plugin_id": "default-hybrid-decomposer",
        "version": "1.0.0",
        "strategy": "hybrid",
        "status": "active",
        "configuration": {
            "max_depth": 6,
            "min_task_size": 1,
            "enable_optimization": true
        },
        "health": {
            "status": "healthy",
            "last_check": "2024-01-01T10:00:00Z"
        },
        "is_default": true
    }
}
```

### `GET /list_plugins`

列出所有插件。

**响应示例**:
```json
{
    "success": true,
    "plugins": [
        {
            "plugin_id": "default-sequential-decomposer",
            "version": "1.0.0",
            "status": "active",
            "strategy": "sequential",
            "is_default": false
        }
    ]
}
```

### `PUT /set_default_strategy`

设置默认拆解策略。

**请求体**:
```json
{
    "strategy": "string"      // 必需，策略名称
}
```

## 数据模型

### ZentexTask

```json
{
    "task_id": "string",              // 任务ID
    "parent_task_id": "string",      // 父任务ID
    "subtask_ids": ["string"],       // 子任务ID列表
    "depends_on": ["string"],        // 依赖任务ID列表
    "bundle_id": "string",           // 捆绑ID
    "subtask_id": "string",          // 子任务ID
    "idempotency_key": "string",     // 幂等键
    "title": "string",               // 标题
    "task_type": "string",           // 任务类型
    "status": "string",              // 状态
    "priority": "string",            // 优先级
    "progress": 0.0,                // 进度 (0.0-1.0)
    "originator_id": "string",       // 创建者ID
    "target_id": "string",           // 目标执行者ID
    "remarks": "string",             // 备注信息
    "started_at": "string",          // 开始时间
    "completed_at": "string",        // 完成时间
    "deadline": "string",            // 截止时间
    "estimated_duration": 60,        // 预估时长(分钟)
    "tags": ["string"],              // 标签
    "contract": {},                  // 任务契约
    "metadata": {},                  // 扩展元数据
    "last_updated_at": "string",     // 最后更新时间
    "created_at": "string"           // 创建时间
}
```

### SuspendedTask

```json
{
    "task_id": "string",                  // 任务ID
    "original_status": "string",          // 原始状态
    "suspension_reason": "string",         // 挂起原因
    "recovery_conditions": ["string"],    // 恢复条件
    "suspension_context": {},              // 挂起上下文
    "suspended_at": "string",             // 挂起时间
    "auto_resume_at": "string"            // 自动恢复时间
}
```

## 枚举值

### TaskType

- `cognitive_step`: 认知步骤
- `agent_delegation`: 代理委托
- `system_action`: 系统动作
- `intervention`: 人工干预
- `mission`: 使命任务

### TaskStatus

- `todo`: 待处理
- `in_progress`: 进行中
- `blocked`: 阻塞
- `waiting_confirmation`: 等待确认
- `suspended`: 已挂起
- `done`: 已完成
- `failed`: 失败
- `archived`: 已归档

### TaskPriority

- `critical`: 紧急
- `high`: 高
- `medium`: 中
- `low`: 低

### CoordinationMode

- `parallel`: 并行
- `bundle`: 捆绑
- `sequential`: 顺序

## 错误代码

| 错误代码 | 描述 | 解决方案 |
|---------|------|----------|
| `MISSING_FIELD` | 缺少必需字段 | 检查请求参数 |
| `INVALID_TASK_TYPE` | 无效的任务类型 | 使用有效的任务类型 |
| `INVALID_STATUS` | 无效状态 | 使用有效的状态值 |
| `INVALID_PRIORITY` | 无效优先级 | 使用有效的优先级 |
| `INVALID_DEADLINE` | 无效截止时间 | 使用ISO 8601格式 |
| `INVALID_STATE_TRANSITION` | 非法状态转换 | 检查状态转换规则 |
| `NOT_FOUND` | 资源不存在 | 检查ID是否正确 |
| `DEPENDENCY_NOT_MET` | 依赖未满足 | 先完成依赖任务 |
| `CIRCULAR_DEPENDENCY` | 循环依赖 | 重新设计依赖关系 |
| `CREATION_FAILED` | 创建失败 | 检查输入参数 |
| `UPDATE_FAILED` | 更新失败 | 检查任务状态 |
| `CLAIM_FAILED` | 认领失败 | 检查依赖和权限 |
| `SUSPEND_FAILED` | 挂起失败 | 检查任务状态 |
| `RESUME_FAILED` | 恢复失败 | 检查挂起状态 |
| `DEPENDENCY_ADD_FAILED` | 添加依赖失败 | 检查循环依赖 |
| `DEPENDENCY_REMOVE_FAILED` | 移除依赖失败 | 检查依赖关系 |
| `BULK_UPDATE_FAILED` | 批量更新失败 | 检查任务列表 |
| `BULK_SUSPEND_FAILED` | 批量挂起失败 | 检查任务状态 |
| `BULK_RESUME_FAILED` | 批量恢复失败 | 检查挂起状态 |
| `INTERVENTION_FAILED` | 干预失败 | 检查权限和状态 |
| `STATISTICS_FAILED` | 统计失败 | 检查系统状态 |
| `SAVE_STATE_FAILED` | 保存失败 | 检查存储权限 |
| `CLEANUP_FAILED` | 清理失败 | 检查任务状态 |

## 使用示例

### Python 客户端

```python
from zentex.tasks import TaskManager

# 初始化
manager = TaskManager(transcript_store=store)
interface = manager.get_service_interface()

# 创建任务
result = await interface.create_task({
    "title": "数据分析",
    "task_type": "cognitive_step",
    "originator_id": "user-123",
    "priority": "high"
})

# 检查结果
if result["success"]:
    task_id = result["task"]["task_id"]
    print(f"任务创建成功: {task_id}")
else:
    print(f"错误: {result['error']} ({result['error_code']})")
```

### 错误处理

```python
async def safe_create_task(interface, task_data):
    try:
        result = await interface.create_task(task_data)
        
        if not result["success"]:
            error_handlers = {
                "MISSING_FIELD": lambda: logger.error("缺少必需字段"),
                "INVALID_TASK_TYPE": lambda: logger.error("无效任务类型"),
                "CREATION_FAILED": lambda: logger.error("创建失败")
            }
            
            handler = error_handlers.get(result["error_code"])
            if handler:
                handler()
            else:
                logger.error(f"未知错误: {result['error']}")
            
            return None
        
        return result["task"]
        
    except Exception as e:
        logger.error(f"异常: {e}")
        return None
```

---

## 版本信息

- **当前版本**: v1.5.0
- **最后更新**: 2024-01-01
- **兼容性**: Python 3.8+

## 支持

如有问题，请查看详细文档或联系开发团队。
