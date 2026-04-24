from __future__ import annotations


def test_task_trigger_negotiation_scans_real(real_ci_runtime) -> None:
    """功能：验证 trigger_negotiation_scans 可调用。"""
    rows = real_ci_runtime.task_service.trigger_negotiation_scans()
    assert isinstance(rows, list)
    for item in rows[:3]:
        assert hasattr(item, "model_dump") or isinstance(item, dict) or isinstance(item, str)
