from __future__ import annotations

from zentex.tasks.service import task_plugin_match_capabilities


def test_task_plugin_match_capabilities_real() -> None:
    """功能：验证 task_plugin_match_capabilities 能力匹配。"""
    out = task_plugin_match_capabilities(
        candidate_capabilities=["read", "write.file"],
        required_capabilities=["read"],
    )
    assert out["has_required_capabilities"] is True
    assert "read" in out["matched_required"]
