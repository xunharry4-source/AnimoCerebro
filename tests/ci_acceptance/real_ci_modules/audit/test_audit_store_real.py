from __future__ import annotations


def test_audit_store_real(real_ci_runtime) -> None:
    """功能：验证 audit.service.store 返回真实审计存储对象。"""
    store = real_ci_runtime.audit_service.store
    assert store is not None
    assert callable(getattr(store, "record_flow_start", None))
    assert callable(getattr(store, "list_flows", None))
