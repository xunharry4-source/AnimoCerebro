# 文档系统集成指南

完整的产品文档 + 项目计划文档 + 插件化架构

## 系统架构

```
任务发布系统
├─ 第1步：识别任务类别
│  └─ DocumentRouter 判断类型
│
├─ 第2步：选择文档类型
│  ├─ 插件任务 (PLUGIN_*) → 产品文档
│  │  └─ ProductDocument
│  │     └─ 系统架构 + 功能模块 + 功能点 + 验证
│  │
│  └─ 普通项目任务 → 项目计划文档
│     └─ ProjectPlanDocument
│        └─ 项目计划 + 项目目标 + 里程碑 + 风险
│
├─ 第3步：验证文档
│  ├─ 检查所有必需字段完整
│  ├─ 验证数据一致性
│  └─ 生成验证报告
│
├─ 第4步：文档转任务
│  ├─ ProductDocumentToTaskConverter
│  │  └─ 功能模块 → 任务
│  │     └─ 功能点 → 子任务 (含验证方法)
│  │
│  └─ ProjectPlanToTaskConverter
│     ├─ 里程碑 → 任务
│     │  └─ 交付物 → 子任务 (含成功标准)
│     └─ 风险项 → 风险应对任务
│
└─ 第5步：交给任务系统
   ├─ TaskList 保存（含原始文档数据）
   ├─ 支持 JSON 序列化
   └─ 可在任务中查看产品文档
```

## 工作流程

### 场景1：创建插件

```python
# 1. 识别为插件任务
task_category = "plugin_create"
router = DocumentRouter()
doc_type = router.get_document_type(task_category)
# → DocumentType.PRODUCT_DOCUMENT

# 2. 创建产品文档
from zentex.tasks.product_document import ProductDocument
doc = ProductDocument(
    name="新插件名称",
    # ... 填充系统架构、功能模块等5个部分
)

# 3. 验证
is_valid, errors = doc.validate_document()

# 4. 转换为任务
from zentex.tasks.task_generator import convert_product_document_to_task_list
task_list, errors = convert_product_document_to_task_list(doc)

# 5. 保存任务
from zentex.tasks.task_generator import save_task_list_to_json
save_task_list_to_json(task_list, "task_list.json")
```

### 场景2：项目重构

```python
# 1. 识别为项目任务
task_category = "project_refactor"
router = DocumentRouter()
doc_type = router.get_document_type(task_category)
# → DocumentType.PROJECT_PLAN_DOCUMENT

# 2. 创建项目计划文档
from src.plugins.tasks.project_plan_document.project_plan_document_plugin import ProjectPlanDocument
doc = ProjectPlanDocument(
    part1_project_name="微服务架构升级",
    part1_task_category=task_category,
    # ... 填充项目计划、目标、里程碑、风险的5个部分
)

# 3. 验证
is_valid, errors = doc.validate_document()

# 4. 转换为任务
from src.plugins.tasks.project_plan_document.project_plan_to_task_converter import convert_project_plan_to_task_list
task_list, errors = convert_project_plan_to_task_list(doc)

# 5. 保存任务
from zentex.tasks.task_generator import save_task_list_to_json
save_task_list_to_json(task_list, "task_list.json")
```

## 文档格式对比

### ProductDocument（插件）- 5个章节

```
1. 系统架构描述
   ├─ 架构风格（微服务/单体/分布式）
   ├─ 主要组件
   ├─ 数据流
   ├─ 部署架构
   └─ 性能指标

2. 项目计划
   ├─ 时间计划
   ├─ 里程碑
   ├─ 团队成员
   ├─ 资源
   ├─ 风险
   └─ 依赖

3. 项目目标
   ├─ 业务目标
   ├─ 技术目标
   ├─ 成功标准
   └─ 可测量指标

4. 功能模块
   ├─ 模块清单
   ├─ 模块优先级
   └─ 模块依赖

5. 详细功能点
   ├─ 功能描述
   ├─ 验收标准
   ├─ 验证方法
   └─ 技术需求
```

### ProjectPlanDocument（项目）- 5个部分

