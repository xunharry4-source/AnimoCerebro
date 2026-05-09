from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.tasks.models import TaskStatus
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.verification.models import VerificationStrategy, VerificationType


def _verified_payload(suffix: str) -> dict:
    payload = task_payload(suffix=suffix, title_prefix="status-verify")
    payload["contract"] = {
        "verification": {
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "real_status_done_bridge",
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
    return payload


@pytest.mark.asyncio
async def test_update_task_status_done_routes_through_verification_and_records_failed_outcome(real_ci_runtime) -> None:
    """直接 update DONE 不得绕过 verification；缺 evidence 时必须失败并落库 outcome。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(_verified_payload(suffix))
    claimed = await real_ci_runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.IN_PROGRESS,
        remarks="real work started",
    )
    assert claimed.status == TaskStatus.IN_PROGRESS

    with pytest.raises(TaskStateError) as exc_info:
        await real_ci_runtime.task_service.update_task_status(
            task.task_id,
            TaskStatus.DONE,
            remarks="operator tried to mark done without evidence",
        )
    assert "routed through verification" in str(exc_info.value)

    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None
    assert queried.task_id == task.task_id
    assert queried.status == TaskStatus.FAILED

    outcome = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["task_id"] == task.task_id
    assert outcome["overall_passed"] is False
    assert outcome["actual_outcome"]["task_id"] == task.task_id
    assert outcome["actual_outcome"]["status_update_request"] is True
    assert outcome["actual_outcome"]["requested_status"] == "done"
    assert "evidence" not in outcome["actual_outcome"]
    verification_result = outcome["verification_result"]
    assert verification_result["overall_passed"] is False
    assert verification_result["recommendation"] == "reject"
    assert verification_result["verifier_results"]
    rule_results = verification_result["verifier_results"][0]["details"]["rule_results"]
    assert rule_results[0]["passed"] is True
    assert rule_results[1]["passed"] is False


@pytest.mark.asyncio
async def test_update_task_status_done_without_verification_keeps_legacy_state_machine(real_ci_runtime) -> None:
    """未启用 verification 的任务仍按原状态机更新，并查询确认真的完成。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="status-no-verify")
    )
    claimed = await real_ci_runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.IN_PROGRESS,
        remarks="started",
    )
    assert claimed.status == TaskStatus.IN_PROGRESS

    done = await real_ci_runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.DONE,
        remarks="legacy completion without verification contract",
    )
    assert done.status == TaskStatus.DONE

    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None
    assert queried.task_id == task.task_id
    assert queried.status == TaskStatus.DONE
    assert real_ci_runtime.task_service.get_task_outcome(task.task_id) is None
