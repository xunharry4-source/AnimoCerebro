# Agents Module / 外部 Agent 能力入口模块

## Overview / 概述

This module manages how Zentex records, authorizes, invokes, audits, and observes external Agent capabilities.

本模块负责 Zentex 如何登记、授权、调用、审计和观测外部 Agent 提供的能力入口。

External Agents are **external capability providers**, not parts of the Zentex brain. Zentex must adapt to external Agents with minimal impact. External Agents must not be required to adopt Zentex-specific lifecycle, identity, memory, role, or protocol semantics.

外部 Agent 是**外部能力提供方**，不是 Zentex 大脑整体的一部分。Zentex 必须以最小影响方式适配外部 Agent，不得要求外部 Agent 接入 Zentex 专属生命周期、身份体系、记忆体系、角色体系或固定协议。

From the brain's perspective, an external Agent is a stronger external capability source in the same broad category as MCP and CLI: it may expose richer reasoning, planning, memory, or autonomy, but Zentex still treats it as an external callable capability.

从大脑视角看，外部 Agent 是比 MCP、CLI 更强的外部能力源：它可能具备更复杂的推理、规划、记忆或自治能力，但 Zentex 仍然只把它视为可调用的外部能力。

## Design Boundary / 设计边界

### Zentex owns / Zentex 负责

- Local registration of an external capability entry.
- Local capability metadata and permission scope.
- Local invocation adapter and request/response mapping.
- Local trust policy that decides whether Zentex may call the external capability.
- Local audit records, task receipts, and execution evidence.
- Optional local health probes when the external capability supports them.

- 外部能力入口的本地登记。
- 本地能力元数据和权限边界。
- 本地调用适配器与请求/响应映射。
- 本地信任策略，用于决定 Zentex 是否允许调用该外部能力。
- 本地审计记录、任务回执和执行证据。
- 在外部能力支持时进行可选的本地健康探测。

### Zentex does not own / Zentex 不负责

- External Agent identity.
- External Agent lifecycle.
- External Agent runtime state.
- External Agent memory, self-model, role, or internal governance.
- External Agent protocol design.
- External Agent receipt format.

- 外部 Agent 的身份主权。
- 外部 Agent 的生命周期。
- 外部 Agent 的运行时状态。
- 外部 Agent 的记忆、自我模型、角色或内部治理。
- 外部 Agent 的协议设计。
- 外部 Agent 的回执格式。

## Mandatory Principles / 强制原则

1. **Minimal external impact**
   Zentex adapts to the external Agent. The external Agent must not be forced to implement Zentex-specific endpoints such as `/handshake`, `/status`, `/execute`, `/tasks`, or `/receipts/{id}`.

2. **Local identity only**
   `agent_id` is a Zentex-local asset identifier unless explicitly documented otherwise. External Agents must not be required to return or store Zentex-generated IDs.

3. **Registration is metadata, not takeover**
   Registering an external Agent records a capability entry. It must not imply that Zentex owns, controls, supervises, or absorbs that external Agent.

4. **Health checks are optional**
   A capability can be registered even if it has no health endpoint or is temporarily unavailable. Health status may be `unknown`, `unchecked`, `available`, or `unavailable`.

5. **Capability declaration can be manual**
   Capabilities may come from user-provided metadata, documentation, OpenAPI, MCP, custom adapters, or optional discovery. Discovery must not be mandatory.

6. **Receipts are local facts**
   Zentex generates and stores local receipts/audit evidence. External responses are normalized into local evidence; the external Agent must not be required to implement Zentex receipt contracts.

7. **Trust is local authorization**
   Trust level describes whether Zentex is allowed to call the capability under local policy. It is not an attempt to govern the external Agent itself.

8. **Service hooks are optional Zentex services**
   Zentex may define optional service hooks, but none of them is a universal registration requirement. Each hook means "if the external Agent exposes this interface, Zentex can provide this service." Missing hooks lower supervision depth or confidence; they must not make the external Agent impossible to register.

## Correct Architecture / 正确架构

```text
Zentex Brain
  |
  | needs capability: novel.chapter.draft
  v
zentex.agents
  |
  | local registry + policy + adapter + audit
  v
External Agent / HTTP API / MCP / CLI / Webhook / Service
```

The module should be understood as:

