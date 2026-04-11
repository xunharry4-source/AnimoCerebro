# CLI 工具详细页面实现文档

## 概述

本文档记录了 CLI 工具详细页面的完整实现，包括后端 API、前端组件、数据模型和测试。

**实现日期**: 2026-04-10  
**功能版本**: v1.0  
**相关路由**: `/console/cli-tools/:toolName`

---

## 功能特性

### 1. 工具详细信息展示
- 基本信息：名称、描述、映射域、插件 ID、特征码
- 配置信息：只读模式、副作用、状态变更、云审计要求
- 项目信息：项目名称、路径、描述

### 2. 信用分系统
- **总分计算** (0-100 分)
  - 成功率权重: 60%
  - 使用频率权重: 20%
  - 响应时间权重: 20%
- **信用等级**
  - 优秀 (≥85 分)
  - 良好 (70-84 分)
  - 一般 (50-69 分)
  - 较差 (<50 分)
- **可视化展示**
  - 大号分数显示
  - 成功率进度条
  - 执行次数统计
  - 使用频率标识

### 3. 任务管理
四个标签页展示不同状态的任务：

#### 3.1 进行中的任务
- 任务 ID、标题、进度条、开始时间、优先级

#### 3.2 待处理任务
- 任务 ID、标题、创建时间、优先级、备注

#### 3.3 失败的任务
- 任务 ID、标题、完成时间、失败原因/备注

#### 3.4 执行历史
- Trace ID、状态、退出码、执行时间、耗时

### 4. 任务统计卡片
实时显示：
- 进行中任务数
- 待处理任务数
- 失败任务数
- 已完成任务数

---

## 技术架构

### 后端实现

#### 1. 数据模型 (`src/zentex/web_console/contracts/cli.py`)

```python
class CliTaskSummary(BaseModel):
    """CLI 任务摘要信息"""
    task_id: str
    title: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    priority: str = "medium"
    remarks: Optional[str] = None

class CliExecutionHistory(BaseModel):
    """CLI 执行历史记录"""
    trace_id: str
    tool_name: str
    status: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: List[str] = []
    working_directory: Optional[str] = None
    executed_at: str
    duration_ms: Optional[int] = None

class CliCreditScore(BaseModel):
    """CLI 工具信用分"""
    total_score: float  # 0-100
    success_rate: float  # 0-1
    total_executions: int
    successful_executions: int
    failed_executions: int
    average_response_time_ms: Optional[float]
    error_rate: float  # 0-1
    usage_frequency: str  # low/medium/high
    credit_level: str  # excellent/good/fair/poor
    last_updated: str

class CliToolDetailResponse(BaseModel):
    """CLI 工具详细信息响应"""
    # 基本信息字段...
    credit_score: CliCreditScore
    task_statistics: Dict[str, int]
```

#### 2. 服务层 (`src/zentex/cli/service.py`)

**核心方法**:

```python
class CliIntegrationService:
    def __init__(self, adapter, transcript_store=None, task_service=None):
        self._adapter = adapter
        self._transcript_store = transcript_store
        self._task_service = task_service
    
    def get_tool_detail(self, tool_name: str) -> Optional[CliToolRuntimeState]
    def get_tool_tasks_by_status(self, tool_name: str, status_filter: str) -> List[Dict]
    def get_tool_execution_history(self, tool_name: str, limit: int = 50) -> List[Dict]
    def calculate_credit_score(self, tool_name: str) -> Dict[str, Any]
    def get_task_statistics(self, tool_name: str) -> Dict[str, int]
```

**信用分计算逻辑**:

```python
def calculate_credit_score(self, tool_name: str) -> Dict[str, Any]:
    # 1. 获取执行历史
    history = self.get_tool_execution_history(tool_name, limit=1000)
    
    # 2. 计算基础指标
    total = len(history)
    successful = sum(1 for h in history if h["status"] == "success")
    success_rate = successful / total if total > 0 else 0.0
    
    # 3. 评估使用频率
    if total > 100: frequency = "high"
    elif total > 20: frequency = "medium"
    else: frequency = "low"
    
    # 4. 计算加权分数
    score_from_success = success_rate * 60
    score_from_usage = {"high": 20, "medium": 15, "low": 10}[frequency]
    score_from_response = 20  # 默认满分
    
    total_score = min(max(score_from_success + score_from_usage + score_from_response, 0), 100)
    
    # 5. 确定等级
    if total_score >= 85: level = "excellent"
    elif total_score >= 70: level = "good"
    elif total_score >= 50: level = "fair"
    else: level = "poor"
    
    return {...}
```

