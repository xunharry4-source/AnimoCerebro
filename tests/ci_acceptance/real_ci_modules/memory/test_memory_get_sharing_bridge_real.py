from __future__ import annotations

from zentex.memory.sharing.zmsp import ZMSPDecoder

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_get_sharing_bridge_real(real_ci_runtime) -> None:
    """功能：验证 get_sharing_bridge 可导出真实记忆数据包并可解码校验内容。"""
    suffix = unique_suffix()
    marker = f"bridge-marker-{suffix}"
    real_ci_runtime.memory_service.remember(
        title=f"bridge-{suffix}",
        content=marker,
        source="tests",
        tags=["q1", "bridge"],
    )

    bridge = real_ci_runtime.memory_service.get_sharing_bridge()
    assert bridge is not None
    payload = bridge.export_records(layer="all", limit=500)
    assert isinstance(payload, (bytes, bytearray)) and len(payload) > 0

    records, metadata = ZMSPDecoder().decode(payload)
    assert metadata["record_count"] > 0
    assert any(marker in str(item.get("content", "")) for item in records), "导出包未包含刚写入记忆内容"