```
第1部分: 基本信息
├─ 项目名称
├─ 项目描述
├─ 任务类别
└─ 版本号

第2部分: 项目计划
├─ 开始和结束日期
├─ 团队成员及角色
├─ 预估总工时
├─ 资源需求
├─ 预算
└─ 外部依赖

第3部分: 整体项目目标
├─ 业务目标
├─ 技术目标
├─ 成功指标
└─ 验收标准

第4部分: 里程碑
├─ 里程碑名称和描述
├─ 目标日期
├─ 交付物列表
├─ 成功标准
└─ 关键指标

第5部分: 风险点
├─ 风险标题和描述
├─ 概率和影响
├─ 优先级
├─ 缓解策略
└─ 应急计划
```

## 插件架构

### 项目计划文档插件

位置：`src/plugins/tasks/project_plan_document/`

文件：
- `plugin.json` - 插件配置
- `register.py` - 注册接口
- `startup.py` - 启动接口
- `project_plan_document_plugin.py` - 核心数据模型
- `project_plan_to_task_converter.py` - 任务转换
- `project_plan_example.py` - 使用示例
- `README.md` - 文档

特点：
- 按插件规范设计
- 与 ProductDocument 格式一致
- 完整的验证和转换逻辑
- 提供示例和文档

### 文档路由插件

位置：`src/plugins/tasks/document_router/`

文件：
- `plugin.json` - 插件配置
- `register.py` - 注册接口
- `startup.py` - 启动接口
- `document_router_plugin.py` - 路由决策逻辑
- `README.md` - 文档

特点：
- 自动判断文档类型
- 提供路由建议
- 支持决策推理
- 易于扩展

## 集成点

### 1. 在任务服务中集成

```python
# 在任务创建时
from src.plugins.tasks.document_router.document_router_plugin import DocumentRouter

def create_task_from_document(task_category: str, document_data: dict):
    # 1. 路由
    doc_type = DocumentRouter.get_document_type(task_category)
    
    # 2. 创建和验证文档
    if doc_type.value == "product_document":
        from zentex.tasks.product_document import ProductDocument
        doc = ProductDocument(**document_data)
        from zentex.tasks.task_generator import convert_product_document_to_task_list
        task_list, errors = convert_product_document_to_task_list(doc)
    else:
        from src.plugins.tasks.project_plan_document.project_plan_document_plugin import ProjectPlanDocument
        doc = ProjectPlanDocument(**document_data)
        from src.plugins.tasks.project_plan_document.project_plan_to_task_converter import convert_project_plan_to_task_list
        task_list, errors = convert_project_plan_to_task_list(doc)
    
    # 3. 返回结果
    return task_list, errors
```

### 2. API 端点

```python
# POST /api/tasks/from-document
{
    "task_category": "project_refactor",
    "document": {
        "part1_project_name": "...",
        "part1_description": "...",
        # ... 其他字段
    }
}

# 响应
{
    "task_list_id": "TL-xxx",
    "document_type": "project_plan_document",
    "tasks_count": 5,
    "subtasks_count": 12,
    "message": "创建成功"
}
```

### 3. UI 工作流

```
1. 用户输入任务类别
   ↓
2. 系统推荐文档格式
   ↓
3. 用户填填文档（按模板）
   ↓
4. 系统验证文档
   ↓
5. 用户确认后转换为任务
   ↓
6. 任务显示在任务系统中
   ↓
7. 可在任务详情中查看原始文档
```

## 插件化优势

✅ **模块化** - 每个文档类型独立管理  
✅ **可扩展** - 支持添加新的文档类型  
✅ **可重用** - 两个插件共享通用框架  
✅ **易于测试** - 每个插件独立测试  
✅ **易于维护** - 变更集中在特定插件  
✅ **易于集成** - 标准化的插件接口  

## 后续优化

1. **动态插件注册** - 支持运行时加载新的文档类型
2. **插件版本管理** - 支持多个版本并存
3. **插件配置** - 高级自定义选项
4. **插件监控** - 性能和错误监控
5. **插件市场** - 第三方插件生态
