from __future__ import annotations

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.objective_engine import NineQDrivenObjectiveEngine, ObjectiveProfileMissingError


def _q8_snapshot(suffix: str) -> dict:
    objective = {
        "current_mission": f"deliver v1 objective export {suffix}",
        "primary_objectives": ["persist exact Q8 mission"],
        "secondary_objectives": ["expose contract checks"],
        "completion_conditions": ["objective endpoint returns this condition"],
        "pause_conditions": ["q8 profile missing"],
        "escalation_conditions": ["q9 posture missing"],
        "current_phase_tasks": [f"objective export task {suffix}"],
        "priority_order": [f"objective export task {suffix}"],
    }
    return {
        "tool_id": "nine_question_q8_decision",
        "summary": "Q8 objective export test",
        "confidence": 0.91,
        "trace_id": f"q8-objective-export-{suffix}",
        "result": {"objective": objective},
        "context_updates": {
            "q8_objective_profile": objective,
            "q8_objective_and_queue": {"objective": objective, "task_queue": {"next_self_tasks": []}},
        },
    }


def _q2_snapshot(suffix: str) -> dict:
    identity = {
        "role": "Zentex objective controller",
        "mission": "preserve hard boundaries during objective derivation",
        "non_bypassable_constraints": [f"preserve_audit_chain_{suffix}"],
        "forbidden_directions": [f"rewrite_identity_kernel_{suffix}"],
        "continuity_lock": {"locked_fields": ["role", "mission"], "enforced": True},
    }
    return {
        "tool_id": "nine_question_q2_identity",
        "summary": "Q2 hard boundary source",
        "confidence": 0.93,
        "trace_id": f"q2-objective-export-{suffix}",
        "result": {"identity_kernel_snapshot": identity},
        "context_updates": {"identity_kernel_snapshot": identity},
    }


def _q3_tight_resource_snapshot(suffix: str) -> dict:
    state = {
        "resource_status": "scarce",
        "budget_remaining_ratio": 0.08,
        "assets_insufficient": True,
    }
    return {
        "tool_id": "nine_question_q3_resources",
        "summary": "Q3 scarce resource state",
        "confidence": 0.9,
        "trace_id": f"q3-tight-resource-{suffix}",
        "result": {"q3_resource_state": state},
        "context_updates": {"q3_resource_state": state},
    }


def _q4_insufficient_evidence_snapshot(suffix: str) -> dict:
    state = {
        "capability_evidence_status": "insufficient",
        "capability_confidence": 0.31,
    }
    return {
        "tool_id": "nine_question_q4_capability",
        "summary": "Q4 insufficient capability evidence",
        "confidence": 0.82,
        "trace_id": f"q4-insufficient-evidence-{suffix}",
        "result": {"q4_capability_state": state},
        "context_updates": {"q4_capability_state": state},
    }


def _q5_single_brain_snapshot(suffix: str) -> dict:
    state = {
        "authorization_scope": "single_brain",
        "collaboration_available": False,
        "external_agent_authorized": False,
    }
    return {
        "tool_id": "nine_question_q5_authorization",
        "summary": "Q5 collaboration unavailable",
        "confidence": 0.87,
        "trace_id": f"q5-single-brain-{suffix}",
        "result": {"q5_authorization_state": state},
        "context_updates": {"q5_authorization_state": state},
    }


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "release executor",
        "resource_context": "limited isolated ci acceptance app",
        "risk_level": "medium",
        "evaluation_weights": {
            "accuracy": 0.45,
            "risk_control": 0.35,
            "continuity": 0.2,
        },
        "conservative_mode_triggered": True,
        "evaluation_style": "evidence_first",
        "action_rhythm_hint": "confirm_before_commit",
        "confirmation_required_conditions": ["human confirms high risk release"],
    }
    evolution_profile = {
        "allowed_directions": ["tighten objective contract"],
        "risk_threshold": 0.12,
        "forbidden_directions": ["synthesize fallback objective"],
        "validation_requirements": ["query persisted Q8 and Q9 profiles"],
        "rollback_conditions": ["objective export violates hard boundary"],
    }
    return {
        "tool_id": "nine_question_q9_posture",
        "summary": "Q9 objective export test",
        "confidence": 0.88,
        "trace_id": f"q9-objective-export-{suffix}",
        "result": {
            "evaluation_profile": evaluation_profile,
            "evolution_profile": evolution_profile,
        },
        "context_updates": {
            "q9_action_posture": {
                "evaluation_profile": evaluation_profile,
                "evolution_profile": evolution_profile,
            },
            "q9_evaluation_profile": evaluation_profile,
            "q9_evolution_profile": evolution_profile,
        },
    }


