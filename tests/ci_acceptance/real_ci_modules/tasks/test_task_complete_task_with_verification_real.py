from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.tasks.verification.models import VerificationStrategy, VerificationType


@pytest.mark.asyncio
async def test_task_complete_task_with_verification_real(real_ci_runtime) -> None:
    """功能：验证 complete_task_with_verification 真实执行验证器后完成并可查询终态。"""
    suffix = unique_suffix()
    payload = task_payload(suffix=suffix, title_prefix="verify")
    payload["contract"] = {
        "verification": {
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "real_required_receipt",
                    "verifier_type": VerificationType.RULE_BASED.value,
                    "retry_on_failure": False,
                    "max_retries": 0,
                    "config": {
                        "rules": [
                            {"type": "required_field", "field": "actual_outcome"},
                            {"type": "required_field", "field": "evidence"},
                        ]
                    },
                }
            ],
        }
    }
    task = await real_ci_runtime.task_service.create_task(payload)
    out = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"ok": True}, "evidence": ["real-ci verification receipt"]},
    )
    assert isinstance(out, dict)
    assert out.get("success") is True
    assert out.get("verification_skipped") is not True
    assert out["verification_result"]["overall_passed"] is True
    assert out["verification_result"]["verifier_results"]
    assert out["task_outcome"]["overall_passed"] is True
    assert out["task_outcome"]["actual_outcome"] == {"ok": True}
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None
    assert queried.task_id == task.task_id
    assert queried.status.value == "done"
    persisted_outcome = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert persisted_outcome is not None
    assert persisted_outcome["task_id"] == task.task_id
    assert persisted_outcome["overall_passed"] is True
    assert persisted_outcome["actual_outcome"] == {"ok": True}
    assert persisted_outcome["verification_result"]["overall_passed"] is True
    assert persisted_outcome["verification_result"]["verifier_results"]
