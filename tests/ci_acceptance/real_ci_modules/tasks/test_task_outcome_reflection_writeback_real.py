from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service
from zentex.reflection.models import ReflectionType
from zentex.tasks.verification.models import VerificationStrategy, VerificationType


def _snapshot(suffix: str, task_title: str) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-outcome-reflection-{suffix}",
            "summary": "Q8 outcome reflection writeback real test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"reflect task outcome {suffix}",
                    "primary_objectives": ["write task outcome to reflection"],
                    "secondary_objectives": ["preserve verification evidence"],
                    "completion_conditions": ["reflection record can be queried"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["reflection writeback failed"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"q8-reflection-task-{suffix}",
                            "title": task_title,
                            "priority": "high",
                            "expected_outcome": {"reflection": "written"},
                            "success_criteria": ["task outcome exists", "reflection record exists"],
                            "acceptance_conditions": ["task_outcomes.written_back_to_reflection is true"],
                            "verification_method": "rule_based_outcome_contract",
                            "risk_assessment": {"risk_level": "medium"},
                        }
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


def _reflection_e2e_payload(*, suffix: str, scenario: str, verifier_type: VerificationType) -> dict:
    verifier_id = f"reflection_{scenario}_{suffix}"
    if verifier_type == VerificationType.AUTOMATED_TEST:
        verifier = {
            "verifier_id": verifier_id,
            "verifier_type": VerificationType.AUTOMATED_TEST.value,
            "retry_on_failure": False,
            "max_retries": 0,
            "config": {
                "command": "python3 -c 'import time; time.sleep(2)'",
                "working_dir": ".",
                "timeout_seconds": 1,
            },
        }
    else:
        verifier = {
            "verifier_id": verifier_id,
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
    return {
        "title": f"reflection {scenario} e2e {suffix}",
        "task_type": "system_action",
        "originator_id": "ci_real_modules",
        "idempotency_key": f"reflection-{scenario}-{suffix}",
        "metadata": {
            "source": "reflection_e2e_real",
            "question_id": "q8",
            "trace_id": f"trace-reflection-{scenario}-{suffix}",
            "scenario": scenario,
        },
        "contract": {
            "expected_outcome": {"scenario": scenario, "reflection": "must be queryable"},
            "success_criteria": [f"{scenario} outcome persisted", "reflection writeback persisted"],
            "acceptance_conditions": ["task_outcomes reflection flag is true"],
            "verification_method": verifier_type.value,
            "risk_assessment": {"risk_level": "medium", "scenario": scenario},
            "verification": {
                "enabled": True,
                "strategy": VerificationStrategy.ALL_MUST_PASS.value,
                "fallback_action": "fail",
                "max_total_retries": 0,
                "verifiers": [verifier],
            },
        },
    }


def _reflection_result_payload(*, suffix: str, scenario: str) -> dict:
    result = {
        "actual_outcome": {
            "scenario": scenario,
            "artifact": f"reflection-{scenario}-{suffix}",
        }
    }
    if scenario != "failed":
        result["evidence"] = [f"real reflection {scenario} evidence {suffix}"]
    return result


@pytest.mark.parametrize(
    ("scenario", "verifier_type", "expected_passed", "expected_task_status", "expected_verifier_status"),
    [
        ("done", VerificationType.RULE_BASED, True, "done", "passed"),
        ("failed", VerificationType.RULE_BASED, False, "failed", "failed"),
        ("timeout", VerificationType.AUTOMATED_TEST, False, "failed", "timeout"),
    ],
)
@pytest.mark.asyncio
async def test_task_outcome_reflection_writeback_done_failed_timeout_paths_real(
    real_ci_runtime,
    scenario: str,
    verifier_type: VerificationType,
    expected_passed: bool,
    expected_task_status: str,
    expected_verifier_status: str,
) -> None:
    """DONE/FAILED/TIMEOUT 三路径：真实 verification、真实 outcome、真实 reflection 写入后查询。"""
    suffix = unique_suffix()
    payload = _reflection_e2e_payload(suffix=suffix, scenario=scenario, verifier_type=verifier_type)
    task = await real_ci_runtime.task_service.create_task(payload)

    completion = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result=_reflection_result_payload(suffix=suffix, scenario=scenario),
        remarks=f"reflection {scenario} writeback source outcome",
    )
    assert completion["success"] is expected_passed
    queried_task = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried_task is not None
    assert queried_task.status.value == expected_task_status

    before = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert before is not None
    assert before["task_id"] == task.task_id
    assert before["trace_id"] == payload["metadata"]["trace_id"]
    assert before["overall_passed"] is expected_passed
    assert before["written_back_to_reflection"] is False
    assert before["actual_outcome"] == {
        "scenario": scenario,
        "artifact": f"reflection-{scenario}-{suffix}",
    }
    verifier_results = before["verification_result"]["verifier_results"]
    assert len(verifier_results) == 1
    assert verifier_results[0]["verifier_id"] == f"reflection_{scenario}_{suffix}"
    assert verifier_results[0]["status"] == expected_verifier_status
    assert verifier_results[0]["passed"] is expected_passed
    if scenario == "failed":
        rule_results = verifier_results[0]["details"]["rule_results"]
        assert rule_results[0]["passed"] is True
        assert rule_results[1]["passed"] is False
    if scenario == "timeout":
        assert "超时" in verifier_results[0]["summary"]

    writeback = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task.task_id,
    )
    assert writeback["created"] is True
    reflection_id = writeback["reflection_id"]

    after = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert after is not None
    assert after["written_back_to_reflection"] is True
    assert after["reflection_id"] == reflection_id
    assert after["overall_passed"] is expected_passed

    reflection = real_ci_runtime.reflection_service.get_reflection(reflection_id)
    assert reflection.reflection_type == ReflectionType.OUTCOME_REFLECTION
    assert reflection.trace_id == payload["metadata"]["trace_id"]
    assert reflection.context["source"] == "task_outcome_writeback"
    assert reflection.context["question_id"] == "q8"
    assert reflection.context["task_id"] == task.task_id
    assert reflection.context["task_title"] == payload["title"]
    assert reflection.context["task_status"] == expected_task_status
    assert reflection.context["overall_passed"] is expected_passed
    assert reflection.context["actual_outcome"] == before["actual_outcome"]
    assert reflection.context["expected_outcome"] == payload["contract"]["expected_outcome"]
    assert reflection.context["success_criteria"] == payload["contract"]["success_criteria"]
    assert reflection.context["acceptance_conditions"] == payload["contract"]["acceptance_conditions"]
    assert reflection.context["verification_result"]["overall_passed"] is expected_passed
    assert reflection.context["verification_result"]["verifier_results"][0]["status"] == expected_verifier_status

    queried = real_ci_runtime.reflection_service.list_reflections(
        {
            "trace_id": payload["metadata"]["trace_id"],
            "reflection_type": ReflectionType.OUTCOME_REFLECTION,
        }
    )
    matching = [item for item in queried if item.context.get("task_id") == task.task_id]
    assert len(matching) == 1
    assert matching[0].reflection_id == reflection_id

    second = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task.task_id,
    )
    assert second["created"] is False
    assert second["reflection_id"] == reflection_id


