# MongoDB CRUD Connector

This is a standalone external connector stored under the repository root
`plugins/` directory. It does not import Zentex `src/` code.

The connector reads one JSON request from stdin and writes one JSON response to
stdout. It requires a real MongoDB server and `pymongo`; it does not use mocks,
fake databases, or in-memory substitutes.

Supported capabilities:

- `mongodb_ping`
- `mongodb_create`
- `mongodb_read`
- `mongodb_update`
- `mongodb_delete`

Write capabilities return read-after-write evidence such as inserted documents,
matched/modified/deleted counts, and post-query counts.

## 中文

### 注册方式

推荐通过知识卡片注册：

```http
POST /api/web/external-connectors/register-from-manifest
```

```json
{
  "manifest_path": "mongodb_crud_connector/manifest.json",
  "connector_id_override": "mongodb_crud_connector",
  "display_name": "MongoDB CRUD Connector",
  "connection_config": {
    "timeout_seconds": 20
  },
  "permission_scope": {
    "allowed_operations": [
      "mongodb_ping",
      "mongodb_create",
      "mongodb_read",
      "mongodb_update",
      "mongodb_delete"
    ]
  }
}
```

也可以手动注册：

```http
POST /api/web/external-connectors
```

```json
{
  "connector_id": "mongodb_crud_connector",
  "connector_type": "sdk_app",
  "target_app": "mongodb",
  "display_name": "MongoDB CRUD Connector",
  "description": "Standalone external connector for real MongoDB CRUD operations.",
  "connection_config": {
    "plugin_path": "mongodb_crud_connector/connector.py",
    "timeout_seconds": 20
  },
  "auth_config": {},
  "permission_scope": {},
  "capabilities": []
}
```

注册后检查：

```http
GET /api/web/external-connectors/mongodb_crud_connector
GET /api/web/external-connectors/mongodb_crud_connector/health
```

### 调用示例

```http
POST /api/web/external-connectors/mongodb_crud_connector/test-call
```

```json
{
  "capability": "mongodb_create",
  "arguments": {
    "mongo_uri": "mongodb://127.0.0.1:27017/",
    "database": "zentex_demo",
    "collection": "items",
    "document": {
      "item_id": "demo-1",
      "status": "new"
    }
  },
  "trace_id": "mongodb-create-demo"
}
```

## English

### Registration

Recommended registration from the manifest knowledge card:

```http
POST /api/web/external-connectors/register-from-manifest
```

```json
{
  "manifest_path": "mongodb_crud_connector/manifest.json",
  "connector_id_override": "mongodb_crud_connector",
  "display_name": "MongoDB CRUD Connector",
  "connection_config": {
    "timeout_seconds": 20
  },
  "permission_scope": {
    "allowed_operations": [
      "mongodb_ping",
      "mongodb_create",
      "mongodb_read",
      "mongodb_update",
      "mongodb_delete"
    ]
  }
}
```

Manual registration is also supported:

```http
POST /api/web/external-connectors
```

```json
{
  "connector_id": "mongodb_crud_connector",
  "connector_type": "sdk_app",
  "target_app": "mongodb",
  "display_name": "MongoDB CRUD Connector",
  "description": "Standalone external connector for real MongoDB CRUD operations.",
  "connection_config": {
    "plugin_path": "mongodb_crud_connector/connector.py",
    "timeout_seconds": 20
  },
  "auth_config": {},
  "permission_scope": {},
  "capabilities": []
}
```

Post-registration checks:

```http
GET /api/web/external-connectors/mongodb_crud_connector
GET /api/web/external-connectors/mongodb_crud_connector/health
```

### Invocation Example

```http
POST /api/web/external-connectors/mongodb_crud_connector/test-call
```

```json
{
  "capability": "mongodb_create",
  "arguments": {
    "mongo_uri": "mongodb://127.0.0.1:27017/",
    "database": "zentex_demo",
    "collection": "items",
    "document": {
      "item_id": "demo-1",
      "status": "new"
    }
  },
  "trace_id": "mongodb-create-demo"
}
```
