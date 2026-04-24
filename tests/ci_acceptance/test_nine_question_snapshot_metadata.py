from __future__ import annotations

import pytest

from zentex.nine_questions.query import COMPOSED_RECORD_SCHEMA_VERSION
from zentex.nine_questions.service import NineQuestionService


@pytest.mark.asyncio
async def test_persist_kernel_state_backfills_snapshot_metadata(acceptance_app):
    service = acceptance_app.state.nine_question_service
    state_manager = service._state_manager

    kernel_state = {
        "question_snapshots": {
            "q2": {
                "tool_id": "nine-question-q2-who-am-i",
                "summary": "q2 summary",
                "confidence": 0.88,
                "result": {"role": "assistant"},
                "context_updates": {},
                "trace_id": "q2:test-trace",
            },
            "q8": {
                "tool_id": "nine_question_q8_decision",
                "summary": "q8 summary",
                "confidence": 0.91,
                "result": {"objective_profile": {"current_mission": "x"}},
                "context_updates": {},
                "trace_id": "q8:test-trace",
                "timestamp": "2026-04-23T00:45:07.194314+00:00",
            },
        },
        "snapshot_version": 2,
        "dirty_questions": [],
        "last_refresh_reason": "metadata-test",
    }

    await service.persist_kernel_state(kernel_state)
    persisted = await state_manager.get_state("nq-baseline")

    for question_id in ("q2", "q8"):
        snapshot = persisted["question_snapshots"][question_id]
        assert str(snapshot.get("timestamp") or "").strip()
        assert str(snapshot.get("generated_at") or "").strip()
        assert str(snapshot.get("updated_at") or "").strip()
        assert int(snapshot.get("snapshot_schema_version") or 0) >= COMPOSED_RECORD_SCHEMA_VERSION

    q2_snapshot = persisted["question_snapshots"]["q2"]
    assert q2_snapshot["generated_at"] == q2_snapshot["timestamp"]


def _snapshot_with_diagnosis(
    *,
    trace_id: str,
    summary: str,
    authenticity_status: str,
    module_statuses: dict[str, str],
) -> dict:
    module_runs = [
        {"module_id": module_id, "status": status, "data": {"value": module_id}}
        for module_id, status in module_statuses.items()
    ]
    diagnosis = {
        "authenticity_status": authenticity_status,
        "snapshot_fallback_used": False,
        "used_fallback": False,
        "module_runs": module_runs,
    }
    return {
        "tool_id": "nine-question-q1-where-am-i",
        "summary": summary,
        "confidence": 0.9 if authenticity_status == "completed" else 0.0,
        "trace_id": trace_id,
        "result": {"status": authenticity_status, "context_updates": {"q1_execution_diagnosis": diagnosis}},
        "context_updates": {"q1_execution_diagnosis": diagnosis},
    }


def test_failed_snapshot_does_not_replace_existing_qualified_snapshot():
    existing = _snapshot_with_diagnosis(
        trace_id="q1:existing-success",
        summary="primary_domain=software; confidence=0.91; status=completed",
        authenticity_status="completed",
        module_statuses={
            "dependency_check": "completed",
            "domain_inference": "completed",
        },
    )
    failed_candidate = _snapshot_with_diagnosis(
        trace_id="q1:bad-llm-rerun",
        summary="Q1 partial failure: Unknown provider tool: __bad_llm_provider__",
        authenticity_status="completed",
        module_statuses={
            "q1_audit_integration": "completed",
            "q1_memory_integration": "completed",
            "q1_reflection_integration": "completed",
            "q1_learning_integration": "completed",
            "dependency_check": "completed",
            "workspace_structure_scan": "completed",
            "content_sampling": "completed",
            "functional_plugin_chain": "completed",
            "environment_scan": "completed",
            "domain_inference": "partial_failed",
            "uncertainty_projection": "partial_failed",
            "state_write": "partial_failed",
        },
    )

    decision = NineQuestionService._should_accept_new_snapshot(existing, failed_candidate)

    assert decision == {
        "accept_snapshot": False,
        "merge_diagnostics_only": True,
        "preserve_previous_success": True,
        "reason": "existing_snapshot_qualified_new_snapshot_unqualified",
    }


def test_rejected_snapshot_diagnostics_do_not_overwrite_canonical_diagnosis():
    existing = _snapshot_with_diagnosis(
        trace_id="q1:existing-success",
        summary="primary_domain=software; confidence=0.91; status=completed",
        authenticity_status="completed",
        module_statuses={
            "dependency_check": "completed",
            "domain_inference": "completed",
        },
    )
    failed_candidate = _snapshot_with_diagnosis(
        trace_id="q1:bad-llm-rerun",
        summary="Q1 partial failure: Unknown provider tool: __bad_llm_provider__",
        authenticity_status="completed",
        module_statuses={
            "dependency_check": "completed",
            "domain_inference": "partial_failed",
        },
    )

    merged = NineQuestionService._merge_diagnostic_only(existing, failed_candidate)

    canonical = merged["context_updates"]["q1_execution_diagnosis"]
    assert [item["status"] for item in canonical["module_runs"]] == ["completed", "completed"]
    rejected = merged["context_updates"]["q1_rejected_execution_diagnosis"]
    assert [item["status"] for item in rejected["module_runs"]] == ["completed", "partial_failed"]
