from __future__ import annotations

from zentex.tasks.service import task_plugin_check_constraints


def test_task_plugin_check_constraints_real() -> None:
    """功能：验证 task_plugin_check_constraints 约束检查。"""
    out = task_plugin_check_constraints(
        constraints={
            "max_allowed_risk": "medium",
            "requires_network": True,
            "required_artifact_types": ["report"],
        },
        runtime_context={
            "risk_level": "low",
            "network_available": True,
            "available_artifact_types": ["report", "log"],
            "estimated_duration_seconds": 5,
        },
    )
    assert out["allowed"] is True
    assert out["violation_count"] == 0
    assert out["hard_blockers"] == []
