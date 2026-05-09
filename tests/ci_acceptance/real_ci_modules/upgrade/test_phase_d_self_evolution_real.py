from __future__ import annotations

from contextlib import contextmanager
import socket
import threading

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.learning.strategy_patch import (
    build_strategy_patches_from_experience_candidates,
    record_strategy_patch_approval,
)
from zentex.nine_questions.plan_evidence_registry import register_plan_evidence_manifest
from zentex.upgrade.base_models import SelfUpgradeProposal, UpgradeTargetKind
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.management import UpgradeLifecycleStatus, UpgradeManagementRecord
from zentex.upgrade.phase_d_self_evolution import (
    PhaseDSelfEvolutionError,
    activate_phase_d_self_evolution,
    build_phase_d_completion_manifest,
    build_phase_d_self_evolution_plan,
    observe_phase_d_candidate,
    promote_phase_d_candidate,
    record_phase_d_governance_decision,
    register_phase_d_upgrade_candidate,
    rollback_phase_d_candidate,
)
from zentex.upgrade.service import build_default_upgrade_runtime_components


@contextmanager
def _live_http_server(app: FastAPI):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _record_experience_candidate(learning_service, *, suffix: str):
    task_id = f"phase-d-source-failure-{suffix}"
    candidate = {
        "candidate_id": f"experience-candidate:{task_id}",
        "candidate_type": "failure_pattern",
        "task_id": task_id,
        "task_title": f"phase d source failure {suffix}",
        "question_id": "q8",
        "source_trace_id": f"trace-phase-d-{suffix}",
        "overall_passed": False,
        "actual_outcome": {"task_id": task_id, "candidate_type": "failure_pattern"},
        "failed_verifiers": ["q8_required_outcome_evidence"],
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
            "candidate_type": "failure_pattern",
        },
    )


def _approve_strategy_patch(learning_service, *, suffix: str) -> dict:
    _record_experience_candidate(learning_service, suffix=suffix)
    report = build_strategy_patches_from_experience_candidates(
        learning_service=learning_service,
        candidate_version="phase-c-experience-candidate-v1",
        required_candidate_count=1,
    )
    patch = next(item for item in report["patches"] if item["source_task_id"] == f"phase-d-source-failure-{suffix}")
    approval = record_strategy_patch_approval(
        learning_service=learning_service,
        patch=patch,
        approver_id=f"phase-d-approver-{suffix}",
        decision="approved",
        approval_evidence=[f"phase d approval evidence for {patch['patch_id']}"],
    )
    assert approval["strategy_patch_approval_status"] == "approved"
    rows = learning_service.query_overall_records(limit=20, trace_id=approval["learning_trace_id"])
    assert len([row for row in rows if row.detail.get("patch_id") == patch["patch_id"]]) == 1
    return patch


def _real_upgrade_store():
    return build_default_upgrade_runtime_components(
        memory_service=None,
    ).management_store