@pytest.mark.asyncio
async def test_nine_question_objectives_endpoint_queries_exact_q8_q9_profiles(acceptance_app: FastAPI) -> None:
    """查询链路：接口必须通过 requests 返回真实持久化 Q8/Q9 profile，不能只检查 HTTP 200。"""
    suffix = unique_suffix()
    q2_snapshot = _q2_snapshot(suffix)
    q8_snapshot = _q8_snapshot(suffix)
    q9_snapshot = _q9_snapshot(suffix)

    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q2",
        q2_snapshot,
        refresh_reason="objective_engine_real_q2",
    )
    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q8",
        q8_snapshot,
        refresh_reason="objective_engine_real_q8",
    )
    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q9",
        q9_snapshot,
        refresh_reason="objective_engine_real_q9",
    )

    persisted_q2 = await acceptance_app.state.nine_question_service.get_question_snapshot("q2")
    persisted_q8 = await acceptance_app.state.nine_question_service.get_question_snapshot("q8")
    persisted_q9 = await acceptance_app.state.nine_question_service.get_question_snapshot("q9")
    assert persisted_q2["trace_id"] == q2_snapshot["trace_id"], "查询接口前必须能查到真实 Q2 持久化快照"
    assert persisted_q8["trace_id"] == q8_snapshot["trace_id"], "查询接口前必须能查到真实 Q8 持久化快照"
    assert persisted_q9["trace_id"] == q9_snapshot["trace_id"], "查询接口前必须能查到真实 Q9 持久化快照"

    with live_http_server(acceptance_app) as base_url:
        response = requests.get(f"{base_url}/api/web/nine-questions/objectives", timeout=20)

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_status"] == "ready"
    assert payload["synthetic_profile_generated"] is False
    assert payload["source_question_ids"] == ["q8", "q9"]
    assert payload["source_trace_ids"] == {
        "q8": q8_snapshot["trace_id"],
        "q9": q9_snapshot["trace_id"],
    }
    assert payload["derivation_trace"]["objective_profile"] == [
        "q2_role_plus_q3_resources_plus_q8_objective",
        f"source_trace:q8:{q8_snapshot['trace_id']}",
    ]
    assert "resource_tightness_requires_risk_control_and_continuity_attention" in payload["derivation_trace"]["evaluation_profile"]
    assert "conservative_mode_triggered_by_q9" in payload["derivation_trace"]["evaluation_profile"]

    objective = payload["objective_profile"]
    expected_objective = q8_snapshot["context_updates"]["q8_objective_profile"]
    assert objective["current_primary_objective"] == expected_objective["current_mission"]
    assert objective["primary_objectives"] == ["persist exact Q8 mission"]
    assert objective["secondary_objectives"] == ["expose contract checks"]
    assert objective["completion_conditions"] == ["objective endpoint returns this condition"]
    assert objective["pause_conditions"] == ["q8 profile missing"]
    assert objective["escalation_conditions"] == ["q9 posture missing"]
    assert objective["current_phase_tasks"] == [f"objective export task {suffix}"]
    assert objective["priority_order"] == [f"objective export task {suffix}"]

    evaluation = payload["evaluation_profile"]
    expected_evaluation = q9_snapshot["context_updates"]["q9_evaluation_profile"]
    for key, value in expected_evaluation.items():
        if key == "confirmation_required_conditions":
            continue
        assert evaluation[key] == value
    assert evaluation["meta_value_lens_mapping_version"] == "1.0"
    assert evaluation["meta_value_lens_weights"] == {
        "system_capability_lens": 0.2,
        "user_efficiency_lens": 0.0,
        "user_value_lens": 0.45,
    }
    assert evaluation["dominant_meta_value_lenses"] == ["user_value_lens"]
    assert evaluation["unmapped_evaluation_axes"] == {"risk_control": 0.35}
    evolution = payload["evolution_profile"]
    expected_evolution = dict(q9_snapshot["context_updates"]["q9_evolution_profile"])
    expected_evolution.pop("rollback_conditions")
    assert evolution == expected_evolution
    escalation = payload["escalation_profile"]
    assert escalation["pause_conditions"] == ["q8 profile missing"]
    assert escalation["help_request_conditions"] == ["q9 posture missing"]
    assert escalation["confirmation_required_conditions"] == ["human confirms high risk release"]
    assert escalation["revisit_conditions"] == ["q8 profile missing"]
    assert escalation["rollback_conditions"] == ["objective export violates hard boundary"]

    hard_boundary = payload["hard_boundary_check"]
    assert hard_boundary["status"] == "passed"
    assert hard_boundary["violation_count"] == 0
    assert hard_boundary["non_bypassable_constraints_checked"] == [f"preserve_audit_chain_{suffix}"]
    assert hard_boundary["forbidden_directions_checked"] == [f"rewrite_identity_kernel_{suffix}"]
    assert hard_boundary["identity_locked_fields_checked"] == ["role", "mission"]


