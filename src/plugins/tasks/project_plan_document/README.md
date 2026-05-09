# 项目计划文档插件

## 概述

项目计划文档插件用于组织**非插件项目**（如功能开发、重构、基础设施等）的任务发布前置条件。

区别于产品文档（用于插件升级/创建），项目计划文档强调项目执行层面的规划，包括：
- 项目计划（时间、资源、预算）
- 整体目标（业务目标、技术目标）
- 里程碑和交付物
- 风险识别和应对

## 五部分结构

### 第1部分：基本信息
- 项目名称
- 项目描述
- 任务类别
- 版本号

### 第2部分：项目计划
- 开始和结束日期
- 团队成员及角色
- 预估总工时
- 资源需求
- 预算信息
- 外部依赖

### 第3部分：整体项目目标
- 业务目标
- 技术目标
- 成功指标
- 验收标准

### 第4部分：里程碑
- 里程碑名称和描述
- 目标日期
- 交付物列表
- 成功标准
- 关键指标

### 第5部分：风险点
- 风险标题和描述
- 概率和影响评估
- 优先级
- 缓解策略
- 应急计划

## 使用示例

```python
from src.plugins.tasks.project_plan_document.project_plan_example import create_example_project_plan
from src.plugins.tasks.project_plan_document.project_plan_to_task_converter import convert_project_plan_to_task_list

# 1. 创建项目计划文档
plan_doc = create_example_project_plan()

# 2. 验证文档
is_valid, errors = plan_doc.validate_document()
if not is_valid:
    print("文档验证失败:", errors)

# 3. 生成Markdown报告
report = plan_doc.generate_markdown_report()
print(report)

# 4. 转换为任务列表
task_list, errors = convert_project_plan_to_task_list(plan_doc)
if errors:
    print("转换错误:", errors)
```

## 任务类别

项目计划文档支持以下任务类别：

- `project_feature` - 项目功能开发
- `project_refactor` - 项目重构
- `project_infrastructure` - 项目基础设施
- `research` - 研究任务
- `maintenance` - 维护任务

（不支持 `plugin_upgrade` 和 `plugin_create`，这些应使用产品文档）

## API 参考

### ProjectPlanDocument

主要的文档数据类：

```python
plan = ProjectPlanDocument(
    part1_project_name="项目名称",
    part1_description="项目描述",
    part1_task_category="project_feature",
    # ... 其他参数
)

# 验证文档
is_valid, errors = plan.validate_document()

# 检查是否为插件任务
if plan.is_plugin_task():
    # 这会返回False，表示不该使用项目计划文档

# 添加里程碑
milestone = Milestone(name="第一阶段", ...)
plan.add_milestone(milestone)

# 添加风险项
risk = RiskItem(title="技术风险", ...)
plan.add_risk(risk)

# 转换为字典
data = plan.to_dict()

# 生成Markdown报告
report = plan.generate_markdown_report()
```

## 任务转换

项目计划文档可以自动转换为任务列表：

- 每个里程碑转换为一个主任务
- 里程碑的交付物转换为子任务
- 每个风险项转换为风险应对任务（包含缓解和应急两个子任务）

```python
from src.plugins.tasks.project_plan_document.project_plan_to_task_converter import convert_project_plan_to_task_list

task_list, errors = convert_project_plan_to_task_list(plan_doc)

# 访问任务
for task in task_list.tasks:
    print(f"任务: {task.name}")
    for subtask in task.subtasks:
        print(f"  - {subtask.name}")
        print(f"    验证方法: {subtask.verification_method}")
        print(f"    验收标准: {subtask.acceptance_criteria}")
```

## 插件化设计

项目计划文档插件遵循标准的插件架构：

- `plugin.json` - 插件配置
- `register.py` - 插件注册
- `startup.py` - 插件启动
- `project_plan_document_plugin.py` - 核心逻辑
- `project_plan_to_task_converter.py` - 任务转换
- `project_plan_example.py` - 使用示例

## 与产品文档的区别

| 方面 | 项目计划文档 | 产品文档 |
|------|------------|--------|
| 用途 | 非插件项目规划 | 插件功能设计 |
| 关键部分 | 计划、目标、里程碑、风险 | 架构、模块、功能、验证 |
| 时间跨度 | 项目周期 | 开发周期 |
| 适用任务类别 | PROJECT_* | PLUGIN_* |
| 生成字段 | 项目任务、风险应对任务 | 功能任务、子功能任务 |

## 验证规则

项目计划文档在验证时检查：

- 第1部分：项目名称和描述不为空
- 第2部分：日期完整、团队非空、工时>0
- 第3部分：至少有一个业务目标和成功指标
- 第4部分：至少一个里程碑，且有交付物和成功标准
- 第5部分：至少一个风险项

## 后续集成

项目计划文档可以进一步与以下系统集成：

- 项目管理系统（JIRA、Azure DevOps）
- 进度跟踪系统
- 风险管理平台
- 资源分配系统
