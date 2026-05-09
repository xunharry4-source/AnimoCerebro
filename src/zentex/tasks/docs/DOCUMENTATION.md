# Zentex 任务管理模块详细说明

## 目录

1. [模块概述](#模块概述)
2. [架构设计](#架构设计)
3. [核心组件](#核心组件)
4. [数据模型](#数据模型)
5. [API接口](#api接口)
6. [插件系统](#插件系统)
7. [持久化机制](#持久化机制)
8. [使用示例](#使用示例)
9. [最佳实践](#最佳实践)
10. [故障排除](#故障排除)

## 模块概述

Zentex 任务管理模块是一个企业级的任务生命周期管理系统，提供完整的任务创建、执行、监控和管理功能。该模块设计遵循以下原则：

- **模块独立性**: 作为独立的功能模块，不依赖其他业务模块
- **可扩展性**: 支持插件化扩展，可自定义任务拆解策略
- **高可用性**: 支持持久化、备份恢复和故障转移
- **标准化**: 提供统一的对外接口，便于其他模块集成

### 核心功能

- ✅ **任务生命周期管理**: 创建、执行、暂停、恢复、完成、归档
- ✅ **优先级管理**: 四级优先级系统（紧急、高、中、低）
- ✅ **依赖关系管理**: 复杂的任务依赖图和执行顺序控制
- ✅ **批量操作**: 高效的批量状态更新和任务管理
- ✅ **挂起恢复机制**: 智能的任务暂停和自动恢复
- ✅ **持久化存储**: 跨重启的任务状态保持
- ✅ **插件系统**: 可插拔的任务拆解策略
- ✅ **统一接口**: 标准化的对外服务接口

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    对外接口层 (Interface Layer)                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ TaskServiceInterface │  │ TaskManager    │  │ Plugin Manager │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    业务逻辑层 (Business Layer)                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │TaskManagementService│ │ TaskRegistry   │ │ Plugin Registry │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    数据访问层 (Data Layer)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ TaskPersistence │  │ Decomposer      │ │ Transcript Store│ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    数据模型层 (Model Layer)                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ ZentexTask      │  │ SuspendedTask   │  │ TaskContract    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **单一职责**: 每个组件只负责一个明确的功能领域
2. **依赖倒置**: 高层模块不依赖低层模块，都依赖抽象
3. **开闭原则**: 对扩展开放，对修改关闭
4. **接口隔离**: 客户端不应该依赖它不需要的接口
5. **最少知识**: 模块间通过明确的接口通信，减少耦合

## 核心组件

### 1. TaskManager (任务管理器)

高级任务管理接口，提供简化的任务操作API。

```python
class TaskManager:
    """高阶任务管理接口"""
    
    def __init__(self, transcript_store, storage_path=None, 
                 enable_persistence=True, enable_plugin_system=True):
        # 初始化各个子系统
        
    async def create_mission(self, title, content, originator_id, strategy=None):
        # 创建使命任务
        
    def get_service_interface(self):
        # 获取统一对外接口
```

### 2. TaskServiceInterface (统一服务接口)

标准化对外接口，供其他模块安全接入。

```python
class TaskServiceInterface:
    """统一的任务管理对外服务接口"""
    
    async def create_task(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务"""
        
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """获取任务"""
        
    def list_tasks(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """列出任务"""
```

### 3. TaskManagementService (核心服务)

任务管理的核心业务逻辑实现。

```python
class TaskManagementService:
    """独立任务生命周期管理器"""
    
    def __init__(self, registry, transcript_store, decomposer, persistence=None):
        # 初始化核心组件
        
    async def create_task(self, payload: Dict[str, Any]) -> ZentexTask:
        """创建任务"""
        
    def update_task_status(self, task_id: str, new_status: TaskStatus) -> ZentexTask:
        """更新任务状态"""
```

### 4. TaskPersistence (持久化层)

任务数据的持久化存储和恢复。

```python
class TaskPersistence:
    """任务持久化层"""
    
    def save_all(self, tasks, suspended_tasks, idempotency_log, interventions):
        """保存所有数据"""
        
    def load_all(self) -> Dict[str, Any]:
        """加载所有数据"""
```

### 5. Plugin Registry (插件注册中心)

管理任务拆解插件的生命周期。

```python
class TaskPluginRegistry:
    """任务插件注册中心"""
    
    def register_decomposition_plugin(self, spec: TaskDecompositionPluginSpec) -> bool:
        """注册拆解插件"""
        
    def get_decomposition_plugin(self, plugin_id: Optional[str] = None):
        """获取拆解插件"""
```

## 数据模型

### ZentexTask (核心任务模型)

```python
class ZentexTask(BaseModel):
    """Zentex任务核心模型"""
    
    # 基础信息
    task_id: str                    # 任务唯一标识
    title: str                      # 任务标题
    task_type: TaskType             # 任务类型
    status: TaskStatus              # 任务状态
    priority: TaskPriority          # 任务优先级
    
    # 层次关系
    parent_task_id: Optional[str]   # 父任务ID
    subtask_ids: List[str]          # 子任务ID列表
    depends_on: List[str]           # 依赖任务ID列表
    
    # 执行信息
    originator_id: str              # 创建者ID
    target_id: Optional[str]        # 目标执行者ID
    progress: float = 0.0           # 进度 (0.0-1.0)
    
    # 时间信息
    created_at: datetime             # 创建时间
    started_at: Optional[datetime]  # 开始时间
    completed_at: Optional[datetime] # 完成时间
    deadline: Optional[datetime]    # 截止时间
    estimated_duration: Optional[int] # 预估时长(分钟)
    
    # 扩展信息
    tags: List[str] = []            # 标签
    remarks: Optional[str]          # 备注信息
    contract: TaskContract          # 任务契约
    metadata: Dict[str, Any] = {}   # 扩展元数据
```

### TaskStatus (任务状态枚举)

```python
class TaskStatus(str, Enum):
    TODO = "todo"                    # 待处理
    IN_PROGRESS = "in_progress"       # 进行中
    BLOCKED = "blocked"               # 阻塞
    WAITING_CONFIRMATION = "waiting_confirmation"  # 等待确认
    SUSPENDED = "suspended"           # 已挂起
    DONE = "done"                     # 已完成
    FAILED = "failed"                 # 失败
    ARCHIVED = "archived"             # 已归档
```

### TaskType (任务类型枚举)

```python
class TaskType(str, Enum):
    COGNITIVE_STEP = "cognitive_step"     # 认知步骤
    AGENT_DELEGATION = "agent_delegation"   # 代理委托
    SYSTEM_ACTION = "system_action"         # 系统动作
    INTERVENTION = "intervention"           # 人工干预
    MISSION = "mission"                     # 使命任务
```

### TaskPriority (任务优先级枚举)

```python
class TaskPriority(str, Enum):
    CRITICAL = "critical"    # 紧急
    HIGH = "high"           # 高
    MEDIUM = "medium"       # 中
    LOW = "low"             # 低
```

### SuspendedTask (挂起任务模型)

```python
class SuspendedTask(BaseModel):
    """挂起任务模型"""
    
    task_id: str                           # 任务ID
    original_status: TaskStatus            # 原始状态
    suspension_reason: str                 # 挂起原因
    recovery_conditions: List[str] = []    # 恢复条件
    suspension_context: Dict[str, Any] = {} # 挂起上下文
    suspended_at: datetime                 # 挂起时间
    auto_resume_at: Optional[datetime]     # 自动恢复时间
```

## API接口

### 统一接口规范

所有API接口都遵循统一的响应格式：

```python
{
    "success": bool,           # 操作是否成功
    "data": Any,              # 成功时的数据
    "error": str,             # 失败时的错误信息
    "error_code": str,        # 错误代码
    "message": str            # 附加信息
}
```

### 核心API

#### 1. 任务创建

```python
async def create_task(self, request: Dict[str, Any]) -> Dict[str, Any]:
    """
    创建任务
    
    Args:
        request: {
            "title": str,              # 必需：任务标题
            "task_type": str,         # 必需：任务类型
            "originator_id": str,     # 必需：创建者ID
            "priority": str,          # 可选：优先级
            "deadline": str,          # 可选：截止时间
            "tags": List[str],        # 可选：标签
            "metadata": Dict[str, Any] # 可选：元数据
        }
    
    Returns:
        {
            "success": True,
            "task": ZentexTask.model_dump(),
            "message": "Task created successfully"
        }
    """
```

#### 2. 任务查询

```python
def get_task(self, task_id: str) -> Dict[str, Any]:
    """
    获取任务信息
    
    Args:
        task_id: 任务ID
    
    Returns:
        {
            "success": True,
            "task": ZentexTask.model_dump()
        }
    """
```

#### 3. 任务列表

```python
def list_tasks(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    列出任务
    
    Args:
        filters: {
            "status": str,            # 可选：状态过滤
            "priority": str,          # 可选：优先级过滤
            "tags": List[str],        # 可选：标签过滤
            "parent_task_id": str,    # 可选：父任务过滤
            "overdue_only": bool      # 可选：仅过期任务
        }
    
    Returns:
        {
            "success": True,
            "tasks": [ZentexTask.model_dump()],
            "count": int
        }
    """
```

#### 4. 状态更新

```python
def update_task_status(self, task_id: str, status: str, remarks: Optional[str] = None) -> Dict[str, Any]:
    """
    更新任务状态
    
    Args:
        task_id: 任务ID
        status: 新状态
        remarks: 备注信息
    
    Returns:
        {
            "success": True,
            "task": ZentexTask.model_dump(),
            "message": "Status updated successfully"
        }
    """
```

#### 5. 任务认领

```python
def claim_task(self, task_id: str, handler_id: str) -> Dict[str, Any]:
    """
    认领任务
    
    Args:
        task_id: 任务ID
        handler_id: 处理者ID
    
    Returns:
        {
            "success": True,
            "task": ZentexTask.model_dump(),
            "message": "Task claimed successfully"
        }
    """
```

### 高级API

#### 1. 依赖管理

```python
def add_dependency(self, task_id: str, dependency_id: str) -> Dict[str, Any]:
    """添加任务依赖"""

def remove_dependency(self, task_id: str, dependency_id: str) -> Dict[str, Any]:
    """移除任务依赖"""

def get_dependency_tree(self, task_id: str, max_depth: int = 5) -> Dict[str, Any]:
    """获取依赖树"""

def can_execute_task(self, task_id: str) -> Dict[str, Any]:
    """检查任务是否可执行"""
```

#### 2. 挂起恢复

```python
def suspend_task(self, task_id: str, reason: str, recovery_conditions: Optional[List[str]] = None, 
                auto_resume_at: Optional[str] = None) -> Dict[str, Any]:
    """挂起任务"""

def resume_task(self, task_id: str, remarks: Optional[str] = None) -> Dict[str, Any]:
    """恢复任务"""

async def check_auto_resume(self) -> Dict[str, Any]:
    """检查自动恢复"""
```

#### 3. 批量操作

```python
def bulk_update_status(self, task_ids: List[str], status: str, remarks: Optional[str] = None) -> Dict[str, Any]:
    """批量更新状态"""

def bulk_suspend(self, task_ids: List[str], reason: str, recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
    """批量挂起"""

def bulk_resume(self, task_ids: List[str], remarks: Optional[str] = None) -> Dict[str, Any]:
    """批量恢复"""
```

## 插件系统

### 插件架构

任务管理模块采用插件化架构，支持可插拔的任务拆解策略：

```
┌─────────────────────────────────────────────────────────────┐
│                    插件管理层 (Plugin Management)            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Plugin Manager  │  │ Plugin Registry│  │ Plugin Spec     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    插件实现层 (Plugin Implementation)         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Sequential       │  │ Parallel        │  │ Hybrid          │ │
│  │ Decomposer       │  │ Decomposer       │  │ Decomposer       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 内置拆解策略

#### 1. 顺序策略 (Sequential)

按照固定的阶段顺序拆解任务：
- 分析阶段 → 规划阶段 → 准备阶段 → 执行阶段 → 验证阶段 → 收尾阶段

**适用场景**: 需要严格控制执行顺序的任务

#### 2. 并行策略 (Parallel)

将任务拆分为可并行执行的子任务：
- 并行研究 → 并行设计 → 并行实现 → 并行集成

**适用场景**: 可以并行处理以提高效率的任务

#### 3. 混合策略 (Hybrid)

结合顺序和并行策略的优点：
- 串行的核心阶段 + 并行的执行阶段

**适用场景**: 复杂任务，需要平衡效率和协调

#### 4. 依赖驱动策略 (Dependency Driven)

基于任务依赖关系进行智能拆解：
- 依赖发现 → 依赖解决 → 核心执行 → 依赖验证

**适用场景**: 具有复杂依赖关系的任务

### 自定义插件开发

#### 1. 创建插件规范

```python
from zentex.tasks.decomposition_plugin import TaskDecompositionPluginSpec

class CustomDecompositionPluginSpec(TaskDecompositionPluginSpec):
    """自定义拆解插件规范"""
    
    @classmethod
    def plugin_kind(cls) -> str:
        return "task_decomposition"
```

#### 2. 实现插件逻辑

```python
from zentex.tasks.decomposition_plugin import TaskDecompositionPlugin

class CustomDecompositionPlugin(TaskDecompositionPlugin):
    """自定义拆解插件实现"""
    
    def decompose_mission(self, mission_title: str, mission_content: str, 
                         context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        # 实现自定义拆解逻辑
        subtasks = [
            {
                "local_id": "custom-step-1",
                "title": f"自定义步骤1: {mission_title}",
                "task_type": TaskType.COGNITIVE_STEP,
                "content": f"自定义处理 {mission_content}",
                "objective": "自定义目标",
                "requirements": ["需求1", "需求2"],
                "depends_on": [],
                "coordination_mode": CoordinationMode.SEQUENTIAL
            }
        ]
        return subtasks
```

#### 3. 注册插件

```python
from zentex.tasks.plugin_registry import TaskPluginRegistry

# 创建插件规范
spec = CustomDecompositionPluginSpec(
    plugin_id="custom-decomposer",
    version="1.0.0",
    feature_code="task_decomposition.custom",
    plugin_layer=PluginLayer.FUNCTIONAL,
    is_concurrency_safe=True,
    lifecycle_status=PluginLifecycleStatus.ACTIVE,
    health_status=PluginHealthStatus.HEALTHY,
    rollback_conditions=["Quality score below threshold"],
    revocation_reasons=[],
    strategy="custom",
    max_depth=5,
    min_task_size=1,
    enable_optimization=True,
    confidence_threshold=0.8
)

# 注册插件
registry = TaskPluginRegistry()
success = registry.register_decomposition_plugin(spec)
```

## 持久化机制

### 存储架构

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (Application Layer)               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ TaskManager     │  │ Auto Save       │  │ Backup Manager  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    持久化层 (Persistence Layer)              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ TaskPersistence │  │ JSON Files      │  │ Backup Files    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    存储层 (Storage Layer)                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ tasks.json       │  │ suspended.json  │  │ backup_*/       │ │
│  │ idempotency.json │  │ interventions.  │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 存储文件结构

```
task_data/
├── tasks.json              # 任务数据
├── suspended_tasks.json    # 挂起任务数据
├── idempotency.json        # 幂等性日志
├── interventions.json      # 干预记录
└── backup_YYYYMMDD_HHMMSS/  # 备份目录
    ├── tasks.json
    ├── suspended_tasks.json
    ├── idempotency.json
    └── interventions.json
```

### 持久化特性

#### 1. 原子性操作

所有数据变更都是原子性的，要么全部成功，要么全部失败。

#### 2. 自动备份

- 每次保存前自动创建备份
- 保留最近N个备份版本
- 支持手动备份和恢复

#### 3. 数据完整性

- JSON序列化/反序列化处理
- 日期时间字段自动转换
- 数据验证和错误恢复

#### 4. 性能优化

- 增量保存支持
- 批量写入优化
- 异步保存选项

### 配置选项

```python
# 创建带持久化的任务管理器
task_manager = TaskManager(
    transcript_store=store,
    storage_path="./task_data",      # 存储路径
    enable_persistence=True,         # 启用持久化
    backup_count=5,                 # 备份数量
    auto_save=True                  # 自动保存
)
```

## 使用示例

### 基础使用

```python
from zentex.tasks import TaskManager

# 1. 初始化任务管理器
task_manager = TaskManager(
    transcript_store=your_store,
    storage_path="./task_data"
)

# 2. 获取统一接口
interface = task_manager.get_service_interface()

# 3. 创建任务
result = await interface.create_task({
    "title": "数据分析",
    "task_type": "cognitive_step",
    "originator_id": "user-123",
    "priority": "high",
    "deadline": "2024-01-15T18:00:00Z"
})

if result["success"]:
    task_id = result["task"]["task_id"]
    print(f"任务创建成功: {task_id}")
else:
    print(f"任务创建失败: {result['error']}")
```

### 高级使用

```python
# 1. 创建使命任务（自动拆解）
mission_result = await task_manager.create_mission(
    title="构建推荐系统",
    content="从零开始构建机器学习推荐系统",
    originator_id="team-001",
    strategy="hybrid"  # 使用混合策略
)

# 2. 查看拆解结果
mission_id = mission_result["task_id"]
subtasks = task_manager.list_tasks({"parent_task_id": mission_id})
print(f"拆解出 {len(subtasks['tasks'])} 个子任务")

# 3. 设置依赖关系
for task in subtasks["tasks"]:
    if task["title"].startswith("数据准备"):
        await interface.add_dependency(task["task_id"], "data-collection")

# 4. 批量认领任务
ready_tasks = task_manager.get_ready_tasks()
for task in ready_tasks:
    await interface.claim_task(task.task_id, "agent-001")

# 5. 监控执行进度
stats = interface.get_task_statistics()
print(f"总任务数: {stats['statistics']['total_tasks']}")
print(f"进行中: {stats['statistics']['by_status']['in_progress']}")
print(f"已完成: {stats['statistics']['by_status']['done']}")
```

### 插件系统使用

```python
# 1. 查看可用策略
strategies = task_manager.get_available_decomposition_strategies()
print(f"可用策略: {strategies}")

# 2. 切换默认策略
task_manager.set_default_decomposition_strategy("parallel")

# 3. 使用特定策略创建任务
result = await task_manager.create_mission(
    title="并行处理任务",
    content="需要并行处理的复杂任务",
    originator_id="user-456",
    strategy="parallel"
)

# 4. 查看插件信息
plugins = task_manager.list_plugins()
for plugin in plugins:
    print(f"插件: {plugin['plugin_id']}, 策略: {plugin['strategy']}")

# 5. 获取插件统计
plugin_stats = task_manager.get_plugin_stats()
print(f"插件统计: {plugin_stats}")
```

### 挂起恢复使用

```python
# 1. 挂起任务
suspend_result = await interface.suspend_task(
    "task-123",
    reason="等待外部API恢复",
    recovery_conditions=["外部API状态正常"],
    auto_resume_at="2024-01-15T10:00:00Z"
)

# 2. 查看挂起任务
suspended = interface.get_suspended_tasks()
print(f"挂起任务数: {suspended['count']}")

# 3. 手动恢复任务
resume_result = await interface.resume_task("task-123", "条件已满足")

# 4. 检查自动恢复
auto_resumed = await task_manager.check_auto_resume()
print(f"自动恢复了 {len(auto_resumed)} 个任务")
```

## 最佳实践

### 1. 初始化配置

```python
# 推荐的生产环境配置
task_manager = TaskManager(
    transcript_store=transcript_store,
    storage_path="/data/tasks",           # 使用专用存储路径
    enable_persistence=True,              # 启用持久化
    backup_count=10,                     # 保留更多备份
    auto_save=True,                      # 自动保存
    enable_plugin_system=True            # 启用插件系统
)
```

### 2. 错误处理

```python
async def safe_create_task(interface, task_data):
    """安全创建任务"""
    try:
        result = await interface.create_task(task_data)
        
        if not result["success"]:
            # 根据错误代码处理不同错误
            if result["error_code"] == "MISSING_FIELD":
                logger.error(f"缺少必需字段: {result['error']}")
            elif result["error_code"] == "CREATION_FAILED":
                logger.error(f"创建失败: {result['error']}")
            
            return None
        
        return result["task"]
        
    except Exception as e:
        logger.error(f"创建任务异常: {e}")
        return None
```

### 3. 批量操作优化

```python
async def batch_process_tasks(interface, task_ids, new_status):
    """批量处理任务"""
    # 分批处理，避免一次性处理太多任务
    batch_size = 50
    
    for i in range(0, len(task_ids), batch_size):
        batch = task_ids[i:i + batch_size]
        result = interface.bulk_update_status(batch, new_status)
        
        if result["success"]:
            logger.info(f"批量更新成功: {result['success_count']}/{len(batch)}")
        else:
            logger.error(f"批量更新失败: {result['error']}")
        
        # 避免过于频繁的操作
        await asyncio.sleep(0.1)
```

### 4. 依赖管理

```python
def create_task_with_dependencies(interface, title, dependencies):
    """创建带依赖的任务"""
    # 首先创建任务
    result = interface.create_task({
        "title": title,
        "task_type": "cognitive_step",
        "originator_id": "system"
    })
    
    if not result["success"]:
        return None
    
    task_id = result["task"]["task_id"]
    
    # 添加依赖关系
    for dep_id in dependencies:
        dep_result = interface.add_dependency(task_id, dep_id)
        if not dep_result["success"]:
            logger.warning(f"添加依赖失败: {task_id} -> {dep_id}")
    
    return task_id
```

### 5. 监控和维护

```python
async def maintenance_task(task_manager):
    """定期维护任务"""
    # 1. 检查自动恢复
    resumed = await task_manager.check_auto_resume()
    if resumed:
        logger.info(f"自动恢复了 {len(resumed)} 个任务")
    
    # 2. 归档旧任务
    archived = task_manager.bulk_archive_completed(older_than_days=30)
    if archived["archived_count"] > 0:
        logger.info(f"归档了 {archived['archived_count']} 个已完成任务")
    
    # 3. 清理失败任务
    cleaned = task_manager.cleanup_failed_tasks(force=False)
    if cleaned["deleted_count"] > 0:
        logger.info(f"清理了 {cleaned['deleted_count']} 个失败任务")
    
    # 4. 保存状态
    saved = task_manager.save_state()
    if not saved:
        logger.error("状态保存失败")
```

## 故障排除

### 常见问题

#### 1. 任务创建失败

**问题**: `error_code": "MISSING_FIELD"`

**原因**: 缺少必需字段（title, task_type, originator_id）

**解决**: 确保请求包含所有必需字段

```python
# 正确的请求
request = {
    "title": "任务标题",           # 必需
    "task_type": "cognitive_step", # 必需
    "originator_id": "user-123",  # 必需
    "priority": "high"            # 可选
}
```

#### 2. 状态转换失败

**问题**: `error_code": "INVALID_STATE_TRANSITION"`

**原因**: 尝试非法的状态转换

**解决**: 检查状态转换规则

```python
# 合法的状态转换
legal_transitions = {
    "todo": ["in_progress", "blocked", "failed", "suspended", "archived"],
    "in_progress": ["waiting_confirmation", "blocked", "done", "failed", "suspended"],
    "suspended": ["todo", "in_progress", "blocked", "failed", "archived"]
}
```

#### 3. 依赖循环

**问题**: 添加依赖时失败

**原因**: 会创建循环依赖

**解决**: 检查依赖关系，避免循环

```python
# 检查依赖树
dep_tree = interface.get_dependency_tree("task-a")
# 分析是否存在循环
```

#### 4. 持久化失败

**问题**: 任务数据丢失

**原因**: 存储路径权限问题或磁盘空间不足

**解决**: 检查存储路径和权限

```python
# 检查持久化状态
stats = interface.get_persistence_stats()
if not stats:
    logger.error("持久化未启用或失败")
```

#### 5. 插件加载失败

**问题**: 无法使用拆解插件

**原因**: 插件未注册或状态不正确

**解决**: 检查插件注册状态

```python
# 检查插件状态
plugins = task_manager.list_plugins()
for plugin in plugins:
    if plugin["status"] != "active":
        logger.warning(f"插件 {plugin['plugin_id']} 状态异常: {plugin['status']}")
```

### 调试技巧

#### 1. 启用详细日志

```python
import logging
logging.getLogger("zentex.tasks").setLevel(logging.DEBUG)
```

#### 2. 检查任务状态

```python
# 获取详细任务信息
task_result = interface.get_task("task-id")
if task_result["success"]:
    task = task_result["task"]
    print(f"状态: {task['status']}")
    print(f"依赖: {task['depends_on']}")
    print(f"进度: {task['progress']}")
```

#### 3. 验证依赖关系

```python
# 检查是否可执行
can_execute = interface.can_execute_task("task-id")
if not can_execute["can_execute"]:
    print(f"无法执行: {can_execute['reason']}")
    print(f"未满足的依赖: {can_execute['unsatisfied_dependencies']}")
```

#### 4. 检查持久化状态

```python
# 获取存储统计
stats = interface.get_persistence_stats()
if stats:
    print(f"存储路径: {stats['persistence_stats']['storage_path']}")
    print(f"备份数量: {stats['persistence_stats']['backup_count']}")
```

### 性能优化

#### 1. 批量操作

对于大量任务，使用批量操作而不是单个操作：

```python
# 推荐：批量操作
interface.bulk_update_status(task_ids, "done")

# 不推荐：单个操作
for task_id in task_ids:
    interface.update_task_status(task_id, "done")
```

#### 2. 合理的过滤

使用过滤条件减少返回的数据量：

```python
# 推荐：精确过滤
interface.list_tasks({
    "status": "todo",
    "priority": "high",
    "overdue_only": True
})

# 不推荐：获取所有数据后过滤
all_tasks = interface.list_tasks()
filtered = [t for t in all_tasks["tasks"] if t["status"] == "todo"]
```

#### 3. 持久化优化

```python
# 对于高频操作，可以临时禁用自动保存
task_manager.service.auto_save = False

# 执行批量操作
# ...

# 手动保存
task_manager.save_state()

# 重新启用自动保存
task_manager.service.auto_save = True
```

---

## 版本历史

- **v1.0.0**: 基础任务管理功能
- **v1.1.0**: 添加优先级和依赖管理
- **v1.2.0**: 实现挂起恢复机制
- **v1.3.0**: 添加批量操作支持
- **v1.4.0**: 实现持久化机制
- **v1.5.0**: 添加插件系统和统一接口

## 联系支持

如有问题或建议，请联系开发团队或查看项目文档。