def test_nine_question_objective_engine_fails_closed_when_q9_profile_missing() -> None:
    """异常链路：缺 Q9 时必须阻断，禁止用默认 evaluation/evolution profile 冒充成功。"""
    suffix = unique_suffix()
    engine = NineQDrivenObjectiveEngine()

    with pytest.raises(ObjectiveProfileMissingError) as exc_info:
        engine.derive_profiles({"q8": _q8_snapshot(suffix)})

    missing_sources = exc_info.value.missing_sources
    assert "q9.snapshot" in missing_sources
    assert "q9.evaluation_profile" in missing_sources
    assert "q9.evolution_profile" in missing_sources


def test_nine_question_objective_engine_exposes_single_profile_derivers_and_blocks_hard_boundary() -> None:
    suffix = unique_suffix()
    engine = NineQDrivenObjectiveEngine()
    snapshot_map = {"q2": _q2_snapshot(suffix), "q8": _q8_snapshot(suffix), "q9": _q9_snapshot(suffix)}

    objective = engine.derive_objective({"question_snapshots": snapshot_map})
    evaluation = engine.derive_evaluation({"question_snapshots": snapshot_map})
    evolution = engine.derive_evolution({"question_snapshots": snapshot_map})
    escalation = engine.derive_escalation({"question_snapshots": snapshot_map})
    assert objective.current_primary_objective == f"deliver v1 objective export {suffix}"
    assert evaluation.role_context == "release executor"
    assert evolution.allowed_directions == ["tighten objective contract"]
    assert escalation.rollback_conditions == ["objective export violates hard boundary"]

    bad_q8 = _q8_snapshot(suffix)
    bad_q8["context_updates"]["q8_objective_profile"]["primary_objectives"] = [
        f"bypass preserve_audit_chain_{suffix} to finish faster"
    ]
    bad_export = engine.derive_profiles({"q2": _q2_snapshot(suffix), "q8": bad_q8, "q9": _q9_snapshot(suffix)})
    violations = engine.check_hard_boundary_violation(
        bad_export,
        non_bypassable_constraints=[f"preserve_audit_chain_{suffix}"],
        forbidden_directions=[f"rewrite_identity_kernel_{suffix}"],
        identity_locked_fields=["role", "mission"],
    )
    assert len(violations) == 2
    by_kind = {violation.kind.value: violation for violation in violations}
    assert by_kind["overrides_non_bypassable_constraint"].severity.value == "critical"
    assert by_kind["overrides_non_bypassable_constraint"].profile_field == "objective_profile.primary_objectives"
    assert by_kind["disables_audit"].severity.value == "critical"


