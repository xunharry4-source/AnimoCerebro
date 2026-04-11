# 系统健康监控功能

## 概述

本功能为Zentex Web控制台添加了系统健康监控页面，提供以下关键信息：

1. **Token使用统计** - 显示总请求次数、输入/输出Token数量
2. **LLM Provider统计** - 每个Provider的健康状态和详细使用情况
3. **功能模块健康** - 监控各个核心模块（Memory、Task、Plugin、Runtime等）的健康状态

## 文件结构

### 后端

- **Contracts**: `src/zentex/web_console/contracts/health.py`
  - `ModuleHealthStatus` - 单个模块的健康状态
  - `LLMProviderStats` - LLM Provider统计信息
  - `TokenUsageStats` - Token使用统计
  - `SystemHealthPayload` - 系统健康状态响应

- **Service**: `src/zentex/web_console/services/health.py`
  - `build_system_health_payload()` - 构建系统健康状态数据
  - `build_token_usage_stats()` - 构建Token使用统计
  - `_get_module_health_status()` - 获取单个模块健康状态

- **Router**: `src/zentex/web_console/routers/health.py`
  - `GET /api/web/health/system` - 获取系统健康状态

### 前端

- **Page**: `src/admin-portal/src/pages/dashboard/HealthDashboard.tsx`
  - 显示Token统计卡片
  - 显示LLM Provider详情
  - 显示各功能模块健康状态
  - 自动刷新（每30秒）

## API端点

### GET /api/web/health/system

获取系统整体健康状态。

**响应示例：**

```json
{
  "overall_health": "healthy",
  "token_usage": {
    "total_request_count": 150,
    "total_input_tokens": 45000,
    "total_output_tokens": 32000,
    "total_tokens": 77000,
    "providers": [
      {
        "provider_name": "openai_compat",
        "api_base": "https://api.openai.com/v1",
        "health_status": "healthy",
        "request_count": 150,
        "input_tokens": 45000,
        "output_tokens": 32000,
        "total_tokens": 77000,
        "error_count": 0
      }
    ]
  },
  "modules": [
    {
      "module_id": "llm_providers",
      "module_name": "LLM Providers",
      "health_status": "healthy",
      "status_message": "1个Provider全部健康",
      "last_check_at": "2026-04-09T10:30:00+00:00",
      "metrics": {
        "total_providers": 1,
        "healthy_providers": 1
      }
    },
    {
      "module_id": "memory",
      "module_name": "Memory Service",
      "health_status": "healthy",
      "last_check_at": "2026-04-09T10:30:00+00:00",
      "metrics": {
        "total_records": 250
      }
    }
  ],
  "timestamp": "2026-04-09T10:30:00+00:00"
}
```

## 访问方式

启动Web控制台后，在左侧导航栏点击 **"系统健康"** 菜单项即可访问。

路径：`/console/health`

## 监控的模块

系统会自动检测并监控以下模块：

1. **LLM Providers** - 大模型Provider的健康状态和统计
2. **Memory Service** - 记忆服务状态
3. **Task Management** - 任务管理服务
4. **Plugin Registry** - 插件注册表
5. **Brain Runtime** - 运行时状态
6. **Active Session** - 当前会话状态

## 健康状态说明

- **healthy** - 模块运行正常
- **degraded** - 模块部分功能降级
- **unhealthy** - 模块不可用或出现严重问题
- **unknown** - 无法确定模块状态

## 特性

- ✅ 实时Token使用统计
- ✅ 各LLM Provider独立统计
- ✅ 多模块健康监控
- ✅ 自动刷新（30秒间隔）
- ✅ 直观的状态颜色标识
- ✅ 详细的指标展示

## 测试

### 后端测试

运行健康API测试：

```bash
python -m pytest tests/web_console/test_health_api.py -v
```

**测试覆盖：**

当前包含8个测试用例，覆盖以下场景：

**正常情况：**
- ✅ API响应结构验证
- ✅ Token统计数据验证
- ✅ 整体健康状态值验证
- ✅ 模块健康状态值验证
- ✅ Provider统计结构完整性验证

**异常情况：**
- ✅ 无runtime时的降级处理

**边界情况：**
- ✅ 空模块列表处理
- ✅ 零Token使用处理
- ✅ 时间戳ISO格式验证
- ✅ 整体状态计算逻辑验证

测试结果：**8/8 passed** ✅

### 前端测试

运行HealthDashboard组件测试：

```bash
cd src/admin-portal
npm test -- HealthDashboard
```

**测试覆盖：**

当前包含12个测试用例，覆盖以下场景：

**正常情况：**
- ✅ Token统计卡片渲染
- ✅ 整体健康状态显示
- ✅ LLM Provider详情展示
- ✅ 模块健康状态显示
- ✅ 时间戳格式显示
- ✅ 自动刷新功能

**异常情况：**
- ✅ API调用失败处理
- ✅ HTTP错误响应处理

**边界情况：**
- ✅ 空模块列表处理
- ✅ 零Token使用显示
- ✅ Provider错误计数显示
- ✅ 降级状态颜色标识

测试结果：**12/12 passed** ✅

## 扩展

如需添加新的监控模块，可以在 `src/zentex/web_console/services/health.py` 的 `build_system_health_payload()` 函数中添加新的模块检查逻辑。

## 回滚指南

如果此功能导致问题，可以通过以下步骤回滚：

1. **前端回滚**：
   - 删除 `src/admin-portal/src/pages/dashboard/HealthDashboard.tsx`
   - 从 `src/admin-portal/src/App.tsx` 中移除 HealthDashboard 的导入和路由配置
   - 从导航菜单中移除"系统健康"项

2. **后端回滚**：
   - 删除 `src/zentex/web_console/contracts/health.py`
   - 删除 `src/zentex/web_console/services/health.py`
   - 删除 `src/zentex/web_console/routers/health.py`
   - 从 `src/zentex/web_console/router.py` 中移除 health_router 的导入和注册
   - 从 `src/zentex/web_console/app.py` 的中间件白名单中移除 `/api/web/health`

3. **测试回滚**：
   - 删除 `tests/web_console/test_health_api.py`

4. **验证回滚**：
   - 确保 Web 控制台正常启动
   - 确保其他 API 端点不受影响
   - 运行现有测试套件确认无回归
