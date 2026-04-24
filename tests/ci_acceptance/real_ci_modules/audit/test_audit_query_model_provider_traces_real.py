from __future__ import annotations


def test_audit_query_model_provider_traces_real(real_ci_runtime) -> None:
    """功能：验证 query_model_provider_traces 返回列表。"""
    rows = real_ci_runtime.audit_service.query_model_provider_traces()
    assert isinstance(rows, list)
    if rows:
        first = rows[0]
        if hasattr(first, "model_dump"):
            payload = first.model_dump()
        elif hasattr(first, "__dict__"):
            payload = dict(first.__dict__)
        else:
            payload = {"value": str(first)}
        assert "trace_id" in payload or "request_id" in payload
