from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_a_observability import (
    Q8PhaseAExitGateError,
    Q8PhaseALensDistributionError,
    Q8PhaseAObservationGateError,
    Q8PhaseAObservationError,
    build_q8_phase_a_exit_gate_report,
    build_q8_phase_a_lens_distribution_report,
    build_q8_phase_a_observation_gate_report,
    build_q8_phase_a_observation_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "phase a observer",
        "resource_context": "real task service observation",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.5,
            "continuity": 0.2,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "evidence_first",
        "action_rhythm_hint": "confirm_before_commit",
    }
    return {
        "trace_id": f"trace-q9-phase-a-{suffix}",
        "summary": "Q9 Phase A observation profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, *, include_q9: bool = True) -> dict:
    snapshot = {
        "q8": {
            "trace_id": f"trace-q8-phase-a-{suffix}",
            "summary": "Q8 Phase A observation test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"observe phase a {suffix}",
                    "primary_objectives": ["observe q9 evaluation effects"],
                    "secondary_objectives": ["preserve phase a metadata"],
                    "completion_conditions": ["phase a observation report is exact"],
                    "pause_conditions": ["phase a metadata missing"],
                    "escalation_conditions": ["priority decision mismatch"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-a-risk-{suffix}",
                            "title": f"phase a high risk task {suffix}",
                            "priority": "medium",
                            "success_criteria": ["risk controlled with evidence"],
                            "risk_assessment": {"risk_level": "high"},
                        }
                    ],
                    "blocked_self_tasks": [
                        {
                            "task_id": f"phase-a-base-{suffix}",
                            "title": f"phase a base priority task {suffix}",
                            "priority": "low",
                            "success_criteria": ["base priority preserved"],
                            "risk_assessment": {"risk_level": "low"},
                        }
                    ],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }
    if include_q9:
        snapshot["q9"] = _q9_snapshot(suffix)
    return snapshot


def _lens_snapshot(session_id: str, suffix: str, lens: str) -> dict:
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    weights = {item: 0.1 for item in required_lenses}
    weights[lens] = 0.7
    evaluation_profile = {
        "role_context": f"phase a {lens} observer",
        "resource_context": "real lens distribution observation",
        "risk_level": "high" if lens == "risk_control" else "low",
        "evaluation_weights": weights,
        "conservative_mode_triggered": False,
        "evaluation_style": f"{lens}_dominant",
        "action_rhythm_hint": "confirm_lens_distribution",
    }
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-a-lens-{lens}-{suffix}",
            "summary": f"Q8 Phase A {lens} lens distribution test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"observe phase a {lens} lens {suffix}",
                    "primary_objectives": [f"activate {lens} lens"],
                    "secondary_objectives": ["preserve lens metadata"],
                    "completion_conditions": ["phase a lens distribution is exact"],
                    "pause_conditions": ["lens metadata missing"],
                    "escalation_conditions": ["lens distribution unhealthy"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-a-lens-{lens}-{suffix}",
                            "title": f"phase a {lens} lens task {suffix}",
                            "priority": "low",
                            "success_criteria": [f"{lens} lens is represented"],
                            "risk_assessment": {
                                "risk_level": "high" if lens == "risk_control" else "low",
                            },
                        }
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        },
        "q9": {
            "trace_id": f"trace-q9-phase-a-lens-{lens}-{suffix}",
            "summary": f"Q9 Phase A {lens} lens profile",
            "context_updates": {
                "q9_evaluation_profile": evaluation_profile,
                "q9_action_posture": {"evaluation_profile": evaluation_profile},
            },
            "result": {"evaluation_profile": evaluation_profile},
        },
    }


