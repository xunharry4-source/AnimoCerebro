# AI 监督与验证系统 (AI Supervision & Verification System)

## 概述

本系统为 AnimoCerebro 提供全面的 AI 执行监督和验证能力，确保 AI 代理人类执行任务时能够被实时监控、验证和干预。

### 核心功能

1. **实时执行监控** - 跟踪所有 AI 执行的行动和任务
2. **自动化验证** - 基于规则的检查确保合规性
3. **人工干预** - 允许人类监督员在需要时介入
4. **审计追踪** - 完整的执行历史记录和警报系统
5. **可配置监督级别** - 从最小到关键的多级监督强度

## 架构组件

### 1. AISupervisor (核心监督引擎)

负责监控和验证 AI 执行的核心引擎。

**主要特性:**
- 可配置的监督规则系统
- 实时执行记录跟踪
- 自动验证检查
- 警报生成和管理

```python
from zentex.supervision.ai_supervisor import AISupervisor, SupervisionLevel

# 初始化监督器
supervisor = AISupervisor(supervision_level=SupervisionLevel.STRICT)

# 开始监控执行
record = supervisor.start_monitoring(
    task_id="task-123",
    action_type="file_operation",
    parameters={"path": "/data/file.txt", "operation": "read"}
)

# 更新执行状态
supervisor.update_execution(record.record_id, "completed", result={"status": "success"})
```

### 2. TaskSupervisor (任务级监督)

专门用于监督任务执行的组件，与现有任务管理系统集成。

```python
from zentex.supervision.ai_supervisor import TaskSupervisor, get_ai_supervisor

task_supervisor = TaskSupervisor(get_ai_supervisor())

# 监督任务执行
record = task_supervisor.supervise_task_execution(
    task_id="task-456",
    action_type="data_processing",
    parameters={"dataset": "sales_data", "operation": "analyze"}
)

# 完成任务监督
task_supervisor.complete_task_supervision(task_id="task-456", success=True)
```

### 3. SupervisedTaskManager (集成管理器)

将监督系统与现有 TaskManagementService 集成的包装器。

```python
from zentex.supervision.integration import create_supervised_task_manager
from zentex.tasks.service import TaskManagementService

# 创建监督管理器
supervised_manager = create_supervised_task_manager(
    task_service=task_service,
    supervision_level=SupervisionLevel.STRICT
)

# 创建并监督任务
task = await supervised_manager.create_and_supervise_task({
    "title": "Process Data",
    "task_type": "MISSION",
    "priority": "HIGH"
})

# 在监督下执行任务
result = await supervised_manager.execute_task_with_supervision(
    task_id=task.task_id,
    execution_function=my_task_function,
    arg1="value1"
)
```

### 4. SupervisionService (统一服务接口)

`SupervisionService` 是监督模块对外部系统（如 Web 控制台、其他微服务）的主要联系点。它封装了核心监督引擎和任务级监督的功能，提供了一套简洁、一致的 API。

**代码示例:**

```python
from zentex.supervision.service import SupervisionService, InterventionRequest

# 初始化服务
service = SupervisionService()

# 获取系统摘要
status = service.get_system_status()
print(f"当前监督级别: {status['supervision_level']}")

# 执行人工干预
intervention = InterventionRequest(
    task_id="task-123",
    action="approve",
    reason="安全审查通过",
    operator_id="admin-001"
)
result = service.perform_intervention(intervention)

# 管理规则
service.update_rule_status("resource_limits", enabled=False)
```

**方法与参数详细说明:**

| 方法 | 参数要求 | 返回类型 | 功能描述 |
|------|----------|----------|----------|
| `get_system_status()` | 无 | `Dict` | 返回执行统计（总计、运行中、成功、失败等）和系统状态。 |
| `list_active_alerts(severity)` | `severity`: 严重程度字符串 (可选) | `List` | 获取所有尚未确认的警报，可按严重程度过滤。 |
| `acknowledge_alert(alert_id)` | `alert_id`: 警报唯一 ID | `bool` | 将特定警报标记为已处理。 |
| `get_execution_records(...)` | `task_id`, `status`: 过滤条件; `limit`: 数量限制 | `List` | 检索历史执行记录，支持按任务 ID 或状态过滤。 |
| `perform_intervention(req)` | `request`: `InterventionRequest` 模型 | `Dict` | 对受监管的任务执行人工干预（批准、拒绝等）。 |
| `update_rule_status(id, en)` | `rule_id`: 规则 ID; `enabled`: 开关状态 | `bool` | 动态启用或禁用特定的监督规则。 |
| `get_all_rules()` | 无 | `List` | 获取当前系统中定义的所有规则及其当前状态。 |
| `configure_system(level)` | `level`: 监督级别字符串 | `bool` | 全局更新系统的监督强度级别。 |
| `get_dashboard_data()` | 无 | `Dict` | 获取用于前端仪表板显示的综合统计和活动数据。 |

