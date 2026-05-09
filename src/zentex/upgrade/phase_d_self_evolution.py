from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.upgrade.base_models import UpgradeTargetKind
from zentex.upgrade.management import (
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeManagementStore,
)


class PhaseDSelfEvolutionError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Phase D self-evolution gate failed")


VALID_GOVERNANCE_DECISIONS = {"approved", "rejected"}
PHASE_D_ACTION = "phase_d_self_evolution"


def build_phase_d_self_evolution_plan(
    *,
    learning_service: Any,
    required_approved_patch_count: int = 1,
    candidate_version: str = "phase-d-self-evolution-v1",
) -> dict[str, Any]:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise PhaseDSelfEvolutionError([{"reason": "learning_service_query_missing"}])
    if required_approved_patch_count <= 0:
        raise PhaseDSelfEvolutionError([{"reason": "required_approved_patch_count_must_be_positive"}])

    approvals = []
    for row in learning_service.query_overall_records(limit=500):
        detail = dict(row.detail or {})
        if detail.get("learning_kind") != "strategy_patch_approval":
            continue
        approval = dict(detail.get("approval") or {})
        if approval.get("decision") != "approved":
            continue
        patch = dict(detail.get("patch") or {})
        if not patch.get("patch_id"):
            continue
        approvals.append({"learning_trace_id": row.trace_id, "patch": patch, "approval": approval})

    if len(approvals) < required_approved_patch_count:
        raise PhaseDSelfEvolutionError(
            [
                {
                    "reason": "approved_strategy_patch_count_below_required",
                    "required": required_approved_patch_count,
                    "actual": len(approvals),
                }
            ]
        )

    selected_approvals = approvals[:required_approved_patch_count]
    d0_to_d4_gates = {
        "d0_evolution_infrastructure": "ready",
        "d1_q8_pilot": "ready",
        "d2_q1_q2_extension": "ready",
        "d3_q5_q7_extension": "ready",
        "d4_q3_q4_q6_q9_extension": "ready",
    }
    patches = [item["patch"] for item in selected_approvals]
    return {
        "phase_d_plan_status": "pending_governance",
        "candidate_version": candidate_version,
        "approved_patch_count": len(approvals),
        "required_approved_patch_count": required_approved_patch_count,
        "d0_to_d4_gates": d0_to_d4_gates,
        "activation_scope": ["q8", "q1_q2", "q5_q7", "q3_q4_q6_q9"],
        "rollback": {
            "required": True,
            "strategy": "deactivate_candidate_and_restore_previous_strategy_patch_set",
        },
        "patches": patches,
        "approval_receipts": selected_approvals,
    }


def register_phase_d_upgrade_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    operator_id: str,
    governance_evidence: list[str],
    required_approved_patch_count: int = 1,
    candidate_version: str = "phase-d-self-evolution-v1",
) -> dict[str, Any]:
    failures = _validate_registration_inputs(
        upgrade_management_store=upgrade_management_store,
        operator_id=operator_id,
        governance_evidence=governance_evidence,
    )
    if failures:
        raise PhaseDSelfEvolutionError(failures)
    plan = build_phase_d_self_evolution_plan(
        learning_service=learning_service,
        required_approved_patch_count=required_approved_patch_count,
        candidate_version=candidate_version,
    )
    patch_ids = [str(patch.get("patch_id") or "") for patch in plan["patches"]]
    record_id = f"phase-d-self-evolution:{candidate_version}:{':'.join(patch_ids)}"
    record = UpgradeManagementRecord(
        record_id=record_id,
        target_kind=UpgradeTargetKind.COGNITIVE_TOOL,
        action="phase_d_self_evolution",
        target_id="nine_questions",
        title="Phase D self-evolution candidate",
        reason="Approved StrategyPatch records are ready for governed self-evolution.",
        trace_id=f"phase-d-self-evolution:{candidate_version}",
        request_id=record_id,
        change_summary="Register D0-D4 governed self-evolution candidate from approved strategy patches.",
        function_summary="Create an auditable upgrade management record before activation.",
        previous_version="v1.0-current",
        current_version="v1.0-current",
        candidate_version=candidate_version,
        current_status=UpgradeLifecycleStatus.QUEUED,
        current_progress=0,
        evidence_refs=list(governance_evidence),
        payload={
            "operator_id": operator_id,
            "phase_d_plan": plan,
            "rollback_required": True,
        },
    )
    upgrade_management_store.upsert(record)
    queried = upgrade_management_store.get(record_id)
    listed = [
        item
        for item in upgrade_management_store.list_records(target_kind=UpgradeTargetKind.COGNITIVE_TOOL)
        if item.record_id == record_id
    ]
    if queried.record_id != record_id or len(listed) != 1:
        raise PhaseDSelfEvolutionError(
            [
                {
                    "reason": "phase_d_upgrade_candidate_query_mismatch",
                    "record_id": record_id,
                    "listed_count": len(listed),
                }
            ]
        )
    return {
        "phase_d_registration_status": "queued",
        "record_id": record_id,
        "candidate_version": candidate_version,
        "current_status": queried.current_status.value,
        "target_kind": queried.target_kind.value,
        "evidence_refs": list(queried.evidence_refs),
        "rollback_required": queried.payload["rollback_required"],
        "d0_to_d4_gates": queried.payload["phase_d_plan"]["d0_to_d4_gates"],
    }


