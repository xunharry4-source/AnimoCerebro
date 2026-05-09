# Zentex Agents Integration Protocol

中文纯文档见 [PROTOCOL.zh-CN.md](./PROTOCOL.zh-CN.md)。

本文档说明外部 Agent 如何以最小改造接入 Zentex。

核心原则：

- 外部 Agent 是外部能力源，不是 Zentex 大脑的一部分。
- `agent_id` 是 Zentex 本地登记 ID，外部 Agent 不需要保存或返回。
- 外部 Agent 只需要按自己的方式被调用；Zentex 通过 adapter/mapping 适配。
- `service_hooks` 是可选服务。实现得越多，Zentex 能提供的监督、验证、建议、回调和恢复能力越多。
- 每次调用都会生成 `external_task_ref`。外部 Agent 应在结果、状态、回调、审核阻塞和产物查询中原样带回它。

## 1. Registration

注册描述的是“Zentex 怎么调用这个外部能力”，不是要求外部 Agent 实现 Zentex 生命周期。

最小 HTTP JSON 注册：

```json
{
  "name": "novel-writer",
  "agent_name": "Novel Writing Agent",
  "version": "1.0.0",
  "function_description": "Write and revise novel drafts",
  "endpoint": "http://127.0.0.1:9100",
  "role_tag": "writing",
  "scope": ["novel.draft", "novel.revise"],
  "adapter_type": "http_json",
  "service_hooks": ["invoke"],
  "adapter_config": {
    "method": "POST",
    "path": "/write",
    "body_template": {
      "task_ref": "$invocation.external_task_ref",
      "prompt": "$payload.prompt",
      "style": "$payload.style"
    },
    "response_mapping": {
      "status": "$response.status",
      "content": "$response.content",
      "task_ref": "$response.task_ref"
    }
  }
}
```

说明：

- External Agents should normally use `http_json` or `webhook`. `legacy_bridge` is kept for compatibility. CLI/MCP can still be adapted as supplemental tool sources, but this protocol should not require them to change behavior for Zentex.
- `service_hooks` 新接入应使用该字段；`protocol_capabilities` 只作为旧字段兼容。
- `auth_config` is optional local auth mapping. It never stores secrets; secrets are stored through the encrypted credential API and referenced by `credential_ref`.
- `body_template` 和 `response_mapping` 支持 `$payload.path`、`$agent.path`、`$invocation.path`、`$response.path`、`$auth.path`。
- 整个字符串等于模板时保留原始类型；嵌入字符串时转为字符串替换。

## 2. Auth For Existing Agent APIs

External Agents do not need to implement a Zentex login protocol. They can keep their existing API token, API key, Basic Auth, login endpoint, or OAuth2 token endpoint. Zentex adapts locally through `auth_config`.

Store secret material first:

```http
POST /api/web/agents/{agent_id}/credentials
```

```json
{
  "credential_id": "novel-writer-prod",
  "credential_type": "bearer_token",
  "secret_payload": {
    "token": "real-secret-token"
  }
}
```

Then reference it from `auth_config`:

```json
{
  "auth_config": {
    "type": "bearer_token",
    "credential_ref": "novel-writer-prod",
    "inject": {
      "headers": {
        "Authorization": "Bearer $auth.access_token"
      }
    }
  }
}
```

Supported API auth types: `bearer_token`, `api_key`, `basic`, `login_flow`, and `oauth2_client_credentials`. Browser login, QR login, MFA, captcha, and manual web session import are out of scope for this phase.

## 3. Invocation Context

每次 dispatch 时 Zentex 提供 invocation 上下文：

```json
{
  "id": "internal-invocation-id",
  "external_task_ref": "ztx_taskref_xxx",
  "task_ref": "ztx_taskref_xxx",
  "zentex_task_id": "optional-zentex-task-id",
  "callback_url": "optional-callback-url",
  "callback_token": "optional-callback-token"
}
```

外部 Agent 应该关心的是 `external_task_ref`，也可以把它叫作 `task_ref`。它是外部可见的任务单号。

Zentex 本地持久化：

