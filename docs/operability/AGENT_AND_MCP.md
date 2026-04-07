# Zentex Agent & MCP Management Guide

Zentex distinguishes between **Heterogeneous Agents** (Long-running advisory brains) and **MCP Tools** (Atomic execution capabilities).

## 1. Heterogeneous Agents (Bridge Protocol)

Agents are persistent external services that collaborate with Zentex via the **4-Phase Bridge Protocol**.

### Core Lifecycle
- **Registration**: `POST /api/web/agents/register`. New agents start in `PENDING` state.
- **Handshake**: `POST /api/web/agents/{id}/handshake`. The Agent submits its `capabilities` list.
- **Heartbeat**: Agents ping `POST /api/web/agents/{id}/heartbeat` to maintain `idle` status.
- **Policy Control**: Users can manually `Revoke Trust` (Block) or `Restore Trust`.
- **Termination**: `DELETE /api/web/agents/{id}` physically removes the asset from the inventory.

### Random Number & Test Data Mock Agents (`make dev`)
| Agent | Port | Primary Capability |
| :--- | :--- | :--- |
| **Random Number Agent** | 9201 (`RANDOM_AGENT_PORT`) | `random_number` |
| **Test Data Agent** | 9202 (`TESTDATA_AGENT_PORT`) | `testdata_generation` (JSON batches under repo `testdata/`) |

---

## 2. MCP (Model Context Protocol) Tools

MCP Servers are bridge-adapted into Zentex runtimes as point-in-time tool providers.

### Domain Mapping
| MCP Type | Zentex Domain | Requires Audit |
| :--- | :--- | :--- |
| Read-only (e.g., Knowledge Hub) | **Cognitive** | No |
| Mutative (e.g., File Write, DB Exec) | **Execution** | Yes (Cloud Audit Redline) |

### Synchronization Logic
The `McpAdapterPlugin` maps MCP tool schemas into Zentex `CognitiveToolRegistry`. 
- **Q3 Discovery**: Tools are aggregated into the "What do I have?" snapshot.
- **Q8 Synthesis**: Tool calls are formatted according to the MCP spec and routed through the transport layer (stdio/SSE).

---

## 3. Operational Commands

- **Install dependencies**: `make install` (Python `.venv` + `requirements*.txt`, then `npm install` in `src/admin-portal`). Equivalent to `./scripts/setup_env.sh`.
- **Startup**: `make dev` (Starts backend, frontend, Random Number Agent, and Test Data Agent).
- **Restart**: `make restart-dev` (Clinical-grade cleanup of ports 8000, 5173, 9201, 9202).
- **Testing**:
  - Backend: `pytest tests/web_console/test_agent_lifecycle.py`
  - Frontend: `npm run test src/admin-portal/src/pages/agents/AgentAssetManager.integration.test.tsx`
