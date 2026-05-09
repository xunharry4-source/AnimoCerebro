# Echo Connector / Echo 连接器

## 中文

这是最小的外部连接器示例。它从 stdin 读取 JSON，向 stdout 写出 JSON，不依赖 `src/` 目录下的任何应用代码。

本地测试：

```bash
echo '{"capability":"echo","arguments":{"message":"hello"},"trace_id":"local","connector_id":"echo_connector"}' \
  | python3 plugins/examples/echo_connector/connector.py
```

预期返回 `status=success`，并包含 `output_summary`、`before_evidence`、`after_evidence` 和 `evidence_refs`。

## English

This is the smallest external connector example. It reads JSON from stdin and writes JSON to stdout. It does not depend on any application code under `src/`.

Local test:

```bash
echo '{"capability":"echo","arguments":{"message":"hello"},"trace_id":"local","connector_id":"echo_connector"}' \
  | python3 plugins/examples/echo_connector/connector.py
```

Expected response: `status=success` with `output_summary`, `before_evidence`, `after_evidence`, and `evidence_refs`.
