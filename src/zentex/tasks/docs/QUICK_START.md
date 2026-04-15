# Zentex 任务管理模块 - 快速入门指南

## 5分钟快速开始

### 第1步：安装和导入

```python
from zentex.tasks import TaskManager
```

### 第2步：创建任务管理器

```python
# 基础配置
task_manager = TaskManager(
    transcript_store=your_transcript_store,  # 必需：审计存储
    storage_path="./my_tasks",              # 可选：存储路径
    enable_persistence=True,                # 可选：启用持久化
    enable_plugin_system=True               # 可选：启用插件系统
)
```

### 第3步：获取统一接口

```python
# 获取标准化接口（推荐其他模块使用）
task_interface = task_manager.get_service_interface()
```

### 第4步：创建第一个任务

```python
# 创建简单任务
result = await task_interface.create_task({
    "title": "我的第一个任务",
    "task_type": "cognitive_step",
    "originator_id": "user-001",
    "priority": "high"
})

if result["success"]:
    task_id = result["task"]["task_id"]
    print(f"✅ 任务创建成功: {task_id}")
else:
    print(f"❌ 创建失败: {result['error']}")
```

### 第5步：管理任务

```python
# 查看任务
task_info = task_interface.get_task(task_id)
print(f"任务状态: {task_info['task']['status']}")

# 更新状态
task_interface.update_task_status(task_id, "in_progress", "开始执行")

# 认领任务
task_interface.claim_task(task_id, "agent-001")

# 完成任务
task_interface.update_task_status(task_id, "done", "任务完成")
```

## 核心概念

### 任务类型

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `cognitive_step` | 认知步骤 | 思考、分析、决策 |
| `agent_delegation` | 代理委托 | 委托给其他Agent执行 |
| `system_action` | 系统动作 | 文件操作、API调用 |
| `intervention` | 人工干预 | 需要人工确认 |
| `mission` | 使命任务 | 复杂任务，会自动拆解 |

### 任务状态

```
todo → in_progress → done
  ↓         ↓         ↓
suspended → blocked → failed
  ↓         ↓         ↓
         archived
```

### 优先级

- 🚨 **critical**: 紧急，立即处理
- 🔥 **high**: 高优先级，尽快处理  
- ⚡ **medium**: 中等优先级，正常处理
- 📝 **low**: 低优先级，有空时处理

## 常用操作

### 1. 创建使命任务（推荐）

使命任务会自动拆解为子任务：

```python
mission_result = await task_manager.create_mission(
    title="构建网站",
    content="从零开始构建一个响应式网站",
    originator_id="team-001",
    strategy="hybrid"  # 使用混合策略
)

print(f"使命任务ID: {mission_result['task']['task_id']}")

# 查看自动生成的子任务
subtasks = task_manager.list_tasks({"parent_task_id": mission_result['task']['task_id']})
print(f"自动拆解出 {subtasks['count']} 个子任务")
```

### 2. 批量操作

```python
# 获取所有待处理任务
todo_tasks = task_interface.list_tasks({"status": "todo"})
task_ids = [task["task_id"] for task in todo_tasks["tasks"]]

# 批量认领
if task_ids:
    result = task_interface.bulk_update_status(task_ids, "in_progress", "批量开始处理")
    print(f"批量更新成功: {result['success_count']}/{len(task_ids)}")
```

### 3. 依赖管理

```python
# 创建有依赖的任务
task_a = await task_interface.create_task({
    "title": "数据收集",
    "task_type": "system_action",
    "originator_id": "system"
})

task_b = await task_interface.create_task({
    "title": "数据分析",
    "task_type": "cognitive_step", 
    "originator_id": "system"
})

# 设置依赖：B依赖于A
task_interface.add_dependency(task_b["task"]["task_id"], task_a["task"]["task_id"])

# 检查是否可执行
can_execute = task_interface.can_execute_task(task_b["task"]["task_id"])
print(f"任务B可执行: {can_execute['can_execute']}")
```

### 4. 挂起和恢复

```python
# 挂起任务
task_interface.suspend_task(
    task_id="task-123",
    reason="等待外部API恢复",
    recovery_conditions=["外部API状态正常"],
    auto_resume_at="2024-01-15T10:00:00Z"
)

# 查看挂起任务
suspended = task_interface.get_suspended_tasks()
print(f"当前挂起任务数: {suspended['count']}")

# 手动恢复
task_interface.resume_task("task-123", "条件已满足")

# 检查自动恢复
auto_resumed = await task_manager.check_auto_resume()
print(f"自动恢复了 {len(auto_resumed)} 个任务")
```

## 插件系统

### 查看可用策略

```python
strategies = task_manager.get_available_decomposition_strategies()
print(f"可用拆解策略: {strategies}")
# 输出: ['sequential', 'parallel', 'hybrid', 'dependency_driven']
```