def test_phase_d_registers_real_upgrade_candidate_and_records_governance(real_ci_runtime) -> None:
    suffix = unique_suffix()
    patch = _approve_strategy_patch(real_ci_runtime.learning_service, suffix=suffix)
    store = _real_upgrade_store()

    plan = build_phase_d_self_evolution_plan(
        learning_service=real_ci_runtime.learning_service,
        required_approved_patch_count=1,
        candidate_version=f"phase-d-self-evolution-{suffix}",
    )
    assert plan["phase_d_plan_status"] == "pending_governance"
    assert plan["approved_patch_count"] >= 1
    assert patch["patch_id"] in {item["patch_id"] for item in plan["patches"]}
    assert plan["d0_to_d4_gates"] == {
        "d0_evolution_infrastructure": "ready",
        "d1_q8_pilot": "ready",
        "d2_q1_q2_extension": "ready",
        "d3_q5_q7_extension": "ready",
        "d4_q3_q4_q6_q9_extension": "ready",
    }

    registration = register_phase_d_upgrade_candidate(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        operator_id=f"phase-d-operator-{suffix}",
        governance_evidence=[f"real approved StrategyPatch {patch['patch_id']}"],
        required_approved_patch_count=1,
        candidate_version=f"phase-d-self-evolution-{suffix}",
    )
    assert registration["phase_d_registration_status"] == "queued"
    assert registration["current_status"] == "queued"
    assert registration["target_kind"] == "cognitive_tool"
    assert registration["rollback_required"] is True
    queried = store.get(registration["record_id"])
    assert queried.record_id == registration["record_id"]
    assert queried.payload["phase_d_plan"]["d0_to_d4_gates"] == registration["d0_to_d4_gates"]

    governance = record_phase_d_governance_decision(
        learning_service=real_ci_runtime.learning_service,
        phase_d_registration=registration,
        reviewer_id=f"phase-d-reviewer-{suffix}",
        decision="approved",
        evidence=[f"queried upgrade record {registration['record_id']} before approval"],
    )
    assert governance["phase_d_governance_status"] == "approved"
    assert governance["record_id"] == registration["record_id"]
    rows = real_ci_runtime.learning_service.query_overall_records(
        limit=20,
        trace_id=governance["learning_trace_id"],
    )
    matching = [row for row in rows if row.detail.get("record_id") == registration["record_id"]]
    assert len(matching) == 1
    assert matching[0].detail["decision"] == "approved"
    assert matching[0].detail["rollback_required"] is True


def test_phase_d_real_activation_shadow_canary_promotion_rollback_and_manifest(real_ci_runtime) -> None:
    suffix = unique_suffix()
    patch = _approve_strategy_patch(real_ci_runtime.learning_service, suffix=suffix)
    store = _real_upgrade_store()
    candidate_version = f"phase-d-real-activation-{suffix}"
    registration = register_phase_d_upgrade_candidate(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        operator_id=f"phase-d-operator-{suffix}",
        governance_evidence=[f"real approved StrategyPatch {patch['patch_id']}"],
        required_approved_patch_count=1,
        candidate_version=candidate_version,
    )
    governance = record_phase_d_governance_decision(
        learning_service=real_ci_runtime.learning_service,
        phase_d_registration=registration,
        reviewer_id=f"phase-d-reviewer-{suffix}",
        decision="approved",
        evidence=[f"real governance review for {registration['record_id']}"],
    )

    activation = activate_phase_d_self_evolution(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        record_id=registration["record_id"],
        operator_id=f"phase-d-operator-{suffix}",
        evidence_refs=[governance["learning_trace_id"], f"real phase d activation {suffix}"],
        canary_scope=["q8"],
    )
    assert activation["phase_d_activation_status"] == "canary_running"
    assert activation["activation_receipts"]["approval_id"] == governance["learning_trace_id"]
    assert activation["activation_receipts"]["shadow_run_id"].startswith("phase-d-shadow:")
    assert activation["activation_receipts"]["canary_run_id"].startswith("phase-d-canary:")
    queried_after_activation = store.get(registration["record_id"])
    assert queried_after_activation.current_status == UpgradeLifecycleStatus.CANARY_RUNNING
    assert queried_after_activation.payload["activation_receipts"]["canary"]["scope"] == ["q8"]

    observation = observe_phase_d_candidate(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        record_id=registration["record_id"],
        operator_id=f"phase-d-observer-{suffix}",
        evidence_refs=[activation["learning_trace_id"]],
        metrics={"error_rate": 0.0, "latency_ms": 120, "sample_count": 3},
    )
    assert observation["phase_d_observation_status"] == "healthy"

    promotion = promote_phase_d_candidate(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        record_id=registration["record_id"],
        reviewer_id=f"phase-d-promoter-{suffix}",
        evidence_refs=[observation["learning_trace_id"]],
    )
    assert promotion["phase_d_promotion_status"] == "active"
    assert store.get(registration["record_id"]).current_status == UpgradeLifecycleStatus.ACTIVE

    rollback = rollback_phase_d_candidate(
        learning_service=real_ci_runtime.learning_service,
        upgrade_management_store=store,
        record_id=registration["record_id"],
        operator_id=f"phase-d-rollback-{suffix}",
        reason="real rollback rehearsal after canary",
        evidence_refs=[promotion["learning_trace_id"]],
    )
    assert rollback["phase_d_rollback_status"] == "rolled_back"
    assert rollback["rollback_receipts"]["rollback_run_id"].startswith("phase-d-rollback:")
    rolled_back = store.get(registration["record_id"])
    assert rolled_back.current_status == UpgradeLifecycleStatus.ROLLED_BACK
    assert rolled_back.evolution_rollback_triggered is True

    manifest = build_phase_d_completion_manifest(record=rolled_back, owner=f"phase-d-ci-{suffix}")
    registered = register_plan_evidence_manifest(
        learning_service=real_ci_runtime.learning_service,
        manifest=manifest,
    )
    assert registered["counts_toward_completion"] is True
    rows = real_ci_runtime.learning_service.query_overall_records(limit=20, trace_id=registered["learning_trace_id"])
    assert any(
        row.detail.get("learning_kind") == "plan_evidence_manifest"
        and row.detail.get("source_kind") == "phase_d_shadow_canary_rollback"
        for row in rows
    )