#### 3. API 路由 (`src/zentex/web_console/routers/cli.py`)

**新增端点**:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/web/cli-tools/{tool_name}/detail` | 获取工具详情（含信用分） |
| GET | `/api/web/cli-tools/{tool_name}/tasks/{status}` | 获取分类任务 |
| GET | `/api/web/cli-tools/{tool_name}/execution-history` | 获取执行历史 |

**状态过滤器**:
- `in-progress` - 进行中的任务
- `pending` - 待处理任务
- `failed` - 失败的任务

#### 4. 依赖注入 (`src/zentex/web_console/dependencies.py`)

更新 `get_cli_service()` 以注入必要的依赖：

```python
def get_cli_service(request: Request) -> Any:
    adapter = getattr(request.app.state, "cli_adapter", None)
    if isinstance(adapter, CliAdapterPlugin):
        transcript_store = getattr(request.app.state, "transcript_store", None)
        task_service = getattr(request.app.state, "task_service", None)
        return CliIntegrationService(
            adapter, 
            transcript_store=transcript_store, 
            task_service=task_service
        )
    return None
```

### 前端实现

#### 1. 详细页面组件 (`src/admin-portal/src/pages/cli/CliToolDetailPage.tsx`)

**组件结构**:

```typescript
CliToolDetailPage
├── 返回按钮
├── 工具基本信息卡片
│   ├── 名称和描述
│   ├── 状态标签
│   └── 详细属性列表
├── 信用分卡片
│   ├── 总分和等级
│   ├── 成功率进度条
│   └── 执行统计
├── 任务统计卡片
│   ├── 进行中
│   ├── 待处理
│   ├── 失败
│   └── 已完成
└── 任务标签页
    ├── Tab 1: 进行中的任务表格
    ├── Tab 2: 待处理任务表格
    ├── Tab 3: 失败任务表格
    └── Tab 4: 执行历史表格
```

**关键特性**:
- 使用 React Hooks (`useState`, `useEffect`, `useParams`, `useNavigate`)
- Material-UI 组件库
- 响应式布局（Stack、Box）
- 异步数据加载
- 错误处理和加载状态

#### 2. 路由配置 (`src/admin-portal/src/App.tsx`)

```tsx
<Route path="/console/cli-tools" element={<CliAssetManager />} />
<Route path="/console/cli-tools/:toolName" element={<CliToolDetailPage />} />
```

#### 3. 列表页面优化 (`src/admin-portal/src/pages/cli/CliAssetManager.tsx`)

添加工具名称可点击链接：

```tsx
{
  field: "command_name",
  renderCell: (params) => (
    <Box
      sx={{
        color: "primary.main",
        cursor: "pointer",
        textDecoration: "underline",
        "&:hover": { color: "primary.dark" },
      }}
      onClick={() => navigate(`/console/cli-tools/${params.value}`)}
    >
      {params.value}
    </Box>
  ),
}
```

---

## 数据流

### 1. 页面加载流程

```
用户点击工具名称
    ↓
导航到 /console/cli-tools/:toolName
    ↓
CliToolDetailPage 组件挂载
    ↓
调用 loadToolDetail(toolName)
    ↓
GET /api/web/cli-tools/{toolName}/detail
    ↓
后端查询工具信息、计算信用分、统计任务
    ↓
返回 CliToolDetailResponse
    ↓
前端渲染基本信息、信用分、任务统计
```

### 2. 标签页切换流程

```
用户切换标签页
    ↓
tabValue 状态更新
    ↓
useEffect 检测到变化
    ↓
根据 tabValue 调用对应 API:
  - Tab 0-2: GET /api/web/cli-tools/{name}/tasks/{status}
  - Tab 3: GET /api/web/cli-tools/{name}/execution-history
    ↓