async def _write_manual_reviews(task_service, tasks, suffix: str, *, obvious_drift: bool = False) -> None:
    for index, task in enumerate(tasks):
        review = {
            "review_status": "completed",
            "reviewer_id": f"phase-a-reviewer-{suffix}",
            "reviewed_at": f"2026-04-28T10:{index:02d}:00+08:00",
            "task_quality_label": "good" if not obvious_drift else "bad",
            "obvious_drift": obvious_drift,
        }
        await task_service.update_task_metadata(
            task.task_id,
            {"phase_a_manual_review": review},
            remarks="Phase A manual review evidence recorded by real test.",
        )
        refreshed = task_service.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.metadata["phase_a_manual_review"] == review


async def _write_open_quality_issue(task_service, task, suffix: str) -> dict:
    issue = {
        "issue_id": f"phase-a-p1-quality-{suffix}",
        "issue_type": "task_quality",
        "severity": "p1",
        "status": "open",
        "summary": "manual review found obvious task quality regression",
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_a_quality_issue": issue},
        remarks="Phase A P1 task quality issue recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_a_quality_issue"] == issue
    return issue


@pytest.mark.asyncio
async def test_q8_phase_a_observation_reports_exact_real_priority_decisions(real_ci_runtime) -> None:
    """查询链路：从真实 Q8 任务 metadata 汇总 Phase A 观察结果，必须逐项符合业务优先级规则。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-observe-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )

    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    assert {task.title for task in tasks} == {
        f"phase a high risk task {suffix}",
        f"phase a base priority task {suffix}",
    }

    report = build_q8_phase_a_observation_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=2,
    )

    assert report["observation_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["expected_task_count"] == 2
    assert report["observed_task_count"] == 2
    assert report["priority_counts"] == {"high": 1, "low": 1}
    assert report["queue_counts"] == {"blocked_self_tasks": 1, "next_self_tasks": 1}
    assert report["applied_rule_counts"] == {
        "base_q8_priority": 1,
        "risk_control_high_risk_to_high": 1,
    }
    assert report["q9_trace_counts"] == {f"trace-q9-phase-a-{suffix}": 2}
    assert report["average_evaluation_weights"] == {
        "accuracy": 0.25,
        "continuity": 0.2,
        "risk_control": 0.5,
        "speed": 0.05,
    }

    receipts_by_title = {receipt["title"]: receipt for receipt in report["receipts"]}
    risk_receipt = receipts_by_title[f"phase a high risk task {suffix}"]
    assert risk_receipt["base_priority"] == "medium"
    assert risk_receipt["final_priority"] == "high"
    assert risk_receipt["actual_priority"] == "high"
    assert risk_receipt["risk_level"] == "high"
    assert risk_receipt["applied_rules"] == ["risk_control_high_risk_to_high"]
    assert risk_receipt["q9_trace_id"] == f"trace-q9-phase-a-{suffix}"
    assert risk_receipt["evaluation_weights"]["risk_control"] == 0.5

    base_receipt = receipts_by_title[f"phase a base priority task {suffix}"]
    assert base_receipt["base_priority"] == "low"
    assert base_receipt["final_priority"] == "low"
    assert base_receipt["actual_priority"] == "low"
    assert base_receipt["risk_level"] == "low"
    assert base_receipt["applied_rules"] == ["base_q8_priority"]


@pytest.mark.asyncio
async def test_q8_phase_a_observation_fails_when_q9_profile_was_missing(real_ci_runtime) -> None:
    """异常链路：Q9 profile 缺失时可以同步任务，但 Phase A 观察必须 fail-closed，不得假装 ready。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, include_q9=False),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    assert {task.metadata["phase_a_evaluation"]["status"] for task in tasks} == {"missing"}

    with pytest.raises(Q8PhaseAObservationError) as exc_info:
        build_q8_phase_a_observation_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=2,
        )

    failures = exc_info.value.failures
    reasons = [failure["reason"] for failure in failures]
    assert reasons.count("phase_a_evaluation_not_ready") == 2
    assert reasons.count("q9_trace_id_missing") == 2
    assert reasons.count("applied_rules_missing") == 2
    assert reasons.count("evaluation_weight_missing") == 6
    assert sorted(
        failure["field"] for failure in failures if failure["reason"] == "evaluation_weight_missing"
    ) == [
        "accuracy",
        "accuracy",
        "continuity",
        "continuity",
        "risk_control",
        "risk_control",
    ]
    assert {failure["task_id"] for failure in failures} == {task.task_id for task in tasks}


