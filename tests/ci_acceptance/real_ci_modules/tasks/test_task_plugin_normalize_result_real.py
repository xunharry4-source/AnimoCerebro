from __future__ import annotations

from zentex.tasks.service import task_plugin_normalize_result


def test_task_plugin_normalize_result_real() -> None:
    """功能：验证 task_plugin_normalize_result 规范化输出。"""
    out = task_plugin_normalize_result({"status": "ok", "result": {"a": 1}})
    assert out["normalized"] is True
    assert out["status"] == "ok"
    assert out["output"]["result"]["a"] == 1
