from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str, task_row: dict) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-q8-contract-{suffix}",
            "summary": "Q8 contract sync real test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"mission-{suffix}",
                    "primary_objectives": ["ship verified q8 task"],
                    "secondary_objectives": ["preserve audit evidence"],
                    "completion_conditions": ["actual outcome captured", "evidence captured"],
                    "pause_conditions": ["missing execution receipt"],
                    "escalation_conditions": ["verification failed"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [task_row],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


def _q9_snapshot(suffix: str, *, conservative: bool, risk_control: float, speed: float = 0.15) -> dict:
    evaluation_profile = {
        "role_context": "release executor",
        "resource_context": "real task synchronization runtime",
        "risk_level": "high" if conservative else "medium",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": risk_control,
            "continuity": 0.2,
            "speed": speed,
        },
        "conservative_mode_triggered": conservative,
        "evaluation_style": "evidence_first",
        "action_rhythm_hint": "confirm_before_commit",
    }
    return {
        "trace_id": f"trace-q9-eval-{suffix}",
        "summary": "Q9 evaluation profile for Q8 sync",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _with_q9(base_snapshot: dict, q9_snapshot: dict) -> dict:
    return {**base_snapshot, "q9": q9_snapshot}


@pytest.mark.asyncio
async def test_q8_sync_preserves_acceptance_contract_and_enables_verification_real(real_ci_runtime) -> None:
    """真实链路：Q8 task_queue 同步到 TaskService 后，验收字段和验证配置不得丢失。"""
    suffix = unique_suffix()
    session_id = f"q8-contract-{suffix}"
    task_row = {
        "task_id": f"q8-task-{suffix}",
        "title": "persist q8 acceptance contract",
        "reason": "G15 requires explicit outcome binding",
        "priority": "high",
        "expected_outcome": {"artifact": "task_outcome_contract"},
        "success_criteria": ["contract persisted", "verification enabled"],
        "acceptance_conditions": ["task.contract.success_criteria is not empty"],
        "verification_method": "rule_based_outcome_contract",
        "risk_assessment": {"risk_level": "medium"},
        "pause_conditions": ["no receipt"],
        "escalation_conditions": ["missing evidence"],
    }

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, task_row),
    )

    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"}
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task.metadata["source"] == "nine_questions.q8"
    assert task.metadata["trace_id"] == f"trace-q8-contract-{suffix}"
    assert task.metadata["objective_profile"]["completion_conditions"] == [
        "actual outcome captured",
        "evidence captured",
    ]
    assert task.contract.expected_outcome == {"artifact": "task_outcome_contract"}
    assert task.contract.success_criteria == ["contract persisted", "verification enabled"]
    assert task.contract.acceptance_conditions == ["task.contract.success_criteria is not empty"]
    assert task.contract.pause_conditions == ["no receipt", "missing execution receipt"]
    assert task.contract.escalation_conditions == ["missing evidence", "verification failed"]
    assert task.contract.verification.enabled is True
    assert task.contract.verification.verifiers, "Q8 tasks must not be marked verified without real verifiers"
    assert task.metadata["phase_a_evaluation"]["status"] == "missing"
    assert task.metadata["phase_a_evaluation"]["missing_sources"] == ["q9.snapshot"]
    assert task.metadata["phase_a_evaluation"]["final_priority"] == "high"


@pytest.mark.asyncio
async def test_q8_sync_generates_explicit_fallback_acceptance_when_missing_real(real_ci_runtime) -> None:
    """异常链路：Q8 未给成功判据时只能生成显式 fallback，不能静默降级。"""
    suffix = unique_suffix()
    session_id = f"q8-fallback-{suffix}"
    task_row = {
        "task_id": f"q8-fallback-task-{suffix}",
        "title": "fallback acceptance must be visible",
        "priority": "medium",
    }

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, task_row),
    )

    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"}
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task.contract.success_criteria == ["actual outcome captured", "evidence captured"]
    assert task.contract.acceptance_conditions == ["actual outcome captured", "evidence captured"]
    assert task.contract.risk_assessment["acceptance_fallback_generated"] is True