```text
external_task_ref -> invocation_id -> zentex_task_id -> agent_id
```

外部 Agent 不需要知道 `agent_id`。多任务并发时，按 `external_task_ref` 区分任务。

## 4. HTTP JSON Example

外部 Agent 接收：

```http
POST /write
Content-Type: application/json
```

```json
{
  "task_ref": "ztx_taskref_abc123",
  "prompt": "写第三章",
  "style": "悬疑"
}
```

外部 Agent 返回：

```json
{
  "status": "completed",
  "task_ref": "ztx_taskref_abc123",
  "content": "第三章正文..."
}
```

Zentex 通过 `response_mapping` 归一化成：

```json
{
  "status": "completed",
  "content": "第三章正文...",
  "task_ref": "ztx_taskref_abc123"
}
```

## 4. External Human Review Block

如果外部小说 Agent 自己要求人工审核，不能绕过。外部 Agent 可以返回：

```json
{
  "status": "waiting_external_human_review",
  "task_ref": "ztx_taskref_abc123",
  "review_id": "review-7788",
  "reason": "editor_review_required"
}
```

Zentex 应把本地 invocation 状态更新为 `waiting_external_human_review`。这表示外部能力内部阻塞，不是 Zentex 调用失败。

推荐 `service_hooks`：

```json
["invoke", "result_view", "callback_result"]
```

## 5. Callback Example

如果注册时包含 `callback_result`，Zentex 会给外部 Agent 注入：

```json
{
  "external_task_ref": "ztx_taskref_abc123",
  "callback_url": "http://zentex/api/web/agents/callbacks/ztx_taskref_abc123",
  "callback_token": "secret-token"
}
```

外部 Agent 后续回调：

```http
POST /api/web/agents/callbacks/ztx_taskref_abc123
Authorization: Bearer secret-token
Content-Type: application/json
```

```json
{
  "status": "waiting_external_human_review",
  "normalized_result": {
    "review_id": "review-7788",
    "reason": "editor_review_required"
  },
  "raw_response": {
    "state": "review_pending"
  }
}
```

支持状态：

- `submitted`
- `running`
- `waiting_external_human_review`
- `completed`
- `failed`
- `uncertain`

Zentex 通过 `external_task_ref + callback_token` 查本地 ledger，不信任远端自报的 `agent_id`。

## 6. About CLI / MCP

CLI and MCP are usually existing tools or standardized tool interfaces. Zentex should not expect them to change specifically for this protocol. They can be connected as supplemental adapter/mapping sources when useful, but this document is mainly for external Agents and recommends HTTP JSON or Webhook integration.

## 7. Optional Service Hooks

| Hook | Zentex service unlocked | Required |
| :--- | :--- | :--- |
| `invoke` | 调用外部能力 | 最小可用 |
| `result_view` | 调用后重新读取结果 | 否 |
| `active_probe` | 主动探查外部可观测事实 | 否 |
| `callback_result` | 外部 Agent 异步推送状态/结果 | 否 |
| `pre_response_advice` | 外部 Agent 回复用户前，Zentex 给建议 | 否 |
| `self_check` | 外部 Agent 提供自检报告 | 否 |
| `progress_stream` | 长任务进度观察 | 否 |
| `cancel` | 请求取消外部任务 | 否 |
| `artifact_list` | 查询产物清单 | 否 |
| `explain_result` | 请求解释结果依据 | 否 |
| `capability_discovery` | 刷新 Zentex 本地能力清单 | 否 |
| `health_probe` | 可用性观察，不作为注册门槛 | 否 |

缺少可选 hook 不阻止注册，只会降低 Zentex 的监督深度或验证置信度。

## 8. Minimal Rules for External Agents

外部 Agent 最少做到：

1. 接收 Zentex 通过 adapter 发来的请求。
2. 如果收到 `external_task_ref` 或 `task_ref`，后续结果和状态原样带回。
3. 不需要返回 Zentex `agent_id`。
4. 如果任务进入外部人工审核，明确返回 `waiting_external_human_review` 或可映射的状态。
5. 如果支持 callback，使用 Zentex 给的 callback URL 和 token。