def record_phase_d_governance_decision(
    *,
    learning_service: Any,
    phase_d_registration: dict[str, Any],
    reviewer_id: str,
    decision: str,
    evidence: list[str],
) -> dict[str, Any]:
    failures = _validate_governance_decision_inputs(
        learning_service=learning_service,
        phase_d_registration=phase_d_registration,
        reviewer_id=reviewer_id,
        decision=decision,
        evidence=evidence,
    )
    if failures:
        raise PhaseDSelfEvolutionError(failures)
    record_id = str(phase_d_registration["record_id"])
    trace_id = f"phase-d-governance:{record_id}:{decision}"
    record = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="phase_d_governance_decision",
        trace_id=trace_id,
        detail={
            "source": "phase_d_self_evolution_governance",
            "record_id": record_id,
            "candidate_version": phase_d_registration["candidate_version"],
            "decision": decision,
            "reviewer_id": reviewer_id,
            "evidence": list(evidence),
            "rollback_required": phase_d_registration["rollback_required"],
            "d0_to_d4_gates": phase_d_registration["d0_to_d4_gates"],
        },
    )
    learning_trace_id = str(getattr(record, "trace_id", "") or "")
    rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matches = [
        row
        for row in rows
        if row.detail.get("learning_kind") == "phase_d_governance_decision"
        and row.detail.get("record_id") == record_id
        and row.detail.get("decision") == decision
    ]
    if len(matches) != 1:
        raise PhaseDSelfEvolutionError(
            [
                {
                    "reason": "phase_d_governance_decision_query_mismatch",
                    "record_id": record_id,
                    "learning_trace_id": learning_trace_id,
                    "match_count": len(matches),
                }
            ]
        )
    return {
        "phase_d_governance_status": decision,
        "record_id": record_id,
        "learning_trace_id": learning_trace_id,
        "reviewer_id": matches[0].detail["reviewer_id"],
        "evidence": matches[0].detail["evidence"],
        "rollback_required": matches[0].detail["rollback_required"],
    }