def test_upgrade_cancel_and_candidate_patch_models_use_real_runtime_store(real_ci_runtime) -> None:
    suffix = unique_suffix()
    store = _real_upgrade_store()
    record = UpgradeManagementRecord(
        record_id=f"cancel-real-store-{suffix}",
        target_kind=UpgradeTargetKind.PLUGIN,
        action="upgrade",
        target_id=f"plugin-{suffix}",
        title=f"cancel queued plugin {suffix}",
        reason="real queued cancel test",
        trace_id=f"cancel-trace-{suffix}",
        request_id=f"cancel-request-{suffix}",
        change_summary="queued cancel test",
        function_summary="verify queued cancel does not TypeError",
        previous_version="1.0.0",
        current_version="1.0.0",
        candidate_version="1.0.1-candidate",
        current_status=UpgradeLifecycleStatus.QUEUED,
    )
    store.upsert(record)
    cancelled = store.cancel(record.record_id, reason="operator cancelled queued real record")
    assert cancelled.current_status == UpgradeLifecycleStatus.CANCELLED
    assert store.get(record.record_id).failure_reason == "operator cancelled queued real record"

    proposal = SelfUpgradeProposal(
        program_id=f"self-upgrade-{suffix}",
        target_metric="reliability",
        baseline_version="1.0.0",
        candidate_version="1.0.1-candidate",
        description="Repeated real capability failures justify a bounded candidate patch.",
        capability_gap="missing reliable comparison tool after repeated failures",
        proposed_changes=["add bounded comparison tool candidate"],
        affected_modules=[f"self-upgrade-{suffix}"],
    )
    patch = UpgradeExecutionService(management_store=store).generate_candidate_patch(proposal)
    assert patch.proposal_id == proposal.proposal_id
    assert patch.patch_id
    assert patch.target_component == proposal.program_id


