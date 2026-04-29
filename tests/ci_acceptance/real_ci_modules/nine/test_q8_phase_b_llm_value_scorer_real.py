from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.llm.service import get_service as get_llm_service
from zentex.nine_questions.q8_phase_b_llm_value_scorer import (
    Q8PhaseBLLMValueScoringError,
    build_q8_phase_b_llm_value_score_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "phase b llm scorer",
        "resource_context": "real semantic value scoring",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_llm_scoring",
        "action_rhythm_hint": "llm_score_edge_case_after_real_outcome",
    }
    return {
        "trace_id": f"trace-q9-phase-b-llm-score-{suffix}",
        "summary": "Q9 Phase B LLM score profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 1) -> dict:
    rows = [
        {
            "task_id": f"phase-b-llm-score-{suffix}-{index}",
            "title": f"phase b LLM value score task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["semantic scorer can verify concrete user value"],
            "expected_outcome": {
                "score_index": index,
                "session_id": session_id,
                "user_value": "documented reduction in user verification effort",
            },
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-llm-score-{suffix}",
            "summary": "Q8 Phase B LLM scoring test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b LLM scoring mission {suffix}",
                    "primary_objectives": ["score semantic value for Q8 edge tasks"],
                    "secondary_objectives": ["preserve independent LLM evidence"],
                    "completion_conditions": ["LLM value score is recorded"],
                    "pause_conditions": ["missing task outcome"],
                    "escalation_conditions": ["LLM scorer rejects edge task"],
                },
                "q8_task_queue": {
                    "next_self_tasks": rows,
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        },
        "q9": _q9_snapshot(suffix),
    }


async def _complete_with_good_outcome(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
                "evidence": [
                    f"real semantic value evidence for {task.task_id}",
                    "user verification steps reduced from manual checklist to single scored receipt",
                ],
                "user_value": "The user can decide whether the Q8 task is useful without re-reading raw execution logs.",
            },
            "evidence": [f"real phase b LLM scoring receipt for {task.task_id}"],
        },
        remarks="phase b LLM value scoring source outcome",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["task_id"] == task.task_id
    assert persisted["actual_outcome"]["evidence"]


async def _mark_llm_review_required(task_service, task, suffix: str) -> dict:
    marker = {
        "required": True,
        "source": "phase_b_rule_edge_case",
        "reason": "rule score confidence was borderline and requires independent semantic review",
        "marked_by": f"phase-b-llm-test-{suffix}",
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_b_llm_review": marker},
        remarks="Phase B LLM edge review marker recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_llm_review"] == marker
    return marker


@pytest.mark.asyncio
async def test_q8_phase_b_llm_value_scorer_calls_real_ollama_for_edge_task(real_ci_runtime) -> None:
    """查询链路：Layer 2 必须用真实 LLM service 评分真实 Q8 边缘任务 outcome。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-llm-score-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _mark_llm_review_required(real_ci_runtime.task_service, task, suffix)
    await _complete_with_good_outcome(real_ci_runtime.task_service, task)

    report = build_q8_phase_b_llm_value_score_report(
        task_service=real_ci_runtime.task_service,
        llm_service=get_llm_service(),
        session_id=session_id,
        expected_task_count=1,
        expected_review_count=1,
        generation_provider_key="acceptance-provider",
        scoring_provider_key="ollama",
        scoring_model="deepseek-r1:14b",
        sample_count=1,
        minimum_semantic_score=0.50,
        minimum_confidence=0.30,
    )

    assert report["value_score_status"] == "passed"
    assert report["scorer_layer"] == "phase_b_llm"
    assert report["session_id"] == session_id
    assert report["generation_provider_key"] == "acceptance-provider"
    assert report["scoring_provider_key"] == "ollama"
    assert report["scoring_model"] == "deepseek-r1:14b"
    assert report["reviewed_task_count"] == 1
    receipt = report["receipts"][0]
    assert receipt["task_id"] == task.task_id
    assert receipt["q8_trace_id"] == task.metadata["trace_id"]
    assert receipt["q9_trace_id"] == task.metadata["phase_a_evaluation"]["source_trace_id"]
    assert receipt["provider_key"] == "ollama"
    assert receipt["model"] == "deepseek-r1:14b"
    assert receipt["outcome_passed"] is True
    assert 0.0 <= receipt["semantic_score"] <= 1.0
    assert 0.0 <= receipt["confidence"] <= 1.0
    assert receipt["semantic_score"] >= 0.50
    assert receipt["confidence"] >= 0.30
    assert receipt["decision"] in {"accept", "downgrade"}
    assert len(receipt["samples"]) == 1
    assert receipt["samples"][0]["provider_key"] == "ollama"
    assert receipt["samples"][0]["model"] == "deepseek-r1:14b"


@pytest.mark.asyncio
async def test_q8_phase_b_llm_value_scorer_fails_when_provider_is_not_isolated(real_ci_runtime) -> None:
    """异常链路：评分 provider 与生成 provider 相同必须 fail-closed，禁止自评。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-llm-same-provider-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _mark_llm_review_required(real_ci_runtime.task_service, task, suffix)
    await _complete_with_good_outcome(real_ci_runtime.task_service, task)

    with pytest.raises(Q8PhaseBLLMValueScoringError) as exc_info:
        build_q8_phase_b_llm_value_score_report(
            task_service=real_ci_runtime.task_service,
            llm_service=get_llm_service(),
            session_id=session_id,
            expected_task_count=1,
            expected_review_count=1,
            generation_provider_key="ollama",
            scoring_provider_key="ollama",
            scoring_model="deepseek-r1:14b",
            sample_count=1,
        )

    assert exc_info.value.failures == [
        {"reason": "llm_scorer_not_isolated_from_generation", "provider_key": "ollama"}
    ]


@pytest.mark.asyncio
async def test_q8_phase_b_llm_value_scorer_fails_when_review_marker_missing(real_ci_runtime) -> None:
    """边界链路：没有真实 edge marker 时，expected_review_count 必须阻断假评分。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-llm-no-marker-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _complete_with_good_outcome(real_ci_runtime.task_service, task)

    with pytest.raises(Q8PhaseBLLMValueScoringError) as exc_info:
        build_q8_phase_b_llm_value_score_report(
            task_service=real_ci_runtime.task_service,
            llm_service=get_llm_service(),
            session_id=session_id,
            expected_task_count=1,
            expected_review_count=1,
            generation_provider_key="acceptance-provider",
            scoring_provider_key="ollama",
            scoring_model="deepseek-r1:14b",
            sample_count=1,
        )

    assert exc_info.value.failures == [
        {"reason": "llm_review_count_mismatch", "expected": 1, "actual": 0}
    ]