## 监督规则系统

### 内置规则

系统预置了以下监督规则：

1. **No Destructive Operations** - 防止未经批准的破坏性操作
2. **Resource Usage Limits** - 监控系统资源使用
3. **Data Access Compliance** - 确保数据访问符合隐私和安全策略
4. **Action Frequency Limits** - 防止过快执行动作

### 自定义规则

您可以添加自定义监督规则：

```python
from zentex.supervision.ai_supervisor import SupervisionRule

def my_custom_check(context: dict) -> bool:
    """自定义验证函数"""
    # 检查逻辑
    return True

custom_rule = SupervisionRule(
    rule_id="my_custom_rule",
    name="My Custom Rule",
    description="Description of what this rule checks",
    check_function=my_custom_check,
    severity="high",  # low, medium, high, critical
    auto_intervene=True  # 是否自动触发干预
)

supervisor.add_rule(custom_rule)
```

## 监督级别

系统支持四种监督级别：

| 级别 | 描述 | 适用场景 |
|------|------|----------|
| `MINIMAL` | 基本日志记录 | 低风险环境 |
| `STANDARD` | 定期检查和警报 | 一般生产环境 |
| `STRICT` | 持续监控和即时干预 | 高风险操作 |
| `CRITICAL` | 最大监督，需人工批准 | 关键系统操作 |

```python
from zentex.supervision.ai_supervisor import initialize_supervision, SupervisionLevel

# 初始化特定级别的监督
initialize_supervision(level=SupervisionLevel.STRICT)
```

## Web API 接口

系统提供了完整的 REST API 用于监控和管理：

### 获取监督状态

```bash
GET /api/supervision/status
```

响应示例：
```json
{
  "level": "strict",
  "total_executions": 150,
  "running": 5,
  "completed": 140,
  "failed": 3,
  "interventions_required": 2,
  "active_alerts": 1
}
```

### 获取活动警报

```bash
GET /api/supervision/alerts?severity=high
```

### 确认警报

```bash
POST /api/supervision/alerts/{alert_id}/acknowledge
```

### 获取执行记录

```bash
GET /api/supervision/executions?task_id=task-123&status=completed&limit=50
```

### 创建人工干预

```bash
POST /api/supervision/intervention
Content-Type: application/json

{
  "task_id": "task-123",
  "action": "approve",
  "reason": "Reviewed and verified safe",
  "operator_id": "human-supervisor-001"
}
```

### 获取监督仪表板

```bash
GET /api/supervision/dashboard
```

### 管理监督规则

```bash
# 获取所有规则
GET /api/supervision/rules

# 启用/禁用规则
POST /api/supervision/rules/update
Content-Type: application/json

{
  "rule_id": "no_destructive_ops",
  "enabled": false
}

# 配置监督级别
POST /api/supervision/configure/level?level=strict
```

## 人工干预流程

当系统检测到需要人工干预的情况时：

1. **警报生成** - 系统创建警报并标记执行记录
2. **执行暂停** - 如果需要，自动暂停任务执行
3. **人工审查** - 监督员通过 API 或 Web 控制台审查
4. **决策** - 批准或拒绝继续执行
5. **恢复执行** - 根据决策继续或终止任务

```python
# 检查是否需要人工批准
record = task_supervisor.get_task_supervision_status(task_id)
if record.intervention_required and not record.human_approved:
    print("Task requires human approval before execution")
    
    # 人工批准后
    ai_supervisor.require_human_approval(
        record.record_id, 
        approved=True, 
        approver_id="supervisor-001"
    )
```

## 集成到现有系统

### 1. 在运行时服务中集成

```python
# src/zentex/runtime/service.py
from zentex.supervision.integration import create_supervised_task_manager

class RuntimeService:
    def __init__(self, ...):
        
        # Initialize supervision
        self.supervised_task_manager = create_supervised_task_manager(
            task_service=self.task_service,
            supervision_level=SupervisionLevel.STANDARD
        )
```

### 2. 在任务执行中使用

```python
# 替换原有的任务执行调用
# 原来:
result = execute_task(task_id)

# 现在:
result = await supervised_manager.execute_task_with_supervision(
    task_id=task_id,
    execution_function=execute_task
)
```

### 3. 注册 Web API 路由

```python
# src/zentex/web_console/app.py
from zentex.web_console.routers import supervision

app.include_router(supervision.router)
```

## 监控和告警

### 查看活动警报