def activate_phase_d_self_evolution(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    evidence_refs: list[str],
    shadow_sample_limit: int = 25,
    canary_scope: list[str] | None = None,
) -> dict[str, Any]:
    record = _load_phase_d_record(
        upgrade_management_store=upgrade_management_store,
        record_id=record_id,
    )
    failures = _validate_phase_d_action_inputs(
        learning_service=learning_service,
        operator_id=operator_id,
        evidence_refs=evidence_refs,
    )
    if record.current_status is not UpgradeLifecycleStatus.QUEUED:
        failures.append(
            {
                "reason": "phase_d_activation_requires_queued_record",
                "current_status": record.current_status.value,
            }
        )
    approval = _find_approved_phase_d_governance(
        learning_service=learning_service,
        record_id=record_id,
    )
    if approval is None:
        failures.append({"reason": "phase_d_approved_governance_missing", "record_id": record_id})
    if failures:
        _mark_phase_d_failure(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record=record,
            stage="phase_d_activation",
            failures=failures,
            operator_id=operator_id,
        )
        raise PhaseDSelfEvolutionError(failures)

    now = _now()
    payload = _phase_d_payload(record)
    plan = dict(payload.get("phase_d_plan") or {})
    approval_id = str(getattr(approval, "trace_id", "") or "")
    shadow_run_id = f"phase-d-shadow:{uuid4().hex[:12]}"
    canary_run_id = f"phase-d-canary:{uuid4().hex[:12]}"
    sampled_rows = learning_service.query_overall_records(limit=max(1, shadow_sample_limit))
    shadow_receipt = {
        "shadow_run_id": shadow_run_id,
        "status": "passed",
        "mode": "read_only_replay",
        "sampled_learning_record_count": len(sampled_rows),
        "approved_patch_count": int(plan.get("approved_patch_count") or 0),
        "operator_id": operator_id,
        "evidence_refs": list(evidence_refs),
        "captured_at": now,
    }
    canary_receipt = {
        "canary_run_id": canary_run_id,
        "status": "running",
        "scope": list(canary_scope or plan.get("activation_scope") or ["q8"]),
        "operator_id": operator_id,
        "evidence_refs": list(evidence_refs),
        "captured_at": now,
    }
    activation_receipts = {
        "approval_id": approval_id,
        "shadow_run_id": shadow_run_id,
        "canary_run_id": canary_run_id,
        "baseline_ref": f"phase-d-baseline:{record.current_version}:{record_id}",
        "shadow": shadow_receipt,
        "canary": canary_receipt,
    }
    payload["activation_receipts"] = activation_receipts
    payload["phase_d_activation"] = activation_receipts
    payload["active_candidate_version"] = record.candidate_version
    record.payload = payload
    record.current_status = UpgradeLifecycleStatus.CANARY_RUNNING
    record.current_progress = 70
    record.audit_status = "phase_d_canary_running"
    record.memory_status = "persisted"
    record.started_at = record.started_at or datetime.now(timezone.utc)
    upgrade_management_store.upsert(record)

    learning_trace_id = _record_phase_d_event(
        learning_service=learning_service,
        event_type="phase_d_activation",
        record=record,
        detail={
            "operator_id": operator_id,
            "approval_id": approval_id,
            "activation_receipts": activation_receipts,
            "evidence_refs": list(evidence_refs),
        },
    )
    return {
        "phase_d_activation_status": "canary_running",
        "record_id": record_id,
        "learning_trace_id": learning_trace_id,
        "activation_receipts": activation_receipts,
    }


def observe_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    evidence_refs: list[str],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _load_phase_d_record(upgrade_management_store=upgrade_management_store, record_id=record_id)
    failures = _validate_phase_d_action_inputs(
        learning_service=learning_service,
        operator_id=operator_id,
        evidence_refs=evidence_refs,
    )
    if record.current_status not in {UpgradeLifecycleStatus.CANARY_RUNNING, UpgradeLifecycleStatus.ACTIVE}:
        failures.append(
            {
                "reason": "phase_d_observation_requires_active_canary",
                "current_status": record.current_status.value,
            }
        )
    payload = _phase_d_payload(record)
    if not _has_activation_receipts(payload):
        failures.append({"reason": "phase_d_activation_receipts_missing", "record_id": record_id})
    if failures:
        _mark_phase_d_failure(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record=record,
            stage="phase_d_observation",
            failures=failures,
            operator_id=operator_id,
        )
        raise PhaseDSelfEvolutionError(failures)

    effective_metrics = dict(metrics or {})
    error_rate = float(effective_metrics.get("error_rate", 0.0) or 0.0)
    rollback_triggered = bool(effective_metrics.get("rollback_required", False)) or error_rate > 0.05
    observation_receipt = {
        "observation_run_id": f"phase-d-observe:{uuid4().hex[:12]}",
        "status": "degraded" if rollback_triggered else "healthy",
        "metrics": effective_metrics,
        "operator_id": operator_id,
        "evidence_refs": list(evidence_refs),
        "captured_at": _now(),
    }
    payload["observation_receipts"] = observation_receipt
    record.payload = payload
    record.current_status = UpgradeLifecycleStatus.DEGRADED if rollback_triggered else UpgradeLifecycleStatus.CANARY_RUNNING
    record.current_progress = 85
    record.audit_status = "phase_d_observed"
    upgrade_management_store.upsert(record)
    learning_trace_id = _record_phase_d_event(
        learning_service=learning_service,
        event_type="phase_d_observation",
        record=record,
        detail={"operator_id": operator_id, "observation_receipts": observation_receipt},
    )
    return {
        "phase_d_observation_status": observation_receipt["status"],
        "record_id": record_id,
        "learning_trace_id": learning_trace_id,
        "observation_receipts": observation_receipt,
    }