@pytest.mark.asyncio
async def test_q8_verification_rejects_missing_evidence_and_accepts_real_receipt(real_ci_runtime) -> None:
    """真实验证链路：缺 evidence 必须失败；提供实际 outcome 和 evidence 才允许 DONE。"""
    suffix = unique_suffix()
    session_id = f"q8-verify-{suffix}"
    task_row = {
        "task_id": f"q8-verify-task-{suffix}",
        "title": "verify q8 receipt",
        "success_criteria": ["actual outcome and evidence are present"],
    }

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, task_row),
    )
    task = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"}
    )[0]

    failed = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"completed": True}},
        remarks="missing evidence must not pass",
    )
    assert failed["success"] is False
    assert failed["action_taken"] == "rejected"
    assert failed["verification_result"]["overall_passed"] is False
    assert real_ci_runtime.task_service.get_task(task.task_id).status.value == "failed"
    failed_outcome = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert failed_outcome is not None
    assert failed_outcome["trace_id"] == f"trace-q8-contract-{suffix}"
    assert failed_outcome["overall_passed"] is False
    assert failed_outcome["actual_outcome"] == {"completed": True}
    assert failed_outcome["success_criteria"] == ["actual outcome and evidence are present"]
    assert failed_outcome["verification_result"]["overall_passed"] is False
    assert failed_outcome["deviation_report"]["failed_verifiers"] == ["q8_required_outcome_evidence"]

    suffix_ok = unique_suffix()
    session_ok = f"q8-verify-ok-{suffix_ok}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_ok,
        snapshot_map=_snapshot(session_ok, suffix_ok, {**task_row, "task_id": f"q8-verify-ok-task-{suffix_ok}"}),
    )
    ok_task = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_ok, "queue_name": "next_self_tasks"}
    )[0]
    passed = await real_ci_runtime.task_service.complete_task_with_verification(
        ok_task.task_id,
        result={"actual_outcome": {"completed": True}, "evidence": ["real-ci receipt"]},
        remarks="real receipt provided",
    )
    assert passed["success"] is True
    assert passed["verification_result"]["overall_passed"] is True
    assert real_ci_runtime.task_service.get_task(ok_task.task_id).status.value == "done"
    passed_outcome = real_ci_runtime.task_service.get_task_outcome(ok_task.task_id)
    assert passed_outcome is not None
    assert passed_outcome["trace_id"] == f"trace-q8-contract-{suffix_ok}"
    assert passed_outcome["overall_passed"] is True
    assert passed_outcome["actual_outcome"] == {"completed": True}
    assert passed_outcome["success_criteria"] == ["actual outcome and evidence are present"]
    assert passed_outcome["verification_result"]["overall_passed"] is True
    assert passed_outcome["verification_result"]["verifier_results"]


@pytest.mark.asyncio
async def test_q8_sync_applies_q9_evaluation_profile_to_real_task_priority_and_metadata(real_ci_runtime) -> None:
    """新增/查询链路：Q9 EvaluationProfile 必须真实影响 Q8 任务优先级并可查询。"""
    suffix = unique_suffix()
    session_id = f"q8-eval-create-{suffix}"
    task_row = {
        "task_id": f"q8-eval-task-{suffix}",
        "title": "risk controlled task becomes high priority",
        "priority": "medium",
        "success_criteria": ["risk must be controlled with evidence"],
        "risk_assessment": {"risk_level": "high"},
    }
    snapshot = _with_q9(
        _snapshot(session_id, suffix, task_row),
        _q9_snapshot(suffix, conservative=False, risk_control=0.42),
    )

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=snapshot,
    )

    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"}
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task.priority.value == "high"
    assert task.metadata["evaluation_profile"]["source_trace_id"] == f"trace-q9-eval-{suffix}"
    assert task.metadata["evaluation_profile"]["evaluation_weights"]["risk_control"] == 0.42
    phase_a = task.metadata["phase_a_evaluation"]
    assert phase_a["status"] == "ready"
    assert phase_a["source_trace_id"] == f"trace-q9-eval-{suffix}"
    assert phase_a["base_priority"] == "medium"
    assert phase_a["final_priority"] == "high"
    assert phase_a["risk_level"] == "high"
    assert phase_a["applied_rules"] == ["risk_control_high_risk_to_high"]

    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried.priority.value == "high"
    assert queried.metadata["phase_a_evaluation"]["final_priority"] == "high"


