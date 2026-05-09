from __future__ import annotations

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.tasks.verification.models import VerificationStrategy, VerificationType
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _verification_contract(expected_artifact: str) -> dict:
    return {
        "expected_outcome": {"artifact": expected_artifact},
        "success_criteria": ["actual_outcome artifact matches expectation", "evidence exists"],
        "acceptance_conditions": ["task_outcomes.overall_passed is true"],
        "risk_assessment": {"risk_level": "medium"},
        "verification": {
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "g11_required_fields",
                    "verifier_type": VerificationType.RULE_BASED.value,
                    "retry_on_failure": False,
                    "max_retries": 0,
                    "config": {
                        "rules": [
                            {"type": "required_field", "field": "actual_outcome"},
                            {"type": "required_field", "field": "evidence"},
                        ]
                    },
                }
            ],
        },
    }


async def _create_completed_task(real_ci_runtime, *, suffix: str, artifact: str):
    payload = task_payload(suffix=suffix, title_prefix="g11-experience", source_module="g11_real_ci")
    payload["contract"] = _verification_contract(artifact)
    created = await real_ci_runtime.task_service.create_task(payload)
    completion = await real_ci_runtime.task_service.complete_task_with_verification(
        created.task_id,
        result={"actual_outcome": {"artifact": artifact}, "evidence": [f"g11 real evidence {suffix}"]},
        remarks=f"g11 outcome binding {suffix}",
    )
    assert completion["success"] is True
    outcome = real_ci_runtime.task_service.get_task_outcome(created.task_id)
    assert outcome is not None
    assert outcome["actual_outcome"] == {"artifact": artifact}
    assert outcome["overall_passed"] is True
    return created


def _assert_binding(binding: dict, *, session_id: str, task_id: str, artifact: str) -> None:
    assert binding["feature_code"] == "G11"
    assert binding["session_id"] == session_id
    assert binding["task_id"] == task_id
    assert binding["actual_outcome"] == {"artifact": artifact}
    assert binding["deviation_report"]["passed"] is True
    assert binding["deviation_report"]["mismatched_fields"] == []
    assert binding["task_outcome"]["overall_passed"] is True
    assert binding["strategy_patch"]["structured"] is True
    assert binding["strategy_patch"]["identity_constraint_protected"] is True
    assert binding["identity_kernel_constraints_preserved"] is True
    evidence_types = {ref["type"] for ref in binding["evidence_refs"]}
    assert {"memory", "reflection", "learning"} <= evidence_types


@pytest.mark.asyncio
async def test_g11_experience_engine_service_registers_binds_queries_and_ranks_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    artifact = f"artifact-{suffix}"
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g11-service-{suffix}")
    task = await _create_completed_task(real_ci_runtime, suffix=suffix, artifact=artifact)

    expectation = kernel_service.register_experience_expectation(
        session_id=session_id,
        task_id=task.task_id,
        expected_outcome={"artifact": artifact},
        success_criteria=["artifact must match", "task outcome must pass"],
        risk_assessment={"risk_level": "medium", "expected_loss": "none"},
        source="service-test",
    )
    assert expectation["feature_code"] == "G11"
    assert expectation["task_id"] == task.task_id
    expectation_memory = real_ci_runtime.memory_service.get_record(expectation["evidence_refs"][0]["memory_id"])
    assert expectation_memory is not None
    assert expectation_memory.target_id == task.task_id

    binding = kernel_service.bind_experience_outcome(
        session_id=session_id,
        expectation_id=expectation["expectation_id"],
        actual_outcome={"artifact": artifact},
        benefits=["repeatable verified path"],
        losses=[],
        source_reliability=0.9,
        strategy_patch={"lesson": "prefer verified g11 experience path", "applies_to_tags": ["g11", "experience"]},
    )
    _assert_binding(binding, session_id=session_id, task_id=task.task_id, artifact=artifact)
    queried = kernel_service.query_experience_binding(session_id=session_id, binding_id=binding["binding_id"])
    assert queried["query_visible"] is True
    assert queried["binding_id"] == binding["binding_id"]
    assert queried["deviation_report"] == binding["deviation_report"]

    ranking = kernel_service.rank_goals_with_experience(
        session_id=session_id,
        candidate_goals=[
            {"goal_id": "plain", "title": "unrelated maintenance", "base_score": 0.5},
            {"goal_id": "g11", "title": "g11 experience reuse", "base_score": 0.5, "tags": ["g11", "experience"]},
        ],
        context={"reason": "verify strategy patch affects subsequent sorting"},
    )
    assert ranking["ranked_goals"][0]["goal_id"] == "g11"
    assert ranking["ranked_goals"][0]["experience_refs"][0]["binding_id"] == binding["binding_id"]
    assert ranking["ranked_goals"][0]["experience_adjusted_score"] > ranking["ranked_goals"][1]["experience_adjusted_score"]

    with pytest.raises(ValueError, match="IdentityKernel"):
        kernel_service.bind_experience_outcome(
            session_id=session_id,
            expectation_id=expectation["expectation_id"],
            actual_outcome={"artifact": artifact},
            strategy_patch={"identity_override": {"allow_unsafe": True}},
        )

    entries = kernel_service.get_transcript(session_id, limit=300)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G11"}
    assert {
        "g11_experience_expectation_registered",
        "g11_experience_outcome_bound",
        "g11_experience_binding_queried",
        "g11_experience_goals_ranked",
    } <= event_types