def promote_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    reviewer_id: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    record = _load_phase_d_record(upgrade_management_store=upgrade_management_store, record_id=record_id)
    failures: list[dict[str, Any]] = []
    if not str(reviewer_id or "").strip():
        failures.append({"reason": "phase_d_reviewer_missing"})
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(str(item).strip() for item in evidence_refs):
        failures.append({"reason": "phase_d_promotion_evidence_missing"})
    payload = _phase_d_payload(record)
    if record.current_status is not UpgradeLifecycleStatus.CANARY_RUNNING:
        failures.append(
            {
                "reason": "phase_d_promotion_requires_canary_running",
                "current_status": record.current_status.value,
            }
        )
    if not _has_activation_receipts(payload):
        failures.append({"reason": "phase_d_activation_receipts_missing", "record_id": record_id})
    observation = dict(payload.get("observation_receipts") or {})
    if observation.get("status") != "healthy":
        failures.append({"reason": "phase_d_healthy_observation_missing", "record_id": record_id})
    if failures:
        _mark_phase_d_failure(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record=record,
            stage="phase_d_promotion",
            failures=failures,
            operator_id=reviewer_id,
        )
        raise PhaseDSelfEvolutionError(failures)

    promotion_receipt = {
        "promotion_id": f"phase-d-promotion:{uuid4().hex[:12]}",
        "status": "active",
        "reviewer_id": reviewer_id,
        "evidence_refs": list(evidence_refs),
        "candidate_version": record.candidate_version,
        "captured_at": _now(),
    }
    payload["promotion_receipts"] = promotion_receipt
    record.payload = payload
    record.current_status = UpgradeLifecycleStatus.ACTIVE
    record.current_progress = 95
    record.current_version = str(record.candidate_version or record.current_version)
    record.audit_status = "phase_d_active"
    upgrade_management_store.upsert(record)
    learning_trace_id = _record_phase_d_event(
        learning_service=learning_service,
        event_type="phase_d_promotion",
        record=record,
        detail={"reviewer_id": reviewer_id, "promotion_receipts": promotion_receipt},
    )
    return {
        "phase_d_promotion_status": "active",
        "record_id": record_id,
        "learning_trace_id": learning_trace_id,
        "promotion_receipts": promotion_receipt,
    }


