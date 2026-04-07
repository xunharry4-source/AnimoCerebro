# Zentex 外部能力对接协议总览

## 📋 三种标准对接方式

Zentex 提供三种标准化的外部能力接入方式，**全部基于标准协议，无需修改 Zentex 代码**。

---

## 1️⃣ CLI 工具接入

**最简单的方式** - 适合命令行工具、脚本

### 注册信息（只需提供）
- ✅ 项目地址 (project_url)
- ✅ 项目名称 (project_name)  
- ✅ 项目说明/文档地址 (documentation_url)
- ✅ 可执行命令路径 (command_executable)
- ✅ 是否只读 (read_only_flag)

### API
```bash
POST /api/web/cli-tools/register
GET  /api/web/cli-tools
```

### 示例
```json
{
  "tool_name": "my-tool",
  "project_url": "https://github.com/user/repo",
  "project_name": "My Tool",
  "description": "Tool description",
  "documentation_url": "https://docs.example.com",
  "command_executable": "/usr/bin/my-tool",
  "read_only_flag": true
}
```

---

## 2️⃣ MCP Server 接入

**推荐用于 AI 工具** - Model Context Protocol

### 注册信息（只需提供）
- ✅ MCP 访问方式 (endpoint + transport_type)
- ✅ MCP 名称 (server_name)
- ✅ MCP 功能说明 (description)
- ✅ MCP 文档地址 (documentation_url)
- ✅ 协议版本 (protocol_version)

### API
```bash
POST /api/web/mcp-servers/register
GET  /api/web/mcp-servers
```

### 示例
```json
{
  "server_id": "my-mcp",
  "server_name": "My MCP Server",
  "description": "Provides AI tools",
  "documentation_url": "https://docs.example.com/mcp",
  "endpoint": "http://localhost:3001/mcp",
  "transport_type": "http",
  "protocol_version": "2024-11-05"
}
```

---

## 3️⃣ Agent 接入

**完整 Agent 系统** - 双向交互和任务调度

### 注册信息（只需提供）
- ✅ Agent ID 和名称
- ✅ 访问端点 (endpoint)
- ✅ 功能说明 (description)
- ✅ 文档地址 (documentation_url)
- ✅ 能力列表 (capabilities)

### Agent 需要实现的接口
```python
POST /handshake    # 能力握手
POST /execute      # 接收任务
GET  /status       # 状态查询
POST /heartbeat    # 心跳上报（可选）
```

### Zentex 提供的接口
```bash
POST /api/web/agents/register      # 注册
GET  /api/web/agents               # 列表
GET  /api/web/agents/{id}/status   # 状态
POST /api/web/agents/{id}/task     # 分发任务
```

### 示例
```json
{
  "agent_id": "my-agent",
  "agent_name": "My Agent",
  "version": "1.0.0",
  "description": "Agent capabilities",
  "documentation_url": "https://docs.example.com",
  "endpoint": "http://localhost:9001/api",
  "capabilities": [...]
}
```

---

## ⚠️ 重要原则

### ❌ 禁止事项
1. **禁止引入 Zentex 代码** - 外部实现不能 import zentex.*
2. **禁止修改 Zentex** - 不能为了适配而改核心代码
3. **禁止侵入式耦合** - 保持完全解耦

### ✅ 正确方式
1. **实现标准接口** - HTTP/WebSocket/gRPC
2. **提供元数据** - 项目信息、文档、能力描述
3. **通过 API 注册** - 调用标准注册接口
4. **独立演进** - 双方互不影响

---

## 📖 详细文档

完整的技术规范请参考：
- **Agent README**: `/Agent/README.md`
- **产品功能文档**: `/Zentex_产品功能文档-v1.md`
  - Agent 管理: 第 1140-1178 行
  - MCP 管理: 第 3215-3268 行
  - CLI 管理: 第 1626-1665 行

---

**核心理念**: 标准化协议 > 代码耦合
