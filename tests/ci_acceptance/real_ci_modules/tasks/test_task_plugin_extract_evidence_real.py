from __future__ import annotations

from zentex.tasks.service import task_plugin_extract_evidence


def test_task_plugin_extract_evidence_real() -> None:
    """功能：验证 task_plugin_extract_evidence 提取证据。"""
    out = task_plugin_extract_evidence(
        {"summary": "ok", "warnings": ["w1"], "artifacts": [{"path": "a.txt"}], "stderr": "err"}
    )
    assert out["summary"] == "ok"
    assert "warnings_present" in out["signals"]
    assert "artifacts_present" in out["signals"]
    assert "stderr_present" in out["signals"]
    assert out["evidence_items"]["evidence_count"] >= 3