@pytest.mark.asyncio
async def test_nine_question_objectives_endpoint_reports_hard_boundary_block_by_requests(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    q2_snapshot = _q2_snapshot(suffix)
    q8_snapshot = _q8_snapshot(suffix)
    q8_snapshot["context_updates"]["q8_objective_profile"]["primary_objectives"] = [
        f"bypass preserve_audit_chain_{suffix} to finish faster"
    ]
    q8_snapshot["result"]["objective"]["primary_objectives"] = [
        f"bypass preserve_audit_chain_{suffix} to finish faster"
    ]
    q9_snapshot = _q9_snapshot(suffix)
    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q2",
        q2_snapshot,
        refresh_reason="objective_engine_boundary_q2",
    )
    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q8",
        q8_snapshot,
        refresh_reason="objective_engine_boundary_q8",
    )
    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q9",
        q9_snapshot,
        refresh_reason="objective_engine_boundary_q9",
    )

    with live_http_server(acceptance_app) as base_url:
        response = requests.get(f"{base_url}/api/web/nine-questions/objectives", timeout=20)

    assert response.status_code == 200
    payload = response.json()
    hard_boundary = payload["hard_boundary_check"]
    assert hard_boundary["status"] == "blocked"
    assert hard_boundary["violation_count"] == 2
    by_kind = {violation["kind"]: violation for violation in hard_boundary["violations"]}
    assert by_kind["overrides_non_bypassable_constraint"]["severity"] == "critical"
    assert by_kind["overrides_non_bypassable_constraint"]["profile_field"] == "objective_profile.primary_objectives"
    assert by_kind["overrides_non_bypassable_constraint"]["constraint_source"] == f"preserve_audit_chain_{suffix}"
    assert by_kind["disables_audit"]["severity"] == "critical"


