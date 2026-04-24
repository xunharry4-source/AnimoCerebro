from __future__ import annotations

from zentex.tasks.service import task_plugin_rule_based_verification


def test_task_plugin_rule_based_verification_real() -> None:
    """功能：验证 task_plugin_rule_based_verification 规则校验。"""
    out = task_plugin_rule_based_verification(
        result={"result": {"summary": "ok"}},
        rules=[
            {"type": "required_field", "field": "result.summary"},
            {"type": "equals", "field": "result.summary", "expected": "ok"},
        ],
    )
    assert out["passed"] is True
    assert out["failure_count"] == 0
    assert out["overall_status"] == "passed"
