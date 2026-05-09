from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_learning_record_nine_question_learning_real(real_ci_runtime) -> None:
    """功能：验证 record_nine_question_learning 真实写入。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.learning_service.record_nine_question_learning(
        question_id="q1",
        learning_kind="ci",
        detail={"summary": f"sum-{suffix}", "question_driver_refs": ["q1"]},
        trace_id=f"trace-{suffix}",
    )
    assert str(rec.trace_id).strip()