@pytest.mark.asyncio
async def test_g11_experience_engine_api_requests_register_bind_query_and_rank_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    artifact = f"api-artifact-{suffix}"
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g11-api-{suffix}")
    task = await _create_completed_task(real_ci_runtime, suffix=f"api-{suffix}", artifact=artifact)
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        expectation_response = requests.post(
            f"{base_url}/api/web/runtime/experience-engine/expectations",
            json={
                "session_id": session_id,
                "task_id": task.task_id,
                "expected_outcome": {"artifact": artifact},
                "success_criteria": ["artifact must match", "task outcome must pass"],
                "risk_assessment": {"risk_level": "medium"},
                "source": "api-test",
            },
            timeout=20,
        )
        assert expectation_response.status_code == 200, expectation_response.text
        expectation = expectation_response.json()
        binding_response = requests.post(
            f"{base_url}/api/web/runtime/experience-engine/bindings",
            json={
                "session_id": session_id,
                "expectation_id": expectation["expectation_id"],
                "actual_outcome": {"artifact": artifact},
                "benefits": ["api verified writeback"],
                "losses": [],
                "source_reliability": 0.85,
                "strategy_patch": {"lesson": "reuse api verified g11 path", "applies_to_tags": ["api", "g11"]},
            },
            timeout=20,
        )
        assert binding_response.status_code == 200, binding_response.text
        binding = binding_response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/experience-engine/bindings/{binding['binding_id']}",
            params={"session_id": session_id},
            timeout=20,
        )
        ranking_response = requests.post(
            f"{base_url}/api/web/runtime/experience-engine/goal-ranking",
            json={
                "session_id": session_id,
                "candidate_goals": [
                    {"goal_id": "api-unrelated", "title": "unrelated work", "base_score": 0.5},
                    {"goal_id": "api-g11", "title": "api g11 reuse", "base_score": 0.5, "tags": ["api", "g11"]},
                ],
                "context": {"reason": "api ranking verification"},
            },
            timeout=20,
        )

    _assert_binding(binding, session_id=session_id, task_id=task.task_id, artifact=artifact)
    assert query_response.status_code == 200, query_response.text
    assert query_response.json()["binding_id"] == binding["binding_id"]
    assert ranking_response.status_code == 200, ranking_response.text
    ranking = ranking_response.json()
    assert ranking["ranked_goals"][0]["goal_id"] == "api-g11"
    assert ranking["ranked_goals"][0]["experience_refs"][0]["binding_id"] == binding["binding_id"]
