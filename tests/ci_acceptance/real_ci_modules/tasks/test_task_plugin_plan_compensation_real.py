from __future__ import annotations

from zentex.tasks.service import task_plugin_plan_compensation


def test_task_plugin_plan_compensation_real() -> None:
    """功能：验证 task_plugin_plan_compensation 补偿规划。"""
    out = task_plugin_plan_compensation(
        workspace=".",
        artifacts=[{"path": "tests"}],
        failure_type="incorrect_output",
    )
    assert out["planned"] is True
    assert out["cleanup_target_count"] == 1
    assert out["safe_to_auto_execute"] is True
    assert out["requires_human_confirmation"] is True
