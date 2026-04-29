from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_b_realtime_gate import Q8PhaseBRealtimeGateError
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str, *, gate_config: dict) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-realtime-{suffix}",
            "summary": "Q8 Phase B realtime gate test",
            "context_updates": {
                "phase_b_realtime_gate": gate_config,
                "q8_objective_profile": {
                    "current_mission": f"phase b realtime gate mission {suffix}",
                    "primary_objectives": ["apply realtime value scoring before persistence"],
                    "secondary_objectives": ["preserve gate decision evidence"],
                    "completion_conditions": ["task value gate metadata is queryable"],
                    "pause_conditions": ["value gate rejects task"],
                    "escalation_conditions": ["realtime gate configuration invalid"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-b-realtime-accept-{suffix}",
                            "title": f"verify automated release evidence package {suffix}",
                            "reason": "自动化验证 evidence package，减少人工返工并阻断无证据发布",
                            "priority": "high",
                            "expected_outcome": {"artifact": "release_evidence_package"},
                            "success_criteria": ["evidence package verified"],
                            "acceptance_conditions": ["release evidence has trace id"],
                            "risk_assessment": {"risk_level": "high"},
                            "pause_conditions": ["evidence missing risk"],
                            "escalation_conditions": ["escalate when approval evidence is missing"],
                        },
                        {
                            "task_id": f"phase-b-realtime-downgrade-{suffix}",
                            "title": f"inspect deployment note for operator handoff {suffix}",
                            "reason": "handoff note",
                            "priority": "high",
                            "expected_outcome": {"artifact": "handoff_note"},
                            "success_criteria": ["handoff note inspected"],
                            "risk_assessment": {"risk_level": "high"},
                        },
                        {
                            "task_id": f"phase-b-realtime-reject-{suffix}",
                            "title": "do it",
                            "priority": "medium",
                            "risk_assessment": {"risk_level": "low"},
                        },
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


@pytest.mark.asyncio
async def test_q8_phase_b_realtime_gate_applies_accept_downgrade_and_reject_before_persistence(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-realtime-{suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(
            session_id,
            suffix,
            gate_config={
                "enabled": True,
                "accept_threshold": 0.75,
                "reject_threshold": 0.4,
            },
        ),
    )

    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 3
    by_id = {task.metadata["expected_outcome"].get("artifact", task.title): task for task in tasks}

    accepted = by_id["release_evidence_package"]
    accepted_gate = accepted.metadata["phase_b_realtime_gate"]
    assert accepted.status.value == "todo"
    assert accepted.priority.value == "high"
    assert accepted_gate["decision"] == "accept"
    assert accepted_gate["overall_score"] == 1.0
    assert accepted_gate["dimensions"] == {
        "title_specificity": 1.0,
        "value_mechanism": 1.0,
        "acceptance_contract": 1.0,
        "risk_control": 1.0,
    }
    assert accepted_gate["final_status"] == "todo"
    assert accepted_gate["final_priority"] == "high"

    downgraded = by_id["handoff_note"]
    downgraded_gate = downgraded.metadata["phase_b_realtime_gate"]
    assert downgraded.status.value == "todo"
    assert downgraded.priority.value == "medium"
    assert downgraded_gate["decision"] == "downgrade"
    assert downgraded_gate["overall_score"] == 0.5
    assert downgraded_gate["dimension_failures"]["value_mechanism"] == [
        "value_mechanism_missing"
    ]
    assert downgraded_gate["dimension_failures"]["risk_control"] == [
        "high_risk_control_missing"
    ]
    assert downgraded_gate["original_priority"] == "high"
    assert downgraded_gate["final_priority"] == "medium"

    rejected = next(task for task in tasks if task.title == "do it")
    rejected_gate = rejected.metadata["phase_b_realtime_gate"]
    assert rejected.status.value == "blocked"
    assert rejected.priority.value == "low"
    assert rejected_gate["decision"] == "reject"
    assert rejected_gate["overall_score"] == 0.25
    assert rejected_gate["dimension_failures"]["title_specificity"] == ["title_too_short"]
    assert rejected_gate["dimension_failures"]["value_mechanism"] == [
        "value_mechanism_missing"
    ]
    assert rejected_gate["dimension_failures"]["acceptance_contract"] == [
        "acceptance_contract_incomplete"
    ]
    assert rejected_gate["final_status"] == "blocked"


@pytest.mark.asyncio
async def test_q8_phase_b_realtime_gate_disabled_preserves_original_sync_behavior(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-realtime-disabled-{suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(
            session_id,
            suffix,
            gate_config={"enabled": False},
        ),
    )

    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 3
    rejected_candidate = next(task for task in tasks if task.title == "do it")
    assert rejected_candidate.status.value == "todo"
    assert rejected_candidate.priority.value == "medium"
    assert "phase_b_realtime_gate" not in rejected_candidate.metadata


@pytest.mark.asyncio
async def test_q8_phase_b_realtime_gate_invalid_threshold_fails_before_creating_tasks(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-realtime-invalid-{suffix}"

    with pytest.raises(Q8PhaseBRealtimeGateError) as exc_info:
        await sync_q8_tasks_to_task_service(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            snapshot_map=_snapshot(
                session_id,
                suffix,
                gate_config={
                    "enabled": True,
                    "accept_threshold": 0.5,
                    "reject_threshold": 0.8,
                },
            ),
        )

    assert exc_info.value.failures == [
        {
            "reason": "reject_threshold_above_accept_threshold",
            "reject_threshold": 0.8,
            "accept_threshold": 0.5,
        }
    ]
    assert real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id}) == []
