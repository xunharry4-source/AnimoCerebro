from __future__ import annotations


def test_memory_get_asset_store_real(real_ci_runtime) -> None:
    """功能：验证 get_asset_store 可返回资产存储。"""
    store = real_ci_runtime.memory_service.get_asset_store()
    assert store is not None