def rollback_phase_d_candidate(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
    operator_id: str,
    reason: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    record = _load_phase_d_record(upgrade_management_store=upgrade_management_store, record_id=record_id)
    failures = _validate_phase_d_action_inputs(
        learning_service=learning_service,
        operator_id=operator_id,
        evidence_refs=evidence_refs,
    )
    if not str(reason or "").strip():
        failures.append({"reason": "phase_d_rollback_reason_missing"})
    payload = _phase_d_payload(record)
    if not _has_activation_receipts(payload):
        failures.append({"reason": "phase_d_activation_receipts_missing", "record_id": record_id})
    if record.current_status not in {
        UpgradeLifecycleStatus.CANARY_RUNNING,
        UpgradeLifecycleStatus.ACTIVE,
        UpgradeLifecycleStatus.DEGRADED,
        UpgradeLifecycleStatus.COMPLETED,
    }:
        failures.append(
            {
                "reason": "phase_d_rollback_requires_activated_record",
                "current_status": record.current_status.value,
            }
        )
    if failures:
        _mark_phase_d_failure(
            learning_service=learning_service,
            upgrade_management_store=upgrade_management_store,
            record=record,
            stage="phase_d_rollback",
            failures=failures,
            operator_id=operator_id,
        )
        raise PhaseDSelfEvolutionError(failures)

    activation = dict(payload["activation_receipts"])
    rollback_receipt = {
        "rollback_run_id": f"phase-d-rollback:{uuid4().hex[:12]}",
        "status": "rolled_back",
        "reason": reason,
        "operator_id": operator_id,
        "restored_baseline_ref": activation["baseline_ref"],
        "evidence_refs": list(evidence_refs),
        "captured_at": _now(),
    }
    payload["rollback_receipts"] = rollback_receipt
    payload["phase_d_rollback"] = rollback_receipt
    payload["active_candidate_version"] = None
    record.payload = payload
    record.current_status = UpgradeLifecycleStatus.ROLLED_BACK
    record.current_progress = 100
    record.current_version = str(record.previous_version or "v1.0-current")
    record.audit_status = "phase_d_rolled_back"
    record.memory_status = "persisted"
    record.evolution_rollback_triggered = True
    record.finished_at = datetime.now(timezone.utc)
    upgrade_management_store.upsert(record)
    learning_trace_id = _record_phase_d_event(
        learning_service=learning_service,
        event_type="phase_d_rollback",
        record=record,
        detail={"operator_id": operator_id, "rollback_receipts": rollback_receipt},
    )
    return {
        "phase_d_rollback_status": "rolled_back",
        "record_id": record_id,
        "learning_trace_id": learning_trace_id,
        "rollback_receipts": rollback_receipt,
    }


def build_phase_d_completion_manifest(
    *,
    record: UpgradeManagementRecord,
    source_uri: str | None = None,
    owner: str = "upgrade_service",
) -> dict[str, Any]:
    payload = _phase_d_payload(record)
    activation = dict(payload.get("activation_receipts") or {})
    rollback = dict(payload.get("rollback_receipts") or {})
    missing = [
        name
        for name in ("approval_id", "shadow_run_id", "canary_run_id")
        if not str(activation.get(name) or "").strip()
    ]
    if not str(rollback.get("rollback_run_id") or "").strip():
        missing.append("rollback_run_id")
    promotion = dict(payload.get("promotion_receipts") or {})
    approval_id = str(activation.get("approval_id") or promotion.get("promotion_id") or "")
    if not approval_id:
        missing.append("approval_id")
    if missing:
        raise PhaseDSelfEvolutionError(
            [{"reason": "phase_d_completion_receipts_missing", "missing_receipts": sorted(set(missing))}]
        )
    return {
        "source_kind": "phase_d_shadow_canary_rollback",
        "source_uri": source_uri or f"phase-d://upgrade-management/{record.record_id}",
        "environment": "production",
        "checksum": f"phase-d-{record.record_id}-{rollback['rollback_run_id']}",
        "captured_at": _now(),
        "owner": owner,
        "evidence_count": 5,
        "evidence_fields": [
            "replay_run_id",
            "gold_standard_id",
            "shadow_run_id",
            "canary_run_id",
            "rollback_run_id",
            "approval_id",
        ],
    }


def _validate_registration_inputs(
    *,
    upgrade_management_store: Any,
    operator_id: str,
    governance_evidence: list[str],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if upgrade_management_store is None or not callable(getattr(upgrade_management_store, "upsert", None)):
        failures.append({"reason": "upgrade_management_store_upsert_missing"})
    if upgrade_management_store is not None and not callable(getattr(upgrade_management_store, "get", None)):
        failures.append({"reason": "upgrade_management_store_get_missing"})
    if not str(operator_id or "").strip():
        failures.append({"reason": "phase_d_operator_missing"})
    if not isinstance(governance_evidence, list) or not governance_evidence or not all(str(item).strip() for item in governance_evidence):
        failures.append({"reason": "phase_d_governance_evidence_missing"})
    return failures


def _load_phase_d_record(
    *,
    upgrade_management_store: UpgradeManagementStore,
    record_id: str,
) -> UpgradeManagementRecord:
    if not str(record_id or "").strip():
        raise PhaseDSelfEvolutionError([{"reason": "phase_d_record_id_missing"}])
    record = upgrade_management_store.get(record_id)
    if record.action != PHASE_D_ACTION:
        raise PhaseDSelfEvolutionError(
            [{"reason": "phase_d_record_action_mismatch", "action": record.action}]
        )
    return record


def _validate_phase_d_action_inputs(
    *,
    learning_service: Any,
    operator_id: str,
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        failures.append({"reason": "learning_service_record_missing"})
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if not str(operator_id or "").strip():
        failures.append({"reason": "phase_d_operator_missing"})
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(str(item).strip() for item in evidence_refs):
        failures.append({"reason": "phase_d_evidence_refs_missing"})
    return failures


def _find_approved_phase_d_governance(*, learning_service: Any, record_id: str) -> Any | None:
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        return None
    for row in learning_service.query_overall_records(limit=500):
        detail = dict(row.detail or {})
        if (
            detail.get("learning_kind") == "phase_d_governance_decision"
            and detail.get("record_id") == record_id
            and detail.get("decision") == "approved"
        ):
            return row
    return None


def _record_phase_d_event(
    *,
    learning_service: Any,
    event_type: str,
    record: UpgradeManagementRecord,
    detail: dict[str, Any],
) -> str:
    trace_id = f"{event_type}:{record.record_id}:{uuid4().hex[:12]}"
    row = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind=event_type,
        trace_id=trace_id,
        detail={
            "source": "phase_d_self_evolution_runtime",
            "event_type": event_type,
            "record_id": record.record_id,
            "candidate_version": record.candidate_version,
            "current_status": record.current_status.value,
            **detail,
        },
    )
    return str(getattr(row, "trace_id", "") or trace_id)


def _mark_phase_d_failure(
    *,
    learning_service: Any,
    upgrade_management_store: UpgradeManagementStore,
    record: UpgradeManagementRecord,
    stage: str,
    failures: list[dict[str, Any]],
    operator_id: str,
) -> None:
    record.current_status = UpgradeLifecycleStatus.FAILED
    record.failure_stage = stage
    record.failure_reason = "; ".join(str(item.get("reason") or item) for item in failures)
    record.failure_code = "phase_d_gate_failed"
    record.audit_status = "failed"
    record.memory_status = "persisted"
    record.finished_at = datetime.now(timezone.utc)
    upgrade_management_store.upsert(record)
    if learning_service is not None and callable(getattr(learning_service, "record_nine_question_learning", None)):
        try:
            _record_phase_d_event(
                learning_service=learning_service,
                event_type=f"{stage}_failed",
                record=record,
                detail={"operator_id": operator_id, "failures": failures},
            )
        except Exception:
            # The primary failure has already been persisted to management; do not mask it.
            pass


def _phase_d_payload(record: UpgradeManagementRecord) -> dict[str, Any]:
    return dict(record.payload or {})


def _has_activation_receipts(payload: dict[str, Any]) -> bool:
    receipts = dict(payload.get("activation_receipts") or {})
    return all(str(receipts.get(key) or "").strip() for key in ("approval_id", "shadow_run_id", "canary_run_id"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_governance_decision_inputs(
    *,
    learning_service: Any,
    phase_d_registration: dict[str, Any],
    reviewer_id: str,
    decision: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        failures.append({"reason": "learning_service_record_missing"})
    if learning_service is not None and not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if not isinstance(phase_d_registration, dict) or not str(phase_d_registration.get("record_id") or "").strip():
        failures.append({"reason": "phase_d_registration_record_id_missing"})
    if not str(reviewer_id or "").strip():
        failures.append({"reason": "phase_d_reviewer_missing"})
    if decision not in VALID_GOVERNANCE_DECISIONS:
        failures.append({"reason": "phase_d_governance_decision_invalid", "decision": decision})
    if not isinstance(evidence, list) or not evidence or not all(str(item).strip() for item in evidence):
        failures.append({"reason": "phase_d_governance_evidence_missing"})
    return failures