### 使用不同策略

```python
# 顺序策略：按步骤执行
await task_manager.create_mission(
    title="顺序任务",
    content="需要严格按顺序执行的任务",
    originator_id="user-001",
    strategy="sequential"
)

# 并行策略：可并行执行
await task_manager.create_mission(
    title="并行任务", 
    content="可以并行处理的任务",
    originator_id="user-001",
    strategy="parallel"
)

# 混合策略：平衡效率和控制
await task_manager.create_mission(
    title="复杂任务",
    content="需要平衡效率和控制的复杂任务", 
    originator_id="user-001",
    strategy="hybrid"
)
```

### 查看插件信息

```python
# 列出所有插件
plugins = task_manager.list_plugins()
for plugin in plugins["plugins"]:
    print(f"插件: {plugin['plugin_id']}")
    print(f"策略: {plugin['strategy']}")
    print(f"状态: {plugin['status']}")
    print(f"是否默认: {plugin['is_default']}")
    print("---")

# 获取插件统计
stats = task_manager.get_plugin_stats()
print(f"插件统计: {stats}")
```

## 监控和统计

### 任务统计

```python
# 获取统计信息
stats = task_interface.get_task_statistics()
statistics = stats["statistics"]

print(f"总任务数: {statistics['total_tasks']}")
print(f"按状态分布: {statistics['by_status']}")
print(f"按优先级分布: {statistics['by_priority']}")
print(f"过期任务数: {statistics['overdue_count']}")
print(f"挂起任务数: {statistics['suspended_count']}")
print(f"准备就绪任务数: {statistics['ready_to_execute']}")
```

### 过期任务

```python
# 获取所有过期任务
overdue = task_interface.get_overdue_tasks()
print(f"过期任务数: {overdue['count']}")

for task in overdue["tasks"]:
    print(f"⚠️  {task['title']} (截止: {task['deadline']})")
```

### 就绪任务

```python
# 获取可以执行的任务
ready = task_interface.get_ready_tasks()
print(f"就绪任务数: {ready['count']}")

for task in ready["tasks"]:
    print(f"✅ {task['title']} (优先级: {task['priority']})")
```

## 实际使用场景

### 场景1：数据处理管道

```python
async def create_data_pipeline():
    """创建数据处理管道"""
    
    # 创建使命任务（自动拆解）
    pipeline = await task_manager.create_mission(
        title="数据处理管道",
        content="从数据收集到最终分析的完整管道",
        originator_id="data-team",
        strategy="sequential"
    )
    
    # 获取子任务
    subtasks = task_manager.list_tasks({
        "parent_task_id": pipeline["task"]["task_id"]
    })
    
    # 按顺序执行
    for task in subtasks["tasks"]:
        task_id = task["task_id"]
        
        # 检查依赖
        can_execute = task_interface.can_execute_task(task_id)
        if not can_execute["can_execute"]:
            print(f"⏳ 等待依赖: {can_execute['reason']}")
            continue
        
        # 认领并执行
        task_interface.claim_task(task_id, "data-processor")
        task_interface.update_task_status(task_id, "in_progress")
        
        # 模拟执行
        await asyncio.sleep(1)
        
        # 完成
        task_interface.update_task_status(task_id, "done")
        print(f"✅ 完成: {task['title']}")
```

### 场景2：多Agent协作

```python
async def multi_agent_collaboration():
    """多Agent协作示例"""
    
    # 创建协作任务
    mission = await task_manager.create_mission(
        title="系统重构",
        content="重构微服务架构",
        originator_id="architect-team",
        strategy="parallel"  # 并行执行
    )
    
    # 获取子任务
    subtasks = task_manager.list_tasks({
        "parent_task_id": mission["task"]["task_id"]
    })
    
    # 不同Agent认领不同任务
    agent_mapping = {
        "frontend-developer": ["前端重构", "UI优化"],
        "backend-developer": ["API重构", "数据库优化"],
        "devops-engineer": ["部署配置", "监控设置"]
    }
    
    for task in subtasks["tasks"]:
        task_title = task["title"]
        
        # 根据任务类型分配给合适的Agent
        for agent, keywords in agent_mapping.items():
            if any(keyword in task_title for keyword in keywords):
                task_interface.claim_task(task["task_id"], agent)
                print(f"👥 {agent} 认领任务: {task_title}")
                break
```

### 场景3：智能任务调度