@pytest.mark.asyncio
async def test_task_outcome_reflection_writeback_creates_queryable_reflection_real(real_ci_runtime) -> None:
    """新增/修改链路：task_outcomes 写回 Reflection 后，必须能查询到 reflection 与回写标记。"""
    suffix = unique_suffix()
    session_id = f"outcome-reflection-{suffix}"
    task_title = f"write q8 outcome reflection {suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(suffix, task_title),
    )
    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"},
        limit=1,
        offset=0,
    )
    assert len(tasks) == 1
    task = tasks[0]
    completed = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"reflection": "written"}, "evidence": ["real reflection writeback receipt"]},
        remarks="reflection writeback source outcome",
    )
    assert completed["success"] is True
    before = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert before is not None
    assert before["overall_passed"] is True
    assert before["written_back_to_reflection"] is False
    assert before.get("reflection_id") in (None, "")

    writeback = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task.task_id,
    )

    assert writeback["created"] is True
    reflection_id = writeback["reflection_id"]
    after = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert after is not None
    assert after["written_back_to_reflection"] is True
    assert after["reflection_id"] == reflection_id

    reflection = real_ci_runtime.reflection_service.get_reflection(reflection_id)
    assert reflection.reflection_type == ReflectionType.OUTCOME_REFLECTION
    assert reflection.trace_id == f"trace-outcome-reflection-{suffix}"
    assert reflection.context["source"] == "task_outcome_writeback"
    assert reflection.context["question_id"] == "q8"
    assert reflection.context["task_id"] == task.task_id
    assert reflection.context["task_title"] == task_title
    assert reflection.context["overall_passed"] is True
    assert reflection.context["actual_outcome"] == {"reflection": "written"}
    assert reflection.context["success_criteria"] == ["task outcome exists", "reflection record exists"]
    assert reflection.context["verification_result"]["overall_passed"] is True

    queried = real_ci_runtime.reflection_service.list_reflections(
        {
            "trace_id": f"trace-outcome-reflection-{suffix}",
            "reflection_type": ReflectionType.OUTCOME_REFLECTION,
        }
    )
    matching = [item for item in queried if item.context.get("task_id") == task.task_id]
    assert len(matching) == 1, "按 trace/type 查询必须能命中唯一真实 outcome reflection"

    second = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task.task_id,
    )
    assert second["created"] is False
    assert second["reflection_id"] == reflection_id
    queried_again = real_ci_runtime.reflection_service.list_reflections(
        {
            "trace_id": f"trace-outcome-reflection-{suffix}",
            "reflection_type": ReflectionType.OUTCOME_REFLECTION,
        }
    )
    matching_again = [item for item in queried_again if item.context.get("task_id") == task.task_id]
    assert len(matching_again) == 1, "重复写回不得创建重复 reflection"


def test_task_outcome_reflection_writeback_requires_existing_outcome_real(real_ci_runtime) -> None:
    """异常链路：没有真实 task_outcomes 时必须 fail-closed，不能创建空 reflection。"""
    suffix = unique_suffix()
    missing_task_id = f"missing-outcome-{suffix}"
    trace_id = f"trace-missing-outcome-{suffix}"

    before = real_ci_runtime.reflection_service.list_reflections(
        {"trace_id": trace_id, "reflection_type": ReflectionType.OUTCOME_REFLECTION}
    )
    assert before == []

    with pytest.raises(Exception, match="Task outcome not found"):
        real_ci_runtime.task_service.write_task_outcome_to_reflection(
            real_ci_runtime.reflection_service,
            missing_task_id,
        )

    after = real_ci_runtime.reflection_service.list_reflections(
        {"trace_id": trace_id, "reflection_type": ReflectionType.OUTCOME_REFLECTION}
    )
    assert after == [], "缺 outcome 的失败路径不得写入 reflection 假记录"
