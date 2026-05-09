from __future__ import annotations

from typing import Any


class StrategyPatchApprovalError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("StrategyPatch approval failed")


VALID_APPROVAL_DECISIONS = {"approved", "rejected"}


def build_strategy_patches_from_experience_candidates(
    *,
    learning_service: Any,
    candidate_version: str = "phase-c-experience-candidate-v1",
    required_candidate_count: int = 1,
    limit: int = 200,
) -> dict[str, Any]:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise StrategyPatchApprovalError([{"reason": "learning_service_query_missing"}])
    if required_candidate_count <= 0:
        raise StrategyPatchApprovalError([{"reason": "required_candidate_count_must_be_positive"}])

    candidates = []
    for row in learning_service.query_overall_records(limit=limit):
        detail = dict(row.detail or {})
        if detail.get("learning_kind") != "experience_candidate":
            continue
        if detail.get("candidate_version") != candidate_version:
            continue
        candidate = dict(detail.get("candidate") or {})
        if not candidate.get("candidate_id") or not candidate.get("task_id"):
            continue
        candidates.append((row, candidate))

    if len(candidates) < required_candidate_count:
        raise StrategyPatchApprovalError(
            [
                {
                    "reason": "experience_candidate_count_below_required",
                    "required": required_candidate_count,
                    "actual": len(candidates),
                }
            ]
        )

    patches = [_patch_from_candidate(row=row, candidate=candidate) for row, candidate in candidates]
    return {
        "strategy_patch_status": "pending_approval",
        "candidate_version": candidate_version,
        "candidate_count": len(candidates),
        "patch_count": len(patches),
        "patches": patches,
    }


def record_strategy_patch_approval(
    *,
    learning_service: Any,
    patch: dict[str, Any],
    approver_id: str,
    decision: str,
    approval_evidence: list[str],
) -> dict[str, Any]:
    failures = _validate_approval_inputs(
        learning_service=learning_service,
        patch=patch,
        approver_id=approver_id,
        decision=decision,
        approval_evidence=approval_evidence,
    )
    if failures:
        raise StrategyPatchApprovalError(failures)

    patch_id = str(patch["patch_id"])
    trace_id = f"strategy-patch-approval:{patch_id}:{decision}"
    learning = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="strategy_patch_approval",
        trace_id=trace_id,
        detail={
            "source": "phase_c_strategy_patch_approval",
            "patch_id": patch_id,
            "patch": patch,
            "approval": {
                "approver_id": approver_id,
                "decision": decision,
                "approval_evidence": list(approval_evidence),
            },
        },
    )
    learning_trace_id = str(getattr(learning, "trace_id", "") or "")
    rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matches = [
        row
        for row in rows
        if row.detail.get("patch_id") == patch_id
        and dict(row.detail.get("approval") or {}).get("decision") == decision
    ]
    if len(matches) != 1:
        raise StrategyPatchApprovalError(
            [
                {
                    "reason": "strategy_patch_approval_query_mismatch",
                    "patch_id": patch_id,
                    "learning_trace_id": learning_trace_id,
                    "match_count": len(matches),
                }
            ]
        )
    return {
        "strategy_patch_approval_status": decision,
        "patch_id": patch_id,
        "learning_trace_id": learning_trace_id,
        "approval": matches[0].detail["approval"],
    }


def _patch_from_candidate(*, row: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_type = str(candidate.get("candidate_type") or "")
    task_id = str(candidate.get("task_id") or "")
    if candidate_type == "failure_pattern":
        patch_type = "tighten_acceptance_contract"
        recommendation = "Require explicit evidence before accepting similar Q8 task outcomes."
    else:
        patch_type = "reinforce_success_pattern"
        recommendation = "Prefer similar Q8 tasks when objective, evidence, and outcome match."
    return {
        "patch_id": f"strategy-patch:{candidate.get('candidate_id')}",
        "patch_type": patch_type,
        "target": "q8_task_generation_policy",
        "status": "pending_approval",
        "source_candidate_id": candidate.get("candidate_id"),
        "source_task_id": task_id,
        "source_learning_trace_id": str(getattr(row, "trace_id", "") or ""),
        "candidate_type": candidate_type,
        "recommendation": recommendation,
        "rollback": {
            "strategy": "discard_patch_before_activation",
            "source_task_id": task_id,
        },
    }


def _validate_approval_inputs(
    *,
    learning_service: Any,
    patch: dict[str, Any],
    approver_id: str,
    decision: str,
    approval_evidence: list[str],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        failures.append({"reason": "learning_service_record_missing"})
    if learning_service is not None and not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if not isinstance(patch, dict) or not str(patch.get("patch_id") or "").strip():
        failures.append({"reason": "strategy_patch_id_missing"})
    if not str(approver_id or "").strip():
        failures.append({"reason": "strategy_patch_approver_missing"})
    if decision not in VALID_APPROVAL_DECISIONS:
        failures.append({"reason": "strategy_patch_approval_decision_invalid", "decision": decision})
    if not isinstance(approval_evidence, list) or not approval_evidence or not all(str(item).strip() for item in approval_evidence):
        failures.append({"reason": "strategy_patch_approval_evidence_missing"})
    return failures