@pytest.mark.asyncio
async def test_q8_resync_updates_evaluation_priority_and_archives_removed_real_task(real_ci_runtime) -> None:
    """修改/删除链路：重同步后必须能查到真实 priority 更新，并确认移除任务被归档。"""
    suffix = unique_suffix()
    session_id = f"q8-eval-update-{suffix}"
    kept_task = {
        "task_id": f"q8-eval-kept-{suffix}",
        "title": "kept task becomes critical",
        "priority": "medium",
        "success_criteria": ["critical path has evidence"],
        "risk_assessment": {"risk_level": "high"},
    }
    removed_task = {
        "task_id": f"q8-eval-removed-{suffix}",
        "title": "removed task must be archived",
        "priority": "low",
        "success_criteria": ["archive evidence"],
        "risk_assessment": {"risk_level": "low"},
    }
    first_snapshot = _snapshot(session_id, suffix, kept_task)
    first_snapshot["q8"]["context_updates"]["q8_task_queue"]["next_self_tasks"].append(removed_task)
    first_snapshot = _with_q9(
        first_snapshot,
        _q9_snapshot(f"{suffix}-first", conservative=False, risk_control=0.2, speed=0.45),
    )

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=first_snapshot,
    )
    created = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(created) == 2
    removed_created = [
        task for task in created if task.metadata["queue_name"] == "next_self_tasks" and task.title == removed_task["title"]
    ][0]
    assert removed_created.status.value == "todo"

    second_snapshot = _with_q9(
        _snapshot(session_id, suffix, kept_task),
        _q9_snapshot(f"{suffix}-second", conservative=True, risk_control=0.5),
    )
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=second_snapshot,
    )

    kept = [
        task
        for task in real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
        if task.title == kept_task["title"]
    ][0]
    assert kept.priority.value == "critical"
    assert kept.metadata["phase_a_evaluation"]["source_trace_id"] == f"trace-q9-eval-{suffix}-second"
    assert kept.metadata["phase_a_evaluation"]["applied_rules"] == ["conservative_high_risk_to_critical"]
    assert kept.metadata["phase_a_evaluation"]["final_priority"] == "critical"

    removed_after = real_ci_runtime.task_service.get_task(removed_created.task_id)
    assert removed_after.status.value == "archived"
    assert removed_after.title == removed_task["title"]


@pytest.mark.asyncio
async def test_q8_sync_rejects_malformed_q9_evaluation_profile_without_fake_priority(real_ci_runtime) -> None:
    """异常链路：Q9 snapshot 存在但缺结构化评估字段时必须抛错，不能生成假 priority。"""
    suffix = unique_suffix()
    session_id = f"q8-eval-bad-{suffix}"
    task_row = {
        "task_id": f"q8-eval-bad-task-{suffix}",
        "title": "malformed q9 profile must fail",
        "priority": "medium",
        "success_criteria": ["must not be created from malformed q9"],
    }
    snapshot = _with_q9(
        _snapshot(session_id, suffix, task_row),
        {"trace_id": f"trace-q9-bad-{suffix}", "context_updates": {}, "result": {}},
    )

    with pytest.raises(RuntimeError) as exc_info:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=snapshot,
        )

    assert "incomplete" in str(exc_info.value)
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert tasks == []