更新 tasks 或 history 状态
    ↓
重新渲染表格
```

### 3. 信用分计算流程

```
calculate_credit_score(tool_name)
    ↓
get_tool_execution_history(tool_name, limit=1000)
    ↓
从 transcript_store 查询审计记录
    ↓
过滤出该工具的记录
    ↓
计算指标:
  - total_executions
  - successful_executions
  - failed_executions
  - success_rate
  - error_rate
  - average_response_time_ms
    ↓
评估使用频率 (low/medium/high)
    ↓
加权计算总分:
  - success_rate * 60
  - usage_frequency_score * 20
  - response_time_score * 20
    ↓
确定信用等级 (excellent/good/fair/poor)
    ↓
返回信用分对象
```

---

## 测试策略

### 单元测试 (`tests/web_console/api/test_cli_tool_detail.py`)

**测试用例**:

1. ✅ `test_cli_tool_detail_endpoint_returns_full_info`
   - 验证详情端点返回完整信息
   - 检查信用分结构
   - 验证任务统计数据

2. ✅ `test_cli_tool_detail_not_found`
   - 验证不存在的工具返回 404

3. ✅ `test_cli_tool_tasks_by_status_endpoint`
   - 测试三种状态过滤器
   - 验证返回数据类型

4. ✅ `test_cli_tool_tasks_invalid_status_filter`
   - 验证无效过滤器返回 400

5. ✅ `test_cli_tool_execution_history_endpoint`
   - 验证历史记录查询
   - 检查记录结构

6. ✅ `test_cli_tool_execution_history_with_limit`
   - 测试不同 limit 值
   - 验证数量限制

7. ✅ `test_credit_score_calculation_for_new_tool`
   - 验证新工具默认信用分
   - 检查零执行场景

8. ✅ `test_credit_score_updates_after_executions`
   - 验证执行后信用分更新
   - 检查成功率计算

**测试结果**:
```
✅ 8/8 测试通过
✅ 无回归问题
✅ 现有 CLI 测试保持通过 (2/2)
```

---

## 部署说明

### 1. 后端部署

无需特殊配置，新功能自动集成到现有系统中。

**依赖检查**:
- ✅ `transcript_store` - 用于查询执行历史
- ✅ `task_service` - 用于查询任务数据
- ✅ `cli_adapter` - 用于获取工具信息

### 2. 前端部署

无需额外构建步骤，组件已集成到现有路由系统。

**浏览器兼容性**:
- Chrome/Edge (最新版)
- Firefox (最新版)
- Safari (最新版)

### 3. 数据库迁移

无需数据库迁移，所有数据来自现有存储：
- `BrainTranscriptStore` - 执行历史
- `TaskManagementService` - 任务数据
- `CliAdapterPlugin` - 工具注册信息

---

## 性能优化

### 1. 后端优化

- **分页支持**: 执行历史支持 `limit` 参数（默认 50，最大 200）
- **懒加载**: 标签页内容在切换时加载
- **缓存友好**: 信用分可缓存，定期更新

### 2. 前端优化

- **条件渲染**: 仅在需要时加载标签页数据
- **加载状态**: 显示 CircularProgress 提升用户体验
- **错误边界**: 完善的错误处理和提示

### 3. 网络优化

- **并行请求**: 工具详情一次性获取所有信息
- **按需加载**: 标签页数据按需获取
- **响应压缩**: FastAPI 自动支持 gzip

---

## 安全考虑

### 1. 权限控制

- 继承现有 Web Console 认证机制
- 敏感信息（如 project_path）可选显示

### 2. 输入验证

- 工具名称 URL 编码
- 状态过滤器白名单验证
- Limit 参数范围限制 (1-200)

### 3. 数据脱敏

- Trace ID 截断显示（前 12 字符）
- 命令输出可选择性隐藏

---

## 扩展性

### 1. 添加新的任务状态

修改 `get_tool_tasks_by_status()` 方法，添加新的状态过滤器。

### 2. 自定义信用分算法

修改 `calculate_credit_score()` 中的权重配置：

```python
score_from_success = success_rate * 60  # 调整权重
score_from_usage = {...}  # 自定义频率评分
score_from_response = ...  # 自定义响应时间评分
```

### 3. 添加新的统计维度

在 `CliToolDetailResponse` 中添加新字段，并在服务层实现相应逻辑。

### 4. 实时数据更新

可添加 WebSocket 支持，实现任务状态实时更新：

```python
@router.websocket("/cli-tools/{tool_name}/stream")
async def stream_tool_updates(websocket: WebSocket, tool_name: str):
    # 实现实时推送
