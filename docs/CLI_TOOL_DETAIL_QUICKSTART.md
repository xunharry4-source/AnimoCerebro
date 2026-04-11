# CLI 工具详细页面 - 快速开始指南

## 🚀 快速使用

### 访问详细页面

1. 启动应用后，访问 `/console/cli-tools`
2. 点击任意工具名称
3. 查看工具详细信息、信用分和任务

### 主要功能

- **工具信息**: 基本信息、配置、项目详情
- **信用分**: 0-100 分，四个等级（优秀/良好/一般/较差）
- **任务管理**: 四个标签页展示不同状态的任务
- **执行历史**: 完整的审计追踪记录

---

## 📋 API 端点

### 获取工具详情

```bash
GET /api/web/cli-tools/{tool_name}/detail
```

**响应示例**:
```json
{
  "command_name": "echo",
  "description": "Echo tool",
  "credit_score": {
    "total_score": 85.5,
    "success_rate": 0.95,
    "total_executions": 100,
    "credit_level": "excellent"
  },
  "task_statistics": {
    "in_progress": 2,
    "pending": 5,
    "failed": 1,
    "completed": 50
  }
}
```

### 获取分类任务

```bash
GET /api/web/cli-tools/{tool_name}/tasks/{status_filter}
```

**状态过滤器**:
- `in-progress` - 进行中的任务
- `pending` - 待处理任务
- `failed` - 失败的任务

### 获取执行历史

```bash
GET /api/web/cli-tools/{tool_name}/execution-history?limit=50
```

**参数**:
- `limit`: 返回记录数量（1-200，默认 50）

---

## 🔧 开发指南

### 运行测试

```bash
# 运行所有 CLI 详细页面测试
python -m pytest tests/web_console/api/test_cli_tool_detail.py -v

# 运行单个测试
python -m pytest tests/web_console/api/test_cli_tool_detail.py::test_cli_tool_detail_endpoint_returns_full_info -v
```

### 本地调试

1. 启动后端服务
2. 启动前端开发服务器
3. 访问 `http://localhost:3000/console/cli-tools`
4. 点击工具名称查看详情

---

## 💡 常见问题

### Q: 为什么信用分显示为 50 分？

A: 新工具没有执行历史时，会显示默认分数。执行几次工具后，分数会根据实际表现更新。

### Q: 如何关联任务到 CLI 工具？

A: 在创建任务时，确保：
- `metadata.cli_tool_name` 设置为工具名称，或
- `title` 中包含工具名称

### Q: 执行历史从哪里来？

A: 从 `BrainTranscriptStore` 中查询审计记录。每次工具执行都会自动记录。

### Q: 可以自定义信用分算法吗？

A: 可以。修改 `src/zentex/cli/service.py` 中的 `calculate_credit_score()` 方法。

---

## 📊 信用分计算

### 计算公式

```
总分 = 成功率得分 + 使用频率得分 + 响应时间得分

成功率得分 = success_rate × 60
使用频率得分 = {high: 20, medium: 15, low: 10}
响应时间得分 = {<100ms: 20, <500ms: 15, <1000ms: 10, ≥1000ms: 5}
```

### 信用等级

| 分数范围 | 等级 | 颜色 |
|---------|------|------|
| ≥85 | 优秀 (excellent) | 绿色 |
| 70-84 | 良好 (good) | 蓝色 |
| 50-69 | 一般 (fair) | 橙色 |
| <50 | 较差 (poor) | 红色 |

---

## 🎨 UI 组件

### 页面结构

```
┌─────────────────────────────────────┐
│  ← 返回 CLI 工具列表                 │
├─────────────────────────────────────┤
│  工具基本信息卡片                     │
│  - 名称、描述、状态                   │
│  - 映射域、插件 ID、特征码            │
│  - 只读模式、云审计要求               │
├─────────────────────────────────────┤
│  信用分卡片                           │
│  - 总分和等级                         │
│  - 成功率进度条                       │
│  - 执行统计                           │
├─────────────────────────────────────┤
│  任务统计卡片                         │
│  [进行中] [待处理] [失败] [已完成]    │
├─────────────────────────────────────┤
│  任务标签页                           │
│  [进行中] [待处理] [失败] [执行历史]  │
│  ┌───────────────────────────────┐  │
│  │ 表格数据...                    │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

---

## 🔍 调试技巧

### 查看 API 响应

打开浏览器开发者工具 → Network 标签 → 筛选 `cli-tools`

### 检查信用分计算

```python
# 在 Python 控制台
from zentex.cli.service import CliIntegrationService

service = ...  # 获取 service 实例
score = service.calculate_credit_score("your_tool_name")
print(score)
```

### 验证任务关联

```python
# 检查任务是否正确关联
tasks = service.get_tool_tasks_by_status("tool_name", "in_progress")
print(f"Found {len(tasks)} in-progress tasks")
```

---

## 📝 示例代码

### 前端：导航到详细页面

```tsx
import { useNavigate } from 'react-router-dom';

const navigate = useNavigate();

// 导航到工具详情
navigate(`/console/cli-tools/${toolName}`);
```

### 后端：获取工具详情

```python
from zentex.cli.service import CliIntegrationService

service = CliIntegrationService(adapter, transcript_store, task_service)

# 获取详细信息
detail = service.get_tool_detail("echo")

# 计算信用分
score = service.calculate_credit_score("echo")

# 获取任务
tasks = service.get_tool_tasks_by_status("echo", "in_progress")

# 获取历史
history = service.get_tool_execution_history("echo", limit=50)
```

---

## 🎯 最佳实践

### 1. 任务命名规范

建议在任务标题中包含工具名称，便于自动关联：

```python
task_title = f"[{tool_name}] Process data file"
```

### 2. 元数据标记

使用元数据明确标记任务所属的工具：

```python
metadata = {
    "cli_tool_name": "echo",
    "operation_type": "test_call",
    "initiated_by": "user_action"
}
```

### 3. 错误处理

始终检查 API 响应状态：

```typescript
const response = await fetch(`/api/web/cli-tools/${name}/detail`);
if (!response.ok) {
  throw new Error(`HTTP ${response.status}`);
}
```

### 4. 性能优化

限制历史记录查询数量：

```python
# 不要一次性加载太多记录
history = service.get_tool_execution_history(tool_name, limit=50)
```

---

## 🔄 更新日志

### v1.0 (2026-04-10)

**新增**:
- ✅ 完整的功能实现
- ✅ 8 个单元测试
- ✅ 详细的实现文档
- ✅ 快速开始指南

**已知限制**:
- 信用分算法较简单
- 无实时数据更新
- 任务关联依赖命名约定

---

## 📚 相关文档

- [完整实现文档](./CLI_TOOL_DETAIL_IMPLEMENTATION.md)
- [API 参考](../src/zentex/web_console/routers/cli.py)
- [数据模型](../src/zentex/web_console/contracts/cli.py)

---

**最后更新**: 2026-04-10  
**维护者**: AI Assistant
