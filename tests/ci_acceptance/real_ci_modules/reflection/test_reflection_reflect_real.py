from __future__ import annotations

def test_reflection_reflect_real(real_ci_runtime) -> None:
    """功能：验证 reflect 对外方法，必须成功生成并可查询。"""
    svc = real_ci_runtime.reflection_service
    out = svc.reflect(subject="ci-reflect", context={"question_id": "q1"})
    # 真实性依据：真实反思结果必须可通过服务查询回读并校验关键字段。
    assert out.reflection_id
    queried = svc.get_reflection(out.reflection_id)
    assert queried.subject == "ci-reflect"
    assert queried.context.get("question_id") == "q1"