```text
ExternalAgentCapabilityRegistry
ExternalAgentInvocationAdapter
ExternalAgentLocalPolicy
ExternalCapabilitySourceForBrainRoleInference
ExternalCapabilityVerificationLayer
```

It must not be understood as:

```text
ExternalAgentLifecycleManager
ExternalAgentIdentityAuthority
ExternalAgentGovernanceOwner
```

## Public Interface / 公共接口

Protocol and integration examples are documented in [PROTOCOL.md](./PROTOCOL.md). Chinese-only version: [PROTOCOL.zh-CN.md](./PROTOCOL.zh-CN.md).

外部 Agent 协议字段和简单接入例子见 [PROTOCOL.zh-CN.md](./PROTOCOL.zh-CN.md)。

The public boundary should be imported through `zentex.agents`:

```python
from zentex.agents import (
    AgentManager,
    AgentAsset,
    AgentStatus,
    AgentTrustLevel,
    AgentCoordinationService,
    AgentRegistrationRequest,
    AgentBridge,
    AgentVerificationPlan,
    AgentVerificationService,
    AgentVerificationStatus,
)
```

Current implementation details under this module are transitional. Callers outside this module should not import internal files directly.

当前模块下的实现细节属于过渡状态。模块外调用方不应直接导入内部文件。

## Current Implementation Warning / 当前实现警告

Some current implementation paths still impose Zentex-specific assumptions on external Agents. These are architectural defects and must be refactored:

- Fixed remote paths in `bridge.py`: `/handshake`, `/status`, `/execute`. These now apply only to the `legacy_bridge` adapter and must not be treated as the recommended integration shape.
- Legacy route names such as `/handshake` and `/safety-audit` still exist for compatibility, but their intended meaning is optional capability discovery and Zentex-local invocation policy evaluation.
- Remote receipt requirements that expect external Agents to return Zentex-style `receipt_id`.

Adapter/mapping mode is now the preferred dispatch path. Remaining legacy names and receipt assumptions must continue to be reduced without breaking compatibility.

当前推荐调用路径已经是 adapter/mapping 模式。遗留命名和回执假设仍需在保持兼容的前提下继续收敛。

## Preferred Integration Shape / 推荐接入形态

External Agent registration should describe an existing capability, not prescribe a new protocol. `service_hooks` describes optional Zentex services the external Agent wants to unlock. `protocol_capabilities` remains a backward-compatible alias only.

```json
{
  "name": "novel-writer",
  "agent_name": "Novel Writing Agent",
  "endpoint": "http://127.0.0.1:9100/write",
  "adapter_type": "http_json",
  "service_hooks": ["invoke", "result_view", "active_probe"],
  "capabilities": ["novel.plan", "novel.chapter.draft", "novel.chapter.revise"],
  "adapter_config": {
    "method": "POST",
    "path": "/write",
    "body_template": {
      "task_ref": "$invocation.external_task_ref",
      "prompt": "$payload.prompt",
      "context": "$payload.context",
      "style": "$payload.style"
    },
    "response_mapping": {
      "content": "$response.text",
      "status": "$response.status"
    }
  }
}
```

The external Agent does not need to know Zentex exists. Zentex owns the adapter, mapping, audit, permission checks, and local receipts.

外部 Agent 不需要知道 Zentex 的存在。Zentex 负责适配器、映射、审计、权限检查和本地回执。

## Auth / 登录鉴权

External Agents keep their own existing login and authorization model. Zentex does not require a Zentex-specific login protocol. For HTTP/Webhook/legacy calls, `auth_config` describes how Zentex should obtain and inject auth locally, while secret material is stored through the encrypted credential vault.

外部 Agent 保持自己的登录和鉴权方式。Zentex 不要求它实现 Zentex 专用登录协议。HTTP/Webhook/legacy 调用通过 `auth_config` 描述本地如何登录和注入鉴权，secret 通过加密凭证库保存。

Supported API auth types:

- `bearer_token`
- `api_key`
- `basic`
- `login_flow`
- `oauth2_client_credentials`

Secrets must be written through `/api/web/agents/{agent_id}/credentials` and referenced by `credential_ref`; do not put tokens, passwords, API keys, or client secrets in `adapter_config` or `auth_config`.

本阶段不支持浏览器自动登录、扫码、MFA、captcha 或人工网页 session 导入。

