# 外部应用连接器对接说明 / External Connector Integration Guide

## 中文

### 定位

`plugins/` 是 Zentex 根目录下的外部工具目录，用于放置可以被外部应用连接器中心调用的独立工具。它不是内部插件目录，也不等同于 `src/plugins`。

Zentex 仍然是“大脑”。外部应用连接器中心只是让大脑了解和调用外部软件能力的扩展入口。这里的 manifest 是知识卡片，不是强制门票；没有 manifest 也可以手动注册，但大脑只能按 `minimal` 能力画像理解它。

### 目录结构

推荐每个连接器一个独立目录：

```text
plugins/
  my_connector/
    manifest.json
    connector.py
    requirements.txt
    README.md
```

连接器必须保持独立：

- 不 import `src`、`zentex` 或应用内部模块。
- 与 Zentex 主工程通过 JSON、HTTP、IPC 或外部进程通信。
- 文件入口必须留在根目录 `plugins/` 内，不能越界执行。
- 失败必须透明返回错误，不允许伪成功。

### 能力画像

`profile_level` 表示大脑对连接器的理解程度，不是准入门槛：

- `minimal`：只知道 ID、目标应用、能力名和调用方式。
- `described`：增加能力描述、风险、是否有副作用。
- `verifiable`：增加真实验证方式，例如写后查询、文件哈希、远端资源 ID。
- `governed`：增加权限边界、审计、错误分类、恢复建议和更完整治理信息。

信息越完整，大脑能提供的规划、调用、验证和解释能力越强。信息越少，系统会更保守。

### manifest 知识卡片

推荐的 `manifest.json`：

```json
{
  "connector_id": "my_connector",
  "name": "My Connector",
  "version": "1.0.0",
  "runtime": "python",
  "entrypoint": "connector.py",
  "target_app": "example",
  "connector_type": "sdk_app",
  "profile_level": "described",
  "capabilities": [
    {
      "name": "example_read",
      "description": "Read example data.",
      "read_only": true,
      "risk_level": "read_only",
      "verification": "evidence"
    }
  ],
  "description": "Standalone connector example."
}
```

常用字段：

- `connector_id`：连接器唯一标识。
- `runtime`：运行方式，例如 `python`、`node`、`http`。
- `entrypoint`：入口文件，相对于当前连接器目录。
- `target_app`：目标软件或系统。
- `connector_type`：如 `sdk_app`、`api_app`、`file_app`、`service_bridge`。
- `profile_level`：能力画像等级。
- `capabilities`：能力列表。

### 进程型连接器调用约定

Python/Node 等进程型连接器应从 stdin 读取一个 JSON，并向 stdout 输出一个 JSON。

请求示例：

```json
{
  "capability": "example_read",
  "arguments": {
    "query": "hello"
  },
  "trace_id": "trace-123",
  "connector_id": "my_connector"
}
```

成功响应必须至少包含：

```json
{
  "status": "success",
  "output_summary": {
    "message": "ok"
  },
  "before_evidence": {},
  "after_evidence": {},
  "evidence_refs": []
}
```

失败响应必须至少包含：

```json
{
  "status": "failed",
  "error_code": "MY_CONNECTOR_FAILED",
  "error_stage": "runtime",
  "operator_message": "Human-readable failure reason.",
  "recovery_hint": "How to recover or retry."
}
```

### 副作用能力要求

如果能力会新增、修改、删除外部状态，必须返回真实证据：

- 文件操作：文件存在性、hash、mtime、导出产物路径。
- 数据库操作：写后查询数量、更新后的文档、删除后的计数。
- SaaS/API 操作：远端资源 ID、写后 GET 查询结果。
- 本地软件操作：产物路径、可读取结果、失败上下文。

禁止：

- 只返回 `success` 但没有真实证据。
- 吞异常或隐藏错误。
- mock 外部应用作为真实验收。
- 降级成假正常。

### 本地快速检查

可以直接测试进程型连接器：

```bash
echo '{"capability":"echo","arguments":{"message":"hello"},"trace_id":"local"}' \
  | python3 plugins/examples/echo_connector/connector.py
```

通过 Zentex API 时：

