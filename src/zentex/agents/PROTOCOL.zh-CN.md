# Zentex 外部 Agent 接入协议说明

本文档面向外部 Agent 开发者，说明如何以最小改造接入 Zentex。

## 1. 核心原则

- 外部 Agent 是外部能力源，不是 Zentex 大脑的一部分。
- `agent_id` 是 Zentex 本地登记 ID，外部 Agent 不需要保存、理解或返回。
- 外部 Agent 不需要实现 Zentex 固定生命周期。
- Zentex 通过 adapter/mapping 适配外部 Agent 已有调用方式。
- `service_hooks` 是可选服务钩子，不是准入门槛。
- 每次调用都会生成 `external_task_ref`，外部 Agent 应在后续结果、状态、回调、审核阻塞和产物查询中原样带回。

## 2. 注册协议

注册描述的是“Zentex 如何调用外部 Agent”，不是要求外部 Agent 改造成 Zentex 内部组件。

最小 HTTP JSON 注册示例：

```json
{
  "name": "novel-writer",
  "agent_name": "小说写作 Agent",
  "version": "1.0.0",
  "function_description": "生成和修改小说草稿",
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

字段说明：

| 字段 | 说明 |
| :--- | :--- |
| `name` | Zentex 本地技术名 |
| `agent_name` | 展示名 |
| `endpoint` | 外部 Agent 地址或 Webhook 入口 |
| `adapter_type` | 调用适配器，外部 Agent 推荐使用 `http_json` 或 `webhook`；`legacy_bridge` 仅兼容旧接入 |
| `adapter_config` | 具体调用映射配置 |
| `auth_config` | 可选。本地登录/鉴权适配配置，不保存 secret |
| `service_hooks` | 外部 Agent 选择接入的 Zentex 可选服务 |
| `scope` | Zentex 本地允许调用范围 |

`protocol_capabilities` 是旧字段兼容别名，新接入统一使用 `service_hooks`。

## 3. 需要登录的 Agent

外部 Agent 不需要实现 Zentex 的登录协议。它继续使用自己的 API token、API key、Basic Auth、登录接口或 OAuth2 token endpoint；Zentex 用本地 `auth_config` 描述如何登录、如何把凭证注入请求。

secret 不写入 `adapter_config` 或 `auth_config`。先通过 Zentex 凭证接口加密保存：

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

注册或更新 Agent 时只引用本地凭证：

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

支持的 API 登录方式：

- `bearer_token`
- `api_key`
- `basic`
- `login_flow`
- `oauth2_client_credentials`

本阶段不支持浏览器自动登录、扫码、MFA、captcha 或人工网页登录态导入。

## 4. 模板语法

`body_template`、`headers`、`url/path`、`response_mapping` 可使用模板：

| 模板 | 含义 |
| :--- | :--- |
| `$payload.path` | 本次调用输入 |
| `$agent.path` | Zentex 本地 Agent 登记信息 |
| `$invocation.path` | 本次调用上下文 |
| `$response.path` | 外部 Agent 原始响应 |
| `$auth.path` | Zentex 本地解析出的鉴权数据，只在本地渲染，不要求外部 Agent 理解 |

规则：

- 整个字符串等于模板时，保留原始类型。
- 嵌入字符串时，按字符串替换。
- 找不到路径会视为 mapping 错误。

## 5. 调用上下文

每次 Zentex 调用外部 Agent 时，会生成 invocation 上下文：

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

外部 Agent 最应该关心的是：

```text
external_task_ref
```

它是外部可见任务单号。外部 Agent 可以把它叫作 `task_ref`。

Zentex 本地会持久化：

```text
external_task_ref -> invocation_id -> zentex_task_id -> agent_id
```

这解决同一个外部 Agent 同时处理多个任务时的归属问题。

## 6. HTTP JSON 调用示例

Zentex 发给外部 Agent：

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

Zentex 根据 `response_mapping` 归一化为：

```json
{
  "status": "completed",
  "task_ref": "ztx_taskref_abc123",
  "content": "第三章正文..."
}
```

## 7. 外部人工审核阻塞

如果外部小说 Agent 自己有强制人工审核节点，Zentex 不能绕过。

外部 Agent 可以返回：

```json
{
  "status": "waiting_external_human_review",
  "task_ref": "ztx_taskref_abc123",
  "review_id": "review-7788",
  "reason": "editor_review_required"
}
```

Zentex 应将本地 invocation 标记为：

```text
waiting_external_human_review
```

这表示外部能力内部阻塞，不是 Zentex 调用失败。

推荐服务钩子：

```json
["invoke", "result_view", "callback_result"]
```

## 8. 异步 Callback

如果外部 Agent 注册了 `callback_result`，Zentex 会在调用时注入：

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

| 状态 | 含义 |
| :--- | :--- |
| `submitted` | 已提交，等待外部处理 |
| `running` | 外部正在执行 |
| `waiting_external_human_review` | 外部人工审核阻塞 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `uncertain` | 结果不确定 |

Zentex 通过 `external_task_ref + callback_token` 关联本地记录，不信任远端自报 `agent_id`。

## 9. 关于 CLI / MCP

CLI 和 MCP 通常是既有工具或标准化工具接口，不应要求它们为了 Zentex 专门改造协议。它们只作为 adapter/mapping 的补充接入来源：能映射就接入，不能映射也不影响外部 Agent 协议。

本协议主要面向外部 Agent，推荐外部 Agent 使用 HTTP JSON 或 Webhook 接入。

## 10. 可选服务钩子

| Hook | Zentex 提供的服务 | 是否必选 |
| :--- | :--- | :--- |
| `invoke` | 调用外部能力 | 最小可用 |
| `result_view` | 调用后重新读取结果 | 否 |
| `active_probe` | 主动探查外部可观测事实 | 否 |
| `callback_result` | 外部 Agent 异步推送状态或结果 | 否 |
| `pre_response_advice` | 外部 Agent 回复用户前，Zentex 给建议 | 否 |
| `self_check` | 外部 Agent 提供自检报告 | 否 |
| `progress_stream` | 长任务进度观察 | 否 |
| `cancel` | 请求取消外部任务 | 否 |
| `artifact_list` | 查询产物清单 | 否 |
| `explain_result` | 请求解释结果依据 | 否 |
| `capability_discovery` | 刷新 Zentex 本地能力清单 | 否 |
| `health_probe` | 可用性观察，不作为注册门槛 | 否 |

缺少可选 hook 不阻止注册，只会降低 Zentex 的监督深度或验证置信度。

## 11. 外部 Agent 最小接入规则

外部 Agent 最少做到：

1. 接收 Zentex 通过 adapter 发来的请求。
2. 如果收到 `external_task_ref` 或 `task_ref`，后续结果和状态原样带回。
3. 不需要返回 Zentex `agent_id`。
4. 如果任务进入外部人工审核，明确返回 `waiting_external_human_review` 或可映射的状态。
5. 如果支持 callback，使用 Zentex 给的 callback URL 和 token。

## 12. 常见错误

不要这样做：

- 把 Zentex 的 `agent_id` 当成外部 Agent 身份。
- 要求外部 Agent 必须实现 `/handshake`、`/execute`、`/status`。
- 外部 Agent 返回 `completed`，但实际仍在人工审核。
- 多个任务共用一个外部任务 ID。
- callback 只靠远端自报 `agent_id` 归属任务。

应该这样做：

- 用 `external_task_ref` 关联外部任务。
- 用 adapter/mapping 适配外部 Agent 自己的调用方式。
- 用 `service_hooks` 表示可选增强能力。
- 用 `waiting_external_human_review` 明确表达外部人工阻塞。
- 用 callback token 验证异步回调。