## Optional Zentex Services / 可选 Zentex 服务钩子

External Agents can implement only the hooks they want. The more hooks they expose, the more Zentex can help with observation, verification, advice, cancellation, and scheduling.

外部 Agent 只需要实现自己愿意实现的钩子。实现得越多，Zentex 能提供的观察、验证、建议、取消和调度服务越多。

| `service_hooks` value | Zentex service unlocked | Required |
| :--- | :--- | :--- |
| `invoke` | Call the external capability through the configured adapter/mapping | Minimal useful hook |
| `result_view` | Re-read task result after invocation for stronger supervision | No |
| `active_probe` | Probe external observable effects, such as files, APIs, task states, or artifacts | No |
| `callback_result` | Let the Agent asynchronously push status/result updates by `external_task_ref` | No |
| `pre_response_advice` | Let Zentex give advice before the external Agent replies to its user | No |
| `self_check` | Let Zentex request a self-check report before accepting the result | No |
| `progress_stream` | Observe long-running execution progress | No |
| `cancel` | Request cancellation through the external Agent's own mechanism | No |
| `artifact_list` | Inspect produced artifacts as evidence | No |
| `explain_result` | Ask the Agent to explain result reasoning or execution path | No |
| `capability_discovery` | Refresh locally recorded capabilities | No |
| `health_probe` | Observe availability without making health a registration gate | No |

These are services, not ownership claims. Zentex does not audit or upgrade the external Agent itself; it only improves Zentex-local calling, supervision, and evidence quality.

这些是 Zentex 提供给接入方的服务，不是所有权声明。Zentex 不审计或提升外部 Agent 本体，只提升本地调用、监督和证据质量。

## Task Correlation / 外部任务关联

Every dispatch creates an opaque `external_task_ref` such as `ztx_taskref_...`. Zentex persists:

```text
external_task_ref -> invocation_id -> zentex_task_id -> agent_id
```

External Agents do not need to know `agent_id`, but they should return or use `external_task_ref` when reporting status, callbacks, result views, review blocks, or artifacts. HTTP/Webhook adapters inject it by default when no `body_template` is configured. Custom templates can use `$invocation.external_task_ref` or `$invocation.task_ref`.

每次派发都会生成外部可见的 `external_task_ref`。外部 Agent 不需要理解 Zentex 的 `agent_id`，但需要在状态、回调、结果查看、审核阻塞或产物查询中原样带回 `external_task_ref`，这样 Zentex 才能把并发任务准确归属到本地 invocation 和任务。

## Verification / 验证与监督

External Agent results must not be trusted only because the call returned successfully. Zentex verifies results through local evidence. Supported verification methods include:

- `remote_result_view`: optional external result-view interface.
- `active_probe`: active read-only probe against observable effects.
- `rule_analysis`: local structural rules over the evidence bundle.
- `llm_analysis`: injected LLM verifier for semantic quality and risk checks.

These methods are optional and composable. A missing method is reported as `skipped` or `uncertain`, not as a registration failure.

外部 Agent 的结果不能只因为调用成功就被信任。Zentex 通过本地证据进行验证：远端结果查看、主动探查、规则分析、LLM 分析都只是可组合的监督方式。缺少某项服务钩子时，结果应体现为 `skipped` 或 `uncertain`，而不是拒绝接入。

## Module Independence / 模块独立性

This is an independent functional module.

- Other modules should interact through `zentex.agents` public interfaces.
- Web Console routes should remain thin adapters and must not implement external Agent business logic.
- Kernel, task, and role-governance systems may consume registered capabilities for skill inventory, role inference, and dispatch planning.
- These systems must treat external Agents as external capability sources, not Zentex brain identity or lifecycle components.
- External Agent failures must be contained as external capability invocation failures.

这是独立功能模块。

- 其他模块应通过 `zentex.agents` 公共接口交互。
- Web Console 路由应保持薄适配，不实现外部 Agent 业务逻辑。
- Kernel、任务系统和角色治理系统可以消费已登记能力，用于技能盘点、角色推断和调度规划。
- 这些系统必须把外部 Agent 视为外部能力源，而不是 Zentex 大脑身份或生命周期组件。
- 外部 Agent 失败必须被限定为外部能力调用失败。