@pytest.mark.asyncio
async def test_q8_phase_a_lens_distribution_reports_exact_real_dominant_lenses(real_ci_runtime) -> None:
    """查询链路：Phase A lens 分布必须来自真实 Q8/Q9 同步任务，逐 lens 证明主导激活。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-lens-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )

    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    assert {task.metadata["phase_a_evaluation"]["status"] for task in tasks} == {"ready"}
    assert {task.metadata["phase_a_evaluation"]["evaluation_style"] for task in tasks} == {
        f"{lens}_dominant" for lens in required_lenses
    }

    report = build_q8_phase_a_lens_distribution_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=5,
        required_lenses=required_lenses,
    )

    assert report["lens_distribution_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["observed_task_count"] == 5
    assert report["required_lenses"] == list(required_lenses)
    assert report["lens_activation_counts"] == {lens: 1 for lens in required_lenses}
    assert report["lens_positive_counts"] == {lens: 5 for lens in required_lenses}
    assert report["dominant_lens_coverage_ratio"] == 1.0
    assert report["task_status_counts"] == {"archived": 4, "todo": 1}
    assert sorted(report["q9_trace_counts"].values()) == [1, 1, 1, 1, 1]

    receipts_by_lens = {receipt["dominant_lenses"][0]: receipt for receipt in report["receipts"]}
    assert set(receipts_by_lens) == set(required_lenses)
    for lens in required_lenses:
        receipt = receipts_by_lens[lens]
        assert receipt["evaluation_weights"][lens] == 0.7
        assert receipt["max_weight"] == 0.7
        assert receipt["q9_trace_id"] == f"trace-q9-phase-a-lens-{lens}-{suffix}"


@pytest.mark.asyncio
async def test_q8_phase_a_lens_distribution_fails_when_required_lenses_are_not_activated(real_ci_runtime) -> None:
    """异常链路：只激活一个主导 lens 时，必须列出所有未激活 required lens，不能假装分布健康。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-lens-missing-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_lens_snapshot(session_id, suffix, "risk_control"),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 1
    assert tasks[0].metadata["phase_a_evaluation"]["evaluation_weights"]["risk_control"] == 0.7

    with pytest.raises(Q8PhaseALensDistributionError) as exc_info:
        build_q8_phase_a_lens_distribution_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
            required_lenses=required_lenses,
        )

    failures = exc_info.value.failures
    assert {
        failure["lens"] for failure in failures if failure["reason"] == "required_lens_not_activated"
    } == {"accuracy", "continuity", "speed", "creativity"}
    assert all(failure["reason"] != "lens_weight_missing" for failure in failures)


