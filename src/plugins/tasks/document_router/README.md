# 文档路由插件

## 概述

文档路由插件根据任务类别自动判断应该使用哪种文档类型：
- **插件任务** (`PLUGIN_UPGRADE`, `PLUGIN_CREATE`) → 使用**产品文档**
- **普通项目任务** (功能开发、重构等) → 使用**项目计划文档**

## 核心概念

### 任务类别

| 类别 | 文档类型 | 用途 |
|------|---------|------|
| `plugin_upgrade` | ProductDocument | 升级现有插件 |
| `plugin_create` | ProductDocument | 创建新插件 |
| `project_feature` | ProjectPlanDocument | 项目功能开发 |
| `project_refactor` | ProjectPlanDocument | 项目重构 |
| `project_infrastructure` | ProjectPlanDocument | 基础设施类任务 |
| `research` | ProjectPlanDocument | 研究任务 |
| `maintenance` | ProjectPlanDocument | 维护任务 |

## 使用方式

### 1. 获取文档类型

```python
from src.plugins.tasks.document_router.document_router_plugin import DocumentRouter

# 根据任务类别获取文档类型
doc_type = DocumentRouter.get_document_type("project_feature")
# 返回: DocumentType.PROJECT_PLAN_DOCUMENT

# 判断是否为插件任务
is_plugin = DocumentRouter.should_use_product_document("plugin_upgrade")
# 返回: True
```

### 2. 获取路由建议

```python
recommendation = DocumentRouter.get_routing_recommendation("project_refactor")
# 返回:
# {
#   "task_category": "project_refactor",
#   "document_type": "project_plan_document",
#   "converter_module": "src.plugins.tasks.project_plan_document.project_plan_to_task_converter",
#   "description": "使用项目计划文档定义项目执行计划、目标和风险",
#   "suitable_for": ["功能开发", "项目重构", "基础设施", "研究任务", "维护"],
#   "key_sections": ["项目计划", "项目目标", "里程碑", "风险点"],
# }
```

### 3. 获取决策建议

```python
from src.plugins.tasks.document_router.document_router_plugin import DocumentDecisionEngine

decision = DocumentDecisionEngine.recommend_document_format("research")
# 返回:
# {
#   "can_decide": True,
#   "recommendation": {...},
#   "next_steps": [
#     "1. 填写基本信息 (第1部分)",
#     "2. 制定项目计划 (第2部分)",
#     ...
#   ]
# }
```

## 集成示例

```python
# 在任务系统中的集成
def create_and_route_task(task_category: str, document_data: dict):
    # 1. 验证任务类别
    is_valid, error = DocumentRouter.validate_task_category(task_category)
    if not is_valid:
        raise ValueError(error)
    
    # 2. 获取推荐的文档类型
    doc_type = DocumentRouter.get_document_type(task_category)
    
    # 3. 根据文档类型创建不同的文档实例
    if doc_type == DocumentType.PRODUCT_DOCUMENT:
        from zentex.tasks.product_document import ProductDocument
        doc = ProductDocument(**document_data)
        from zentex.tasks.task_generator import convert_product_document_to_task_list
        task_list, errors = convert_product_document_to_task_list(doc)
    else:
        from src.plugins.tasks.project_plan_document.project_plan_document_plugin import ProjectPlanDocument
        doc = ProjectPlanDocument(**document_data)
        from src.plugins.tasks.project_plan_document.project_plan_to_task_converter import convert_project_plan_to_task_list
        task_list, errors = convert_project_plan_to_task_list(doc)
    
    return task_list, errors
```

## API 参考

### DocumentRouter

静态方法：
- `get_document_type(task_category)` - 获取文档类型
- `should_use_product_document(task_category)` - 判断是否使用产品文档
- `should_use_project_plan_document(task_category)` - 判断是否使用项目计划文档
- `get_routing_recommendation(task_category)` - 获取路由建议
- `validate_task_category(task_category)` - 验证任务类别

### DocumentDecisionEngine

静态方法：
- `recommend_document_format(task_category, brief_description)` - 获取详细的决策建议

## 文档对比

| 方面 | 产品文档 | 项目计划文档 |
|------|---------|------------|
| **关键部分** | 系统架构、功能模块、功能点 | 项目计划、目标、里程碑、风险 |
| **应用场景** | 插件设计 | 项目执行 |
| **时间维度** | 开发周期 | 项目周期 |
| **关键参与者** | 架构师、开发人员 | 项目经理、技术主管 |
| **输出物** | 功能任务、子功能任务 | 项目任务、风险应对任务 |

## 扩展性

文档路由插件易于扩展：

1. **添加新的任务类别**：
   ```python
   class TaskCategory(str, Enum):
       NEW_CATEGORY = "new_category"
       # 在映射表中添加对应关系
   ```

2. **支持新的文档类型**：
   ```python
   class DocumentType(str, Enum):
       NEW_DOCUMENT_TYPE = "new_document"
       # 在路由逻辑中添加处理
   ```

3. **定制化路由规则**：
   ```python
   # 扩展 DocumentRouter 类
   class CustomDocumentRouter(DocumentRouter):
       @staticmethod
       def get_document_type(task_category):
           # 自定义路由逻辑
           pass
   ```
