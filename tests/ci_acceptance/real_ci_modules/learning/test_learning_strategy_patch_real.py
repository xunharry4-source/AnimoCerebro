from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.learning.strategy_patch import (
    StrategyPatchApprovalError,
    build_strategy_patches_from_experience_candidates,
    record_strategy_patch_approval,
)


def _record_experience_candidate(learning_service, *, suffix: str, candidate_type: str, task_id: str):
    candidate = {
        "candidate_id": f"experience-candidate:{task_id}",
        "candidate_type": candidate_type,
        "task_id": task_id,
        "task_title": f"{candidate_type} source task {suffix}",
        "question_id": "q8",
        "source_trace_id": f"trace-{candidate_type}-{suffix}",
        "overall_passed": candidate_type == "success_pattern",
        "actual_outcome": {"task_id": task_id, "candidate_type": candidate_type},
        "failed_verifiers": ["q8_required_outcome_evidence"] if candidate_type == "failure_pattern" else [],
    }
    return learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="experience_candidate",
        trace_id=f"phase-c-experience-candidate-v1:{task_id}",
        detail={
            "source": "phase_c_experience_candidate_promotion",
            "candidate_version": "phase-c-experience-candidate-v1",
            "candidate": candidate,
            "task_id": task_id,
            "candidate_id": candidate["candidate_id"],
            "candidate_type": candidate_type,
        },
    )


def test_strategy_patch_builds_and_records_real_human_approval(real_ci_runtime) -> None:
    suffix = unique_suffix()
    success = _record_experience_candidate(
        real_ci_runtime.learning_service,
        suffix=suffix,
        candidate_type="success_pattern",
        task_id=f"strategy-success-{suffix}",
    )
    failure = _record_experience_candidate(
        real_ci_runtime.learning_service,
        suffix=suffix,
        candidate_type="failure_pattern",
        task_id=f"strategy-failure-{suffix}",
    )
    assert success.trace_id
    assert failure.trace_id

    report = build_strategy_patches_from_experience_candidates(
        learning_service=real_ci_runtime.learning_service,
        candidate_version="phase-c-experience-candidate-v1",
        required_candidate_count=2,
    )

    assert report["strategy_patch_status"] == "pending_approval"
    assert report["candidate_count"] >= 2
    patches_by_task = {patch["source_task_id"]: patch for patch in report["patches"]}
    success_patch = patches_by_task[f"strategy-success-{suffix}"]
    failure_patch = patches_by_task[f"strategy-failure-{suffix}"]
    assert success_patch["patch_type"] == "reinforce_success_pattern"
    assert success_patch["status"] == "pending_approval"
    assert success_patch["rollback"]["strategy"] == "discard_patch_before_activation"
    assert failure_patch["patch_type"] == "tighten_acceptance_contract"

    approval = record_strategy_patch_approval(
        learning_service=real_ci_runtime.learning_service,
        patch=failure_patch,
        approver_id=f"phase-c-approver-{suffix}",
        decision="approved",
        approval_evidence=[f"approved after reviewing candidate {failure_patch['source_candidate_id']}"],
    )

    assert approval["strategy_patch_approval_status"] == "approved"
    assert approval["patch_id"] == failure_patch["patch_id"]
    assert approval["approval"]["approver_id"] == f"phase-c-approver-{suffix}"
    assert approval["approval"]["approval_evidence"] == [
        f"approved after reviewing candidate {failure_patch['source_candidate_id']}"
    ]
    rows = real_ci_runtime.learning_service.query_overall_records(
        limit=20,
        trace_id=approval["learning_trace_id"],
    )
    matching = [row for row in rows if row.detail.get("patch_id") == failure_patch["patch_id"]]
    assert len(matching) == 1
    assert matching[0].detail["learning_kind"] == "strategy_patch_approval"
    assert matching[0].detail["approval"]["decision"] == "approved"


def test_strategy_patch_approval_requires_real_evidence_and_valid_decision(real_ci_runtime) -> None:
    suffix = unique_suffix()
    _record_experience_candidate(
        real_ci_runtime.learning_service,
        suffix=suffix,
        candidate_type="failure_pattern",
        task_id=f"strategy-invalid-{suffix}",
    )
    report = build_strategy_patches_from_experience_candidates(
        learning_service=real_ci_runtime.learning_service,
        candidate_version="phase-c-experience-candidate-v1",
        required_candidate_count=1,
    )
    patch = next(item for item in report["patches"] if item["source_task_id"] == f"strategy-invalid-{suffix}")

    with pytest.raises(StrategyPatchApprovalError) as exc_info:
        record_strategy_patch_approval(
            learning_service=real_ci_runtime.learning_service,
            patch=patch,
            approver_id="",
            decision="auto_approved",
            approval_evidence=[],
        )

    assert exc_info.value.failures == [
        {"reason": "strategy_patch_approver_missing"},
        {"reason": "strategy_patch_approval_decision_invalid", "decision": "auto_approved"},
        {"reason": "strategy_patch_approval_evidence_missing"},
    ]
    rows = real_ci_runtime.learning_service.query_overall_records(limit=200)
    assert all(
        row.detail.get("patch_id") != patch["patch_id"]
        or row.detail.get("learning_kind") != "strategy_patch_approval"
        for row in rows
    )