@pytest.mark.asyncio
async def test_nine_question_objectives_endpoint_applies_dynamic_convergence_rules_by_requests(
    acceptance_app: FastAPI,
) -> None:
    """动态规则链路：Q3/Q4/Q5/历史变化必须真实改写 API 返回，而不是只返回原始 Q9 profile。"""
    suffix = unique_suffix()
    q2_snapshot = _q2_snapshot(suffix)
    q3_snapshot = _q3_tight_resource_snapshot(suffix)
    q4_snapshot = _q4_insufficient_evidence_snapshot(suffix)
    q5_snapshot = _q5_single_brain_snapshot(suffix)
    q8_snapshot = _q8_snapshot(suffix)
    q8_objective = q8_snapshot["context_updates"]["q8_objective_profile"]
    q8_objective["primary_objectives"] = [
        "coordinate external agent release review",
        f"single brain verify release evidence {suffix}",
    ]
    q8_objective["secondary_objectives"] = [
        "delegate multi-agent regression audit",
        f"single brain preserve trace {suffix}",
    ]
    q8_objective["current_phase_tasks"] = [
        "external agent release coordination",
        f"single brain inspect query result {suffix}",
    ]
    q8_objective["priority_order"] = list(q8_objective["current_phase_tasks"])

    q9_snapshot = _q9_snapshot(suffix)
    q9_evaluation = q9_snapshot["context_updates"]["q9_evaluation_profile"]
    q9_evaluation["evaluation_weights"] = {
        "accuracy": 0.70,
        "risk_control": 0.10,
        "continuity": 0.05,
        "speed": 0.15,
    }
    q9_evaluation["conservative_mode_triggered"] = False
    q9_evolution = q9_snapshot["context_updates"]["q9_evolution_profile"]
    q9_evolution["risk_threshold"] = 0.6
    q9_snapshot["context_updates"]["evolution_history"] = [
        {"status": "failed", "reason": "candidate patch rejected"},
        {"status": "blocked", "reason": "validation missing"},
        {"status": "rollback", "reason": "post-check failed"},
    ]

    for question_id, snapshot in (
        ("q2", q2_snapshot),
        ("q3", q3_snapshot),
        ("q4", q4_snapshot),
        ("q5", q5_snapshot),
        ("q8", q8_snapshot),
        ("q9", q9_snapshot),
    ):
        await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
            question_id,
            snapshot,
            refresh_reason=f"objective_engine_dynamic_{question_id}",
        )
        persisted = await acceptance_app.state.nine_question_service.get_question_snapshot(question_id)
        assert persisted["trace_id"] == snapshot["trace_id"], f"{question_id} must be persisted before API query"

    with live_http_server(acceptance_app) as base_url:
        response = requests.get(f"{base_url}/api/web/nine-questions/objectives", timeout=20)

    assert response.status_code == 200, response.text
    payload = response.json()
    objective = payload["objective_profile"]
    assert objective["current_primary_objective"] == f"single brain verify release evidence {suffix}"
    assert objective["primary_objectives"] == [f"single brain verify release evidence {suffix}"]
    assert objective["secondary_objectives"] == [f"single brain preserve trace {suffix}"]
    assert objective["current_phase_tasks"] == [f"single brain inspect query result {suffix}"]
    assert objective["priority_order"] == [f"single brain inspect query result {suffix}"]
    assert "collaboration unavailable: external-agent objectives deferred" in objective["pause_conditions"]

    evaluation = payload["evaluation_profile"]
    assert evaluation["conservative_mode_triggered"] is True
    assert evaluation["evaluation_weights"] == {
        "accuracy": 0.288235,
        "risk_control": 0.4,
        "continuity": 0.25,
        "speed": 0.061765,
    }
    assert evaluation["meta_value_lens_weights"] == {
        "system_capability_lens": 0.25,
        "user_efficiency_lens": 0.061765,
        "user_value_lens": 0.288235,
    }
    assert evaluation["unmapped_evaluation_axes"] == {"risk_control": 0.4}

    evolution = payload["evolution_profile"]
    assert evolution["risk_threshold"] == 0.1
    assert "continuous failure history requires low-risk validation before evolution" in evolution["validation_requirements"]
    assert "q3_resource_tightness_converged_weights_to_risk_control_and_continuity" in payload["derivation_trace"]["evaluation_profile"]
    assert "q4_evidence_insufficient_triggered_conservative_mode" in payload["derivation_trace"]["evaluation_profile"]
    assert "q5_collaboration_unavailable_shrank_objectives_to_single_brain_scope" in payload["derivation_trace"]["objective_profile"]
    assert "evolution_history_continuous_failures_lowered_risk_threshold" in payload["derivation_trace"]["evolution_profile"]


def test_nine_question_objective_engine_derive_evolution_uses_history_to_lower_threshold() -> None:
    suffix = unique_suffix()
    engine = NineQDrivenObjectiveEngine()
    history = [
        {"status": "failed", "reason": "first failed evolution"},
        {"status": "failure", "reason": "second failed evolution"},
        {"status": "rollback", "reason": "third failed evolution"},
    ]

    evolution = engine.derive_evolution(
        {"question_snapshots": {"q2": _q2_snapshot(suffix), "q8": _q8_snapshot(suffix), "q9": _q9_snapshot(suffix)}},
        history=history,
    )

    assert evolution.risk_threshold == 0.1
    assert "continuous failure history requires low-risk validation before evolution" in evolution.validation_requirements
