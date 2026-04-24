# Zentex Agent 模块完整指南

## 📚 目录

1. [模块概述](#模块概述)
2. [架构设计](#架构设计)
3. [核心组件](#核心组件)
4. [外部 Agent 接入流程](#外部-agent-接入流程)
5. [测试 Agent 示例](#测试-agent-示例)
6. [常见问题与调试](#常见问题与调试)
7. [API 参考](#api-参考)

---

## 模块概述

Zentex Agent 模块负责**管理和协调外部/内部 Agent**，提供标准化的协议接口，实现：

- ✅ **Agent 注册与管理** - 统一注册表，追踪所有 Agent 状态
- ✅ **标准协议通信** - HTTP REST API 握手、任务分发、健康检查
- ✅ **安全审计** - 所有操作记录到 BrainTranscriptStore
- ✅ **信任管理** - Pending → Trusted 的授信流程
- ✅ **零依赖设计** - 外部 Agent 无需引入 Zentex 代码

---

## 架构设计

```
┌─────────────────────────────────────────────┐
│         External Agents (Independent)        │
│  ┌──────────────┐    ┌──────────────────┐   │
│  │ Calculator   │    │ Data Generator   │   │
│  │ Port :9001   │    │ Port :9002       │   │
│  └──────┬───────┘    └────────┬─────────┘   │
│         │ Standard HTTP       │              │
└─────────┼─────────────────────┼──────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────────────────────────────┐
│         Zentex Agent Management              │
│                                              │
│  ┌──────────────┐   ┌──────────────────┐    │
│  │ AgentManager │   │ CoordinationSvc  │    │
│  │ (Registry)   │◄──┤ (Orchestration)  │    │
│  └──────────────┘   └────────┬─────────┘    │
│                              │               │
│                     ┌────────▼─────────┐    │
│                     │  AgentBridge     │    │
│                     │ (HTTP Client)    │    │
│                     └──────────────────┘    │
└─────────────────────────────────────────────┘
```

### 关键设计原则

1. **外部 Agent 完全独立**
   - ❌ 禁止 `import zentex.*`
   - ✅ 只需实现标准 HTTP 接口

2. **标准协议优先**
   - `/handshake` - 能力发现
   - `/execute` - 任务执行
   - `/status` - 健康检查

3. **安全红线**
   - 所有 Agent 初始状态为 `PENDING`
   - 必须通过 Handshake + Safety Audit 才能变为 `TRUSTED`
   - 所有操作写入审计日志

---

## 核心组件

### 1. AgentManager (`manager.py`)

**职责**: Agent 资产注册表

```python
from zentex.agents import AgentManager, AgentAsset

manager = AgentManager()

# 添加 Agent
asset = AgentAsset(
    agent_id="my-agent",
    name="my-agent",
    agent_name="My Agent",
    version="1.0.0",
    endpoint="http://localhost:9001",
    ...
)
manager.add_asset(asset)

# 查询 Agent
agent = manager.get_asset("my-agent")
all_agents = manager.list_assets()
```

### 2. AgentCoordinationService (`service.py`)

**职责**: Agent 生命周期编排

主要功能：
- **注册 Agent** - `register_agent()`
- **执行握手** - `perform_handshake()`
- **安全审计** - `perform_safety_audit()`
- **健康监控** - `monitor_health()`
- **任务分发** - `dispatch_task()`

### 3. AgentBridge (`bridge.py`)

**职责**: HTTP 通信层

```python
from zentex.agents import AgentBridge

bridge = AgentBridge(timeout=30.0)

# 握手
data = await bridge.perform_handshake(agent_asset)

# 执行任务
result = await bridge.execute_task(agent_asset, task_payload)

# 健康检查
is_healthy = await bridge.check_health(agent_asset)
```

---

## 外部 Agent 接入流程

### 步骤 1: 实现标准接口

你的 Agent 需要实现以下 HTTP 端点：

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/handshake")
def handshake():
    return {
        "agent_id": "my-agent",
        "version": "1.0.0",
        "capabilities": [
            {"name": "feature1", "description": "..."}
        ]
    }

@app.post("/execute")
def execute(request: dict):
    task_id = request["task_id"]
    action = request["action"]
    params = request["params"]
    
    # 执行逻辑
    result = perform_action(action, params)
    
    return {
        "task_id": task_id,
        "success": True,
        "result": result
    }

@app.get("/status")
def status():
    return {"status": "online"}
```

### 步骤 2: 注册到 Zentex

```bash
curl -X POST http://127.0.0.1:8000/api/web/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-agent",
    "agent_name": "My Agent",
    "version": "1.0.0",
    "function_description": "Description of capabilities",
    "endpoint": "http://localhost:9001",
    "auth_token": "",
    "role_tag": "custom",
    "scope": ["feature1", "feature2"]
  }'
```

响应：
```json
{
  "agent_id": "abc12345",
  "status": "offline",
  "trust_level": "pending"
}
```

### 步骤 3: 触发握手

```bash
curl http://127.0.0.1:8000/api/web/agents/abc12345/handshake
```

握手成功后，Agent 状态会变为 `idle` 或 `trusted`。

### 步骤 4: 查看管理界面

打开浏览器访问：**http://127.0.0.1:5173**

在左侧菜单选择 **"Agents"**，可以看到所有注册的 Agent 及其状态。

---

## 测试 Agent 示例

项目提供了两个完整的测试 Agent：

### Calculator Agent (端口 9001)

**功能**: 数学计算

**启动**:
```bash
cd /Users/harry/Documents/git/AnimoCerebro
.venv/bin/python Agent/test_server.py
```

**测试**:
```bash
curl http://127.0.0.1:9001/status
curl -X POST http://127.0.0.1:9001/handshake
```

### Data Generator Agent (端口 9002)

**功能**: 生成随机 CSV 数据

**测试**:
```bash
curl http://127.0.0.1:9002/status
```

### 运行集成测试

```bash
.venv/bin/python Agent/quick_test.py
```

这个脚本会：
1. 检查 Zentex 后端是否运行
2. 注册两个测试 Agent
3. 列出所有 Agent
4. 触发握手

---

## 常见问题与调试

### 问题 1: 握手超时 (Connection Timeout)

**症状**: 
```
Handshake failed for agent xxx: All connection attempts failed
```

**原因**:
1. Agent 服务器未启动
2. 端口被防火墙阻止
3. `asyncio.create_task()` 在 FastAPI 中不工作

**解决方案**:

✅ **已修复**: 移除了 `asyncio.create_task()`，改为手动触发握手

**调试步骤**:
```bash
# 1. 验证 Agent 服务器是否运行
curl http://127.0.0.1:9001/status

# 2. 测试 httpx 连接
.venv/bin/python Agent/test_httpx.py

# 3. 检查 Zentex 日志
tail -f /tmp/zentex_dev.log | grep handshake
```

### 问题 2: Agent 注册成功但状态一直是 offline

**原因**: 握手尚未执行

**解决**: 手动触发握手
```bash
curl http://127.0.0.1:8000/api/web/agents/{agent_id}/handshake
```

### 问题 3: 导入错误 `ModuleNotFoundError: zentex`

**原因**: 没有使用虚拟环境

**解决**:
```bash
# 错误
python3 script.py

# 正确
.venv/bin/python script.py
```

### 问题 4: 端口冲突

**症状**:
```
ERROR: [Errno 48] address already in use
```

**解决**:
```bash
# 查找占用端口的进程
lsof -i :9001
lsof -i :9002
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

---

## API 参考

### 注册 Agent

**Endpoint**: `POST /api/web/agents/register`

**Request Body**:
```json
{
  "name": "string",
  "agent_name": "string",
  "version": "string",
  "function_description": "string",
  "endpoint": "string",
  "auth_token": "string",
  "role_tag": "string",
  "trust_level": "pending",
  "scope": ["string"]
}
```

**Response**: `AgentAsset` 对象

---

### 列出所有 Agent

**Endpoint**: `GET /api/web/agents`

**Response**: Array of `AgentConsoleRecord`

---

### 触发握手

**Endpoint**: `GET /api/web/agents/{agent_id}/handshake`

**Response**: Updated `AgentAsset`

---

### 更新 Agent 策略

**Endpoint**: `PATCH /api/web/agents/{agent_id}/policy`

**Request Body**:
```json
{
  "trust_level": "trusted",
  "scope": ["new_scope"]
}
```

---

### 查看审计日志

**Endpoint**: `GET /api/web/agents/{agent_id}/audit`

**Response**: Array of audit events

---

## 文件结构

```
src/zentex/agents/
├── __init__.py          # 模块导出
├── manager.py           # AgentManager (注册表)
├── service.py           # AgentCoordinationService (编排)
└── bridge.py            # AgentBridge (HTTP 通信)

Agent/
├── README.md            # 对接协议说明
├── INTEGRATION_GUIDE.md # 快速集成指南
├── TEST_RESULTS.md      # 测试结果报告
├── ARCHITECTURE.md      # 本文档
├── calculator_agent.py  # 测试 Agent 实现
├── data_generator_agent.py
├── test_server.py       # 测试服务器
├── quick_test.py        # 快速测试脚本
└── test_httpx.py        # HTTP 连接测试
```

---

## 最佳实践

### DO ✅

1. **保持 Agent 独立** - 不要引入 Zentex 依赖
2. **实现所有标准接口** - handshake, execute, status
3. **返回结构化响应** - 遵循 JSON Schema
4. **处理错误 gracefully** - 返回有意义的错误信息
5. **记录日志** - 方便调试

### DON'T ❌

1. **不要修改 Zentex 核心代码** - 通过标准 API 交互
2. **不要硬编码端点** - 使用配置管理
3. **不要忽略超时** - 设置合理的 timeout
4. **不要跳过握手** - 这是安全红线
5. **不要暴露敏感信息** - auth_token 要保护

---

## 版本历史

- **2026-04-07**: 初始实现
  - 添加 AgentBridge
  - 实现真实握手
  - 创建测试 Agent
  - 修复 asyncio 问题

---

## 相关文档

- [Agent README](README.md) - 对接协议详细说明
- [Integration Guide](INTEGRATION_GUIDE.md) - 快速开始
- [Test Results](TEST_RESULTS.md) - 测试报告
- [Zentex Product Doc](../../Zentex_产品功能文档-v1.md) - 产品需求

---

**维护者**: Zentex Team  
**最后更新**: 2026-04-07