1. `GET /api/web/external-connectors/plugin-manifests`
2. `POST /api/web/external-connectors/register-from-manifest`
3. `POST /api/web/external-connectors/{connector_id}/test-call`
4. `GET /api/web/external-connectors/{connector_id}/history`

## English

### Purpose

`plugins/` is the root-level directory for standalone external tools that can be called by the External Application Connector Center. It is not the internal plugin directory and is not the same as `src/plugins`.

Zentex remains the brain. The connector center only expands what the brain can understand and call. A manifest is a knowledge card, not a mandatory gate. Connectors without a manifest can still be registered manually, but Zentex treats them as `minimal`.

### Directory Layout

Recommended layout:

```text
plugins/
  my_connector/
    manifest.json
    connector.py
    requirements.txt
    README.md
```

Rules:

- Do not import `src`, `zentex`, or internal application modules.
- Integrate with Zentex through JSON, HTTP, IPC, or external processes.
- Entrypoints must remain under the root `plugins/` directory.
- Failures must be transparent; fake success is not allowed.

### Capability Profile

`profile_level` describes how much the brain knows about the connector:

- `minimal`: ID, target app, capability name, and invocation path.
- `described`: descriptions, risk, and side-effect metadata.
- `verifiable`: real verification such as read-after-write, hashes, or remote resource IDs.
- `governed`: permissions, audit, error classification, and recovery guidance.

More information gives the brain better planning, invocation, verification, and explanation. Less information keeps behavior conservative.

### Manifest Knowledge Card

Recommended `manifest.json`:

```json
{
  "connector_id": "my_connector",
  "name": "My Connector",
  "version": "1.0.0",
  "runtime": "python",
  "entrypoint": "connector.py",
  "target_app": "example",
  "connector_type": "sdk_app",
  "profile_level": "described",
  "capabilities": [
    {
      "name": "example_read",
      "description": "Read example data.",
      "read_only": true,
      "risk_level": "read_only",
      "verification": "evidence"
    }
  ],
  "description": "Standalone connector example."
}
```

Common fields:

- `connector_id`: Unique connector identifier.
- `runtime`: Runtime type, such as `python`, `node`, or `http`.
- `entrypoint`: Entrypoint relative to the connector directory.
- `target_app`: Target software or service.
- `connector_type`: For example `sdk_app`, `api_app`, `file_app`, or `service_bridge`.
- `profile_level`: Capability profile level.
- `capabilities`: Capability list.

### Process Connector Contract

Python/Node process connectors should read one JSON object from stdin and write one JSON object to stdout.

Request:

```json
{
  "capability": "example_read",
  "arguments": {
    "query": "hello"
  },
  "trace_id": "trace-123",
  "connector_id": "my_connector"
}
```

Successful response:

```json
{
  "status": "success",
  "output_summary": {
    "message": "ok"
  },
  "before_evidence": {},
  "after_evidence": {},
  "evidence_refs": []
}
```

Failed response:

```json
{
  "status": "failed",
  "error_code": "MY_CONNECTOR_FAILED",
  "error_stage": "runtime",
  "operator_message": "Human-readable failure reason.",
  "recovery_hint": "How to recover or retry."
}
```

### Side-Effect Requirements

Capabilities that create, update, or delete external state must return real evidence:

- File operations: existence, hash, mtime, exported artifact path.
- Database operations: post-write counts, updated documents, post-delete counts.
- SaaS/API operations: remote resource ID and post-write GET result.
- Local software operations: artifact path, readable result, or failure context.

Forbidden:

- Returning `success` without real evidence.
- Swallowing exceptions or hiding errors.
- Using mocks as real acceptance.
- Downgrading failures into fake success.

### Local Smoke Test

Run a process connector directly:

```bash
echo '{"capability":"echo","arguments":{"message":"hello"},"trace_id":"local"}' \
  | python3 plugins/examples/echo_connector/connector.py
```

Through Zentex API:

1. `GET /api/web/external-connectors/plugin-manifests`
2. `POST /api/web/external-connectors/register-from-manifest`
3. `POST /api/web/external-connectors/{connector_id}/test-call`
4. `GET /api/web/external-connectors/{connector_id}/history`