```python
supervisor = get_ai_supervisor()

# 获取所有活动警报
active_alerts = supervisor.get_active_alerts()

# 按严重程度过滤
critical_alerts = supervisor.get_active_alerts(severity_filter="critical")

for alert in active_alerts:
    print(f"[{alert.severity.upper()}] {alert.message}")
    print(f"  Recommended: {alert.recommended_action}")
```

### 确认和处理警报

```python
# 确认警报
supervisor.acknowledge_alert(alert_id)

# 获取执行摘要
summary = supervisor.get_execution_summary()
print(f"Total executions: {summary['total_executions']}")
print(f"Interventions required: {summary['interventions_required']}")
```

## 最佳实践

### 1. 选择合适的监督级别

- **开发环境**: `MINIMAL` 或 `STANDARD`
- **测试环境**: `STANDARD`
- **生产环境**: `STRICT`
- **关键操作**: `CRITICAL`

### 2. 定义清晰的规则

```python
# 好的规则示例
def check_sensitive_data_access(context: dict) -> bool:
    """检查是否访问敏感数据"""
    params = context["parameters"]
    sensitive_fields = ["password", "ssn", "credit_card"]
    
    return not any(field in str(params).lower() for field in sensitive_fields)
```

### 3. 定期审查警报

```python
# 设置定期审查
import schedule

def review_alerts():
    supervisor = get_ai_supervisor()
    alerts = supervisor.get_active_alerts()
    
    if alerts:
        logger.warning(f"{len(alerts)} unacknowledged alerts require review")
        for alert in alerts:
            logger.warning(f"  - {alert.message}")

schedule.every(1).hours.do(review_alerts)
```

### 4. 记录干预决策

```python
# 始终记录干预的原因和操作者
supervised_manager.intervene_on_task(
    task_id="task-123",
    action="approve",
    reason="Verified data processing is safe and necessary",
    operator_id="supervisor-john-doe"
)
```

## 故障排除

### 问题：监督初始化失败

```python
# 确保正确导入和初始化
from zentex.supervision.ai_supervisor import initialize_supervision, SupervisionLevel

try:
    initialize_supervision(SupervisionLevel.STANDARD)
except Exception as e:
    logger.error(f"Failed to initialize supervision: {e}")
```

### 问题：任务执行被阻止

检查是否需要人工批准：

```python
record = task_supervisor.get_task_supervision_status(task_id)
if record and record.intervention_required:
    print(f"Task requires approval. Notes: {record.supervisor_notes}")
```

### 问题：过多的警报

调整监督级别或禁用非关键规则：

```python
# 降低监督级别
initialize_supervision(SupervisionLevel.STANDARD)

# 或禁用特定规则
supervisor.rules["resource_limits"].enabled = False
```

## 扩展和定制

### 添加自定义验证器

```python
class CustomAISupervisor(AISupervisor):
    def _check_custom_policy(self, context: dict) -> bool:
        """实现自定义策略检查"""
        # 您的自定义逻辑
        return True
    
    def _initialize_default_rules(self):
        super()._initialize_default_rules()
        
        # 添加自定义规则
        self.add_rule(SupervisionRule(
            rule_id="custom_policy",
            name="Custom Policy Check",
            description="Checks custom organizational policies",
            check_function=self._check_custom_policy,
            severity="high",
            auto_intervene=True
        ))
```

### 集成外部监控系统

```python
# 发送警报到外部系统
def external_alert_handler(alert: SupervisionAlert):
    """发送警报到外部监控系统"""
    import requests
    
    requests.post("https://monitoring.example.com/api/alerts", json={
        "title": alert.message,
        "severity": alert.severity,
        "timestamp": alert.timestamp.isoformat(),
        "metadata": {
            "task_id": alert.task_id,
            "category": alert.category
        }
    })

# 注册为监听器
supervisor.intervention_callbacks.append(external_alert_handler)
```

## 安全考虑

1. **权限控制** - 确保只有授权人员可以进行干预
2. **审计日志** - 所有干预都有完整的审计追踪
3. **防篡改** - 执行记录不可修改，只能追加
4. **幂等性** - 干预操作支持幂等性键，防止重复操作

## 未来改进

- [ ] 机器学习驱动的异常检测
- [ ] 实时可视化仪表板
- [ ] 自动化的根本原因分析
- [ ] 预测性干预建议
- [ ] 多租户支持
- [ ] 高级报告和分析

## 相关文档

- [任务管理系统文档](../tasks/README.md)
- [运行时服务文档](../runtime/README.md)
- [Web 控制台文档](../web_console/README.md)

## 支持和反馈

如有问题或建议，请提交 issue 或联系开发团队。
