# 任务管理模块使用指南

## 概述

Zentex 任务管理模块提供了完整的任务生命周期管理功能，包括：

- 统一的对外服务接口
- 可插拔的任务拆解系统
- 完整的持久化机制
- 高级任务操作（批量操作、依赖管理等）

## 快速开始

### 1. 基础初始化

```python
from zentex.tasks import TaskManager

# 创建任务管理器
task_manager = TaskManager(
    transcript_store=your_transcript_store,
    storage_path="./task_data",
    enable_persistence=True,
    enable_plugin_system=True
)

# 获取统一服务接口（推荐其他模块使用）
task_interface = task_manager.get_service_interface()
```

### 2. 创建任务

```python
# 创建简单任务
result = await task_interface.create_task({
    "title": "数据分析任务",
    "task_type": "cognitive_step",
    "originator_id": "user-123",
    "priority": "high",
    "remarks": "分析用户行为数据"
})

# 创建使命任务（会自动拆解）
result = await task_interface.create_mission({
    "title": "构建推荐系统",
    "content": "从零开始构建一个基于机器学习的推荐系统",
    "originator_id": "team-456",
    "strategy": "hybrid"  # 使用混合拆解策略
})
```

### 3. 任务操作

```python
# 获取任务
task_result = task_interface.get_task("task-123")

# 列出任务
tasks_result = task_interface.list_tasks({
    "status": "todo",
    "priority": "high"
})

# 更新任务状态
update_result = task_interface.update_task_status(
    "task-123", 
    "in_progress", 
    "开始执行数据分析"
)

# 认领任务
claim_result = task_interface.claim_task("task-123", "agent-789")
```

## 高级功能

### 1. 任务拆解策略

```python
# 获取可用策略
strategies = task_manager.get_available_decomposition_strategies()
print(f"可用策略: {strategies}")

# 使用特定策略创建任务
result = await task_manager.create_mission(
    title="系统重构",
    content="重构现有微服务架构",
    originator_id="architect-001",
    strategy="parallel"  # 并行策略
)

# 手动拆解任务
subtasks = task_manager.decompose_mission_with_strategy(
    title="API开发",
    content="开发RESTful API接口",
    strategy="sequential"
)
```

### 2. 依赖关系管理

```python
# 添加依赖
add_result = task_interface.add_dependency("task-b", "task-a")

# 检查是否可执行
can_execute = task_interface.can_execute_task("task-b")

# 获取依赖树
dep_tree = task_interface.get_dependency_tree("mission-001")
```

### 3. 挂起和恢复

```python
# 挂起任务
suspend_result = task_interface.suspend_task(
    "task-123",
    reason="等待外部API可用",
    recovery_conditions=["外部API恢复正常"],
    auto_resume_at="2024-01-15T10:00:00Z"
)

# 恢复任务
resume_result = task_interface.resume_task("task-123", "条件已满足")

# 检查自动恢复
resumed_tasks = await task_manager.check_auto_resume()
```

### 4. 批量操作

```python
# 批量更新状态
bulk_result = task_interface.bulk_update_status(
    ["task-1", "task-2", "task-3"],
    "done",
    "批量完成"
)

# 批量挂起
suspend_bulk = task_interface.bulk_suspend(
    ["task-4", "task-5"],
    "系统维护中"
)
```

## 插件系统

### 1. 查看插件信息

```python
# 列出所有插件
plugins = task_manager.list_plugins()

# 获取特定插件信息
plugin_info = task_manager.get_plugin_info("default-hybrid-decomposer")

# 获取插件统计
plugin_stats = task_manager.get_plugin_stats()
```

### 2. 自定义拆解插件

```python
from zentex.tasks.decomposition_plugin import TaskDecompositionPluginSpec, TaskDecompositionPlugin
from zentex.tasks.plugin_registry import TaskPluginRegistry

# 创建插件规范
custom_spec = TaskDecompositionPluginSpec(
    plugin_id="custom-ml-decomposer",
    version="1.0.0",
    feature_code="task_decomposition.ml",
    plugin_layer=PluginLayer.FUNCTIONAL,
    is_concurrency_safe=True,
    status=PluginLifecycleStatus.ACTIVE,
    health_status=PluginHealthStatus.HEALTHY,
    rollback_conditions=["Model quality below threshold"],
    revocation_reasons=[],
    strategy="hybrid",
    max_depth=4,
    min_task_size=2,
    enable_optimization=True,
    confidence_threshold=0.8
)

# 注册插件
registry = TaskPluginRegistry()
success = registry.register_decomposition_plugin(custom_spec)
```

## 统一服务接口

其他模块应该通过 `TaskServiceInterface` 接入任务管理功能：

```python
# 在其他模块中
from zentex.tasks import TaskManager

# 获取服务接口
task_manager = TaskManager(...)
task_interface = task_manager.get_service_interface()

# 使用统一接口
def process_user_request(request):
    # 创建任务
    result = task_interface.create_task({
        "title": request.title,
        "task_type": "agent_delegation",
        "originator_id": request.user_id,
        "priority": request.priority
    })
    
    if result["success"]:
        task_id = result["task"]["task_id"]
        # 认领任务
        claim_result = task_interface.claim_task(task_id, "my-agent")
        return claim_result
    else:
        return {"error": result["error"]}
```

## 监控和统计

```python
# 获取任务统计
stats = task_interface.get_task_statistics()

# 获取持久化统计
persistence_stats = task_interface.get_persistence_stats()

# 获取过期任务
overdue_tasks = task_interface.get_overdue_tasks()

# 获取就绪任务
ready_tasks = task_interface.get_ready_tasks()
```

## 最佳实践

1. **使用统一接口**: 其他模块通过 `TaskServiceInterface` 接入，避免直接依赖内部实现
2. **启用插件系统**: 利用可插拔的拆解策略提高任务处理质量
3. **启用持久化**: 确保任务状态在系统重启后能够恢复
4. **合理使用批量操作**: 对于大量任务操作，使用批量接口提高效率
5. **监控任务状态**: 定期检查任务统计和健康状态

## 错误处理

所有接口都返回标准化的结果格式：

```python
{
    "success": bool,
    "data": any,  # 成功时的数据
    "error": str,  # 失败时的错误信息
    "error_code": str,  # 错误代码
    "message": str  # 附加信息
}
```

建议在调用接口时检查 `success` 字段并处理错误情况。
