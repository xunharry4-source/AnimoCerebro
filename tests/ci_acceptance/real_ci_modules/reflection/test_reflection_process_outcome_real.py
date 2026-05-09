from __future__ import annotations

def test_reflection_process_outcome_real(real_ci_runtime) -> None:
    """功能：验证 process_outcome 对外流程，必须成功生成并可查询。"""
    svc = real_ci_runtime.reflection_service
    exp_id = svc.register_expectation(target_state="done", criteria=["x"], confidence=0.5)
    out = svc.process_outcome(exp_id, actual_state="done", metrics={"score": 1.0})
    # 输入/动作/预期：处理结果后必须生成可落库反思，且可再次查询命中同一记录。
    assert out.reflection_id
    queried = svc.get_reflection(out.reflection_id)
    assert queried.reflection_id == out.reflection_id
    assert queried.reflection_type.value == "outcome_reflection"
    assert queried.context.get("expectation_id") == exp_id
    assert queried.context.get("metrics", {}).get("score") == 1.0