```python
async def intelligent_scheduling():
    """智能任务调度"""
    
    # 获取所有就绪任务
    ready_tasks = task_interface.get_ready_tasks()
    
    # 按优先级排序
    priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    sorted_tasks = sorted(
        ready_tasks["tasks"],
        key=lambda t: priority_order.get(t["priority"], 0),
        reverse=True
    )
    
    # 智能分配
    for task in sorted_tasks[:5]:  # 限制并发数
        task_id = task["task_id"]
        
        # 检查资源可用性
        if is_resource_available():
            task_interface.claim_task(task_id, "auto-scheduler")
            task_interface.update_task_status(task_id, "in_progress")
            print(f"🤖 自动调度: {task['title']} (优先级: {task['priority']})")
```

## 错误处理

### 标准错误处理模式

```python
async def safe_task_operation():
    """安全的任务操作示例"""
    
    try:
        # 创建任务
        result = await task_interface.create_task({
            "title": "测试任务",
            "task_type": "cognitive_step",
            "originator_id": "user-001"
        })
        
        if not result["success"]:
            # 根据错误代码处理
            error_code = result["error_code"]
            
            if error_code == "MISSING_FIELD":
                print("❌ 缺少必需字段")
            elif error_code == "INVALID_TASK_TYPE":
                print("❌ 无效的任务类型")
            else:
                print(f"❌ 未知错误: {result['error']}")
            
            return None
        
        task_id = result["task"]["task_id"]
        
        # 更新状态
        update_result = task_interface.update_task_status(task_id, "in_progress")
        if not update_result["success"]:
            print(f"❌ 状态更新失败: {update_result['error']}")
            return None
        
        print(f"✅ 任务操作成功: {task_id}")
        return task_id
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        return None
```

### 常见错误和解决方案

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `MISSING_FIELD` | 缺少必需字段 | 确保包含 title, task_type, originator_id |
| `INVALID_STATE_TRANSITION` | 非法状态转换 | 检查当前状态，遵循状态转换规则 |
| `DEPENDENCY_NOT_MET` | 依赖未满足 | 先完成依赖任务 |
| `CIRCULAR_DEPENDENCY` | 循环依赖 | 重新设计依赖关系 |
| `TASK_NOT_FOUND` | 任务不存在 | 检查任务ID是否正确 |

## 最佳实践

### 1. 使用统一接口

```python
# ✅ 推荐：使用统一接口
task_interface = task_manager.get_service_interface()
result = await task_interface.create_task({...})

# ❌ 不推荐：直接使用内部实现
result = await task_manager.service.create_task({...})
```

### 2. 启用持久化

```python
# ✅ 推荐：启用持久化
task_manager = TaskManager(
    transcript_store=store,
    enable_persistence=True,
    storage_path="./data/tasks"
)
```

### 3. 合理使用优先级

```python
# ✅ 推荐：根据紧急程度设置优先级
priority_mapping = {
    "紧急修复": "critical",
    "功能开发": "high", 
    "优化改进": "medium",
    "文档更新": "low"
}
```

### 4. 批量操作优化

```python
# ✅ 推荐：批量操作
task_ids = [t["task_id"] for t in tasks]
result = task_interface.bulk_update_status(task_ids, "done")

# ❌ 不推荐：循环单个操作
for task_id in task_ids:
    task_interface.update_task_status(task_id, "done")
```

### 5. 错误处理

```python
# ✅ 推荐：完整错误处理
if result["success"]:
    # 处理成功结果
    pass
else:
    # 根据错误代码处理
    handle_error(result["error_code"], result["error"])
```

## 下一步

### 📚 深入学习

- 查看 [详细文档](DOCUMENTATION.md) 了解完整功能
- 查看 [API参考](API_REFERENCE.md) 了解所有接口
- 查看 [使用指南](README.md) 了解更多示例

### 🚀 进阶功能

- 自定义任务拆解插件
- 复杂依赖关系管理
- 任务模板和复用
- 与其他模块集成

### 🛠️ 开发和扩展

- 贡献代码和插件
- 报告问题和建议
- 参与社区讨论

---

## 快速参考

### 常用方法

```python
# 创建任务
await task_interface.create_task({...})

# 获取任务
task_interface.get_task(task_id)

# 列出任务
task_interface.list_tasks({...})

# 更新状态
task_interface.update_task_status(task_id, "done")

# 认领任务
task_interface.claim_task(task_id, "agent-id")

# 批量操作
task_interface.bulk_update_status(task_ids, "done")

# 获取统计
task_interface.get_task_statistics()
```

### 常用状态

```python
# 状态流转
todo → in_progress → done
     ↓         ↓
suspended → blocked → failed
```

### 常用优先级

```python
priority_levels = {
    "critical": 4,  # 🚨 紧急
    "high": 3,      # 🔥 高
    "medium": 2,    # ⚡ 中
    "low": 1        # 📝 低
}
```

---

💡 **提示**: 这个快速入门指南涵盖了最常用的功能。如需了解完整功能，请查看详细文档。

🎯 **目标**: 通过这个指南，你应该能够在5分钟内开始使用Zentex任务管理模块！