@pytest.mark.asyncio
async def test_q8_phase_a_observation_gate_passes_with_real_lens_trend_and_manual_reviews(real_ci_runtime) -> None:
    """查询门禁：lens 分布、权重趋势、人工抽查证据必须全部来自真实任务查询。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-gate-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(real_ci_runtime.task_service, tasks, suffix)

    report = build_q8_phase_a_observation_gate_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=5,
        required_lenses=required_lenses,
        minimum_manual_reviews=5,
        max_weight_delta=0.75,
        max_obvious_drift_rate=0.0,
    )

    assert report["observation_gate_status"] == "passed"
    assert report["lens_distribution"]["lens_activation_counts"] == {lens: 1 for lens in required_lenses}
    assert report["weight_trend"]["max_weight_delta_allowed"] == 0.75
    assert report["weight_trend"]["max_weight_delta_observed"] == 0.6
    assert report["weight_trend"]["shift_count"] == 4
    assert report["manual_review"]["reviewed_count"] == 5
    assert report["manual_review"]["obvious_drift_count"] == 0
    assert len(report["manual_review"]["receipts"]) == 5


@pytest.mark.asyncio
async def test_q8_phase_a_observation_gate_fails_on_real_weight_shift(real_ci_runtime) -> None:
    """异常门禁：真实任务权重突变超过阈值时必须 fail-closed，不能只看 lens 覆盖通过。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-gate-shift-{suffix}"
    required_lenses = ("accuracy", "risk_control")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2

    with pytest.raises(Q8PhaseAObservationGateError) as exc_info:
        build_q8_phase_a_observation_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=2,
            required_lenses=required_lenses,
            max_weight_delta=0.2,
        )

    failures = exc_info.value.failures
    shift_failures = [failure for failure in failures if failure["reason"] == "evaluation_weight_shift_too_large"]
    assert len(shift_failures) == 1
    assert shift_failures[0]["delta"] == 0.6
    assert shift_failures[0]["max_allowed"] == 0.2


@pytest.mark.asyncio
async def test_q8_phase_a_observation_gate_fails_on_real_manual_review_drift(real_ci_runtime) -> None:
    """异常门禁：真实写入人工抽查 obvious_drift 后，查询门禁必须按漂移率阻断。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-gate-review-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_lens_snapshot(session_id, suffix, "risk_control"),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 1
    await _write_manual_reviews(real_ci_runtime.task_service, tasks, suffix, obvious_drift=True)

    with pytest.raises(Q8PhaseAObservationGateError) as exc_info:
        build_q8_phase_a_observation_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
            required_lenses=("risk_control",),
            minimum_manual_reviews=1,
            max_obvious_drift_rate=0.0,
        )

    failures = exc_info.value.failures
    assert [failure["reason"] for failure in failures] == ["manual_review_obvious_drift_rate_too_high"]
    assert failures[0]["obvious_drift_rate"] == 1.0


@pytest.mark.asyncio
async def test_q8_phase_a_exit_gate_allows_phase_b_skip_after_real_observation_gate(real_ci_runtime) -> None:
    """Phase A 退出门禁：真实观察门禁通过且无 P1 质量问题时，才允许跳过 Phase B。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-exit-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(real_ci_runtime.task_service, tasks, suffix)

    report = build_q8_phase_a_exit_gate_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=5,
        required_lenses=required_lenses,
        minimum_manual_reviews=5,
        max_weight_delta=0.75,
        max_obvious_drift_rate=0.0,
    )

    assert report["phase_a_exit_status"] == "passed"
    assert report["phase_b_skip_allowed"] is True
    assert report["phase_b_required"] is False
    assert report["quality_issues"]["open_p1_quality_issue_count"] == 0
    assert report["observation_gate"]["manual_review"]["reviewed_count"] == 5


@pytest.mark.asyncio
async def test_q8_phase_a_exit_gate_requires_phase_b_when_real_p1_quality_issue_is_open(real_ci_runtime) -> None:
    """异常退出门禁：真实写入开放 P1 task quality issue 后，必须阻断跳过 Phase B。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-exit-p1-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(real_ci_runtime.task_service, tasks, suffix)
    issue = await _write_open_quality_issue(real_ci_runtime.task_service, tasks[0], suffix)

    with pytest.raises(Q8PhaseAExitGateError) as exc_info:
        build_q8_phase_a_exit_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=5,
            required_lenses=required_lenses,
            minimum_manual_reviews=5,
            max_weight_delta=0.75,
            max_obvious_drift_rate=0.0,
        )

    failures = exc_info.value.failures
    assert failures == [
        {
            "reason": "phase_a_open_p1_quality_issue_limit_exceeded",
            "open_p1_quality_issue_count": 1,
            "max_allowed": 0,
        }
    ]
    refreshed = real_ci_runtime.task_service.get_task(tasks[0].task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_a_quality_issue"] == issue
