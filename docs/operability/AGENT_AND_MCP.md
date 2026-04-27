# Zentex Agent & MCP Management Guide | Zentex Agent 和 MCP 管理指南

## English Version

Zentex distinguishes between **Heterogeneous Agents** (Long-running advisory brains) and **MCP Tools** (Atomic execution capabilities).

### 1. Heterogeneous Agents (Bridge Protocol)

Agents are persistent external services that collaborate with Zentex via the **4-Phase Bridge Protocol**.

**Core Lifecycle**:
- **Registration**: `POST /api/web/agents/register`. New agents start in `PENDING` state.
- **Handshake**: `POST /api/web/agents/{id}/handshake`. The Agent submits its `capabilities` list.
- **Heartbeat**: Agents ping `POST /api/web/agents/{id}/heartbeat` to maintain `idle` status.
- **Policy Control**: Users can manually `Revoke Trust` (Block) or `Restore Trust`.
- **Termination**: `DELETE /api/web/agents/{id}` physically removes the asset from the inventory.

**Random Number & Test Data Mock Agents (`make dev`)**:

| Agent | Port | Primary Capability |
| :--- | :--- | :--- |
| **Random Number Agent** | 9201 (`RANDOM_AGENT_PORT`) | `random_number` |
| **Test Data Agent** | 9202 (`TESTDATA_AGENT_PORT`) | `testdata_generation` (JSON batches under repo `testdata/`) |

---

### 2. MCP (Model Context Protocol) Tools

MCP Servers are bridge-adapted into Zentex runtimes as point-in-time tool providers.

**Domain Mapping**:

| MCP Type | Zentex Domain | Requires Audit |
| :--- | :--- | :--- |
| Read-only (e.g., Knowledge Hub) | **Cognitive** | No |
| Mutative (e.g., File Write, DB Exec) | **Execution** | Yes (Cloud Audit Redline) |

**Synchronization Logic**:

The `McpAdapterPlugin` maps MCP tool schemas into Zentex `CognitiveToolRegistry`. 
- **Q3 Discovery**: Tools are aggregated into the "What do I have?" snapshot.
- **Q8 Synthesis**: Tool calls are formatted according to the MCP spec and routed through the transport layer (stdio/SSE).

---

### 3. Operational Commands

- **Install dependencies**: `make install` (Python `.venv` + `requirements*.txt`, then `npm install` in `src/admin-portal`). Equivalent to `./scripts/setup_env.sh`.
- **Startup**: `make dev` (Starts backend, frontend, Random Number Agent, and Test Data Agent).
- **Restart**: `make restart-dev` (Clinical-grade cleanup of ports 8000, 5173, 9201, 9202).
- **Testing**:
  - Backend: `pytest tests/web_console/test_agent_lifecycle.py`
  - Frontend: `npm run test src/admin-portal/src/pages/agents/AgentAssetManager.integration.test.tsx`

---

## 中文版本

Zentex 区分**异构 Agent**（长期运行的咨询大脑）和 **MCP 工具**（原子执行能力）。

### 1. 异构 Agent（桥接协议）

Agent 是持久化的外部服务，通过**四阶段桥接协议**与 Zentex 协作。

**核心生命周期**：
- **注册**：`POST /api/web/agents/register`。新 Agent 以 `PENDING` 状态开始。
- **握手**：`POST /api/web/agents/{id}/handshake`。Agent 提交其 `capabilities` 列表。
- **心跳**：Agent 发送 `POST /api/web/agents/{id}/heartbeat` 以维持 `idle` 状态。
- **策略控制**：用户可以手动`撤销信任`（阻止）或`恢复信任`。
- **终止**：`DELETE /api/web/agents/{id}` 从库存中物理移除该资产。

**随机数和测试数据模拟 Agent（`make dev`）**：

| Agent | 端口 | 主要能力 |
| :--- | :--- | :--- |
| **随机数 Agent** | 9201 (`RANDOM_AGENT_PORT`) | `random_number` |
| **测试数据 Agent** | 9202 (`TESTDATA_AGENT_PORT`) | `testdata_generation`（JSON 批次在仓库 `testdata/` 下） |

---

### 2. MCP（模型上下文协议）工具

MCP 服务器作为即时工具提供者，被桥接适配到 Zentex 运行时中。

**域映射**：

| MCP 类型 | Zentex 域 | 需要审计 |
| :--- | :--- | :--- |
| 只读（例如，知识库） | **认知** | 否 |
| 可变（例如，文件写入、数据库执行） | **执行** | 是（云审计红线） |

**同步逻辑**：

`McpAdapterPlugin` 将 MCP 工具模式映射到 Zentex `CognitiveToolRegistry`。
- **Q3 发现**：工具被聚合到“我有什么？”快照中。
- **Q8 综合**：工具调用根据 MCP 规范格式化，并通过传输层（stdio/SSE）路由。

---

### 3. 操作命令

- **安装依赖**：`make install`（Python `.venv` + `requirements*.txt`，然后在 `src/admin-portal` 中执行 `npm install`）。等同于 `./scripts/setup_env.sh`。
- **启动**：`make dev`（启动后端、前端、随机数 Agent 和测试数据 Agent）。
- **重启**：`make restart-dev`（临床级清理端口 8000、5173、9201、9202）。
- **测试**：
  - 后端：`pytest tests/web_console/test_agent_lifecycle.py`
  - 前端：`npm run test src/admin-portal/src/pages/agents/AgentAssetManager.integration.test.tsx`