def test_phase_d_upgrade_api_uses_real_runtime_db_and_exposes_receipts(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    learning_service = acceptance_app.state.learning_service
    store = acceptance_app.state.upgrade_management_store
    patch = _approve_strategy_patch(learning_service, suffix=suffix)
    registration = register_phase_d_upgrade_candidate(
        learning_service=learning_service,
        upgrade_management_store=store,
        operator_id=f"api-phase-d-operator-{suffix}",
        governance_evidence=[f"api real StrategyPatch {patch['patch_id']}"],
        required_approved_patch_count=1,
        candidate_version=f"api-phase-d-{suffix}",
    )
    governance = record_phase_d_governance_decision(
        learning_service=learning_service,
        phase_d_registration=registration,
        reviewer_id=f"api-phase-d-reviewer-{suffix}",
        decision="approved",
        evidence=[f"api governance for {registration['record_id']}"],
    )

    with _live_http_server(acceptance_app) as base_url:
        activate_response = requests.post(
            f"{base_url}/api/web/upgrades/{registration['record_id']}/phase-d/activate",
            json={
                "reason": f"api phase d activate {suffix}",
                "operator_id": f"api-operator-{suffix}",
                "evidence_refs": [governance["learning_trace_id"]],
            },
            timeout=10,
        )
        observe_response = requests.post(
            f"{base_url}/api/web/upgrades/{registration['record_id']}/observe",
            json={
                "reason": f"api phase d observe {suffix}",
                "operator_id": f"api-observer-{suffix}",
                "evidence_refs": ["api observe healthy"],
            },
            timeout=10,
        )
        promote_response = requests.post(
            f"{base_url}/api/web/upgrades/{registration['record_id']}/promote",
            json={
                "reason": f"api phase d promote {suffix}",
                "reviewer_id": f"api-promoter-{suffix}",
                "evidence_refs": ["api promote healthy canary"],
            },
            timeout=10,
        )
        rollback_response = requests.post(
            f"{base_url}/api/web/upgrades/{registration['record_id']}/rollback",
            json={
                "reason": f"api phase d rollback {suffix}",
                "operator_id": f"api-rollback-{suffix}",
                "evidence_refs": ["api rollback rehearsal"],
            },
            timeout=10,
        )

    assert activate_response.status_code == 200, activate_response.text
    assert activate_response.json()["can_activate_phase_d"] is False
    assert activate_response.json()["activation_receipts"]["approval_id"] == governance["learning_trace_id"]
    assert observe_response.status_code == 200, observe_response.text
    assert promote_response.status_code == 200, promote_response.text
    assert promote_response.json()["can_rollback"] is True
    assert rollback_response.status_code == 200, rollback_response.text
    rollback_body = rollback_response.json()
    assert rollback_body["current_status"] == "rolled_back"
    assert rollback_body["rollback_receipts"]["rollback_run_id"].startswith("phase-d-rollback:")

    queried = store.get(registration["record_id"])
    assert queried.current_status == UpgradeLifecycleStatus.ROLLED_BACK
    rows = learning_service.query_overall_records(limit=200)
    assert any(
        row.detail.get("learning_kind") == "phase_d_rollback"
        and row.detail.get("record_id") == registration["record_id"]
        for row in rows
    )


def test_phase_d_fails_closed_without_approved_strategy_patch(real_ci_runtime) -> None:
    with pytest.raises(PhaseDSelfEvolutionError) as exc_info:
        build_phase_d_self_evolution_plan(
            learning_service=real_ci_runtime.learning_service,
            required_approved_patch_count=10_000,
            candidate_version="phase-d-self-evolution-insufficient",
        )

    assert len(exc_info.value.failures) == 1
    failure = exc_info.value.failures[0]
    assert failure["reason"] == "approved_strategy_patch_count_below_required"
    assert failure["required"] == 10_000
    assert failure["actual"] < 10_000


def test_phase_d_governance_requires_real_evidence(real_ci_runtime) -> None:
    with pytest.raises(PhaseDSelfEvolutionError) as exc_info:
        record_phase_d_governance_decision(
            learning_service=real_ci_runtime.learning_service,
            phase_d_registration={"record_id": "phase-d-invalid", "candidate_version": "v1"},
            reviewer_id="",
            decision="auto_approved",
            evidence=[],
        )

    assert exc_info.value.failures == [
        {"reason": "phase_d_reviewer_missing"},
        {"reason": "phase_d_governance_decision_invalid", "decision": "auto_approved"},
        {"reason": "phase_d_governance_evidence_missing"},
    ]