```

---

## 故障排查

### 常见问题

#### 1. 信用分显示为默认值 (50 分)

**原因**: 工具没有执行历史记录

**解决**: 
- 执行几次工具测试调用
- 检查 transcript_store 是否正确配置

#### 2. 任务列表为空

**原因**: 任务未关联到 CLI 工具

**解决**:
- 确保任务的 `metadata.cli_tool_name` 或 `title` 包含工具名称
- 检查 task_service 是否正确注入

#### 3. 执行历史不显示

**原因**: Transcript store 中没有审计记录

**解决**:
- 确认 CLI 工具执行时写入了审计记录
- 检查 `CliCognitiveToolPlugin` 或 `CliExecutionDomainPlugin` 的 `run_tool`/`execute_action` 方法

#### 4. 404 错误

**原因**: 工具名称不存在

**解决**:
- 检查 URL 中的工具名称是否正确
- 确认工具已在系统中注册

---

## 未来改进

### 短期改进 (v1.1)

- [ ] 添加任务操作按钮（重试、取消）
- [ ] 支持导出执行历史为 CSV
- [ ] 添加信用分趋势图（最近 7/30 天）
- [ ] 实现任务搜索和过滤

### 中期改进 (v2.0)

- [ ] WebSocket 实时任务状态更新
- [ ] 信用分预测模型
- [ ] 工具性能对比分析
- [ ] 批量操作支持

### 长期改进 (v3.0)

- [ ] AI 驱动的工具推荐
- [ ] 自动化异常检测
- [ ] 智能任务调度建议
- [ ] 跨工具依赖分析

---

## 相关文件清单

### 后端文件

| 文件路径 | 说明 | 修改类型 |
|---------|------|---------|
| `src/zentex/web_console/contracts/cli.py` | 数据模型定义 | 新增 |
| `src/zentex/cli/service.py` | 服务层实现 | 扩展 |
| `src/zentex/web_console/routers/cli.py` | API 路由 | 扩展 |
| `src/zentex/web_console/dependencies.py` | 依赖注入 | 修改 |

### 前端文件

| 文件路径 | 说明 | 修改类型 |
|---------|------|---------|
| `src/admin-portal/src/pages/cli/CliToolDetailPage.tsx` | 详细页面组件 | 新增 |
| `src/admin-portal/src/App.tsx` | 路由配置 | 修改 |
| `src/admin-portal/src/pages/cli/CliAssetManager.tsx` | 列表页面 | 修改 |

### 测试文件

| 文件路径 | 说明 |
|---------|------|
| `tests/web_console/api/test_cli_tool_detail.py` | API 单元测试 |

---

## 参考资料

- [FastAPI 依赖注入文档](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Material-UI Grid 系统](https://mui.com/material-ui/react-grid2/)
- [React Router v6](https://reactrouter.com/en/main)
- [Pydantic 数据验证](https://docs.pydantic.dev/)

---

## 变更日志

### v1.0 (2026-04-10)

**新增功能**:
- ✅ CLI 工具详细页面
- ✅ 信用分系统
- ✅ 任务分类展示
- ✅ 执行历史记录
- ✅ 完整的单元测试

**技术改进**:
- 服务层职责分离
- 依赖注入优化
- 类型安全增强
- 错误处理完善

**已知限制**:
- 信用分计算基于简单加权算法
- 任务关联通过元数据匹配
- 无实时数据更新

---

## 联系方式

如有问题或建议，请联系开发团队。

**文档维护者**: AI Assistant  
**最后更新**: 2026-04-10
