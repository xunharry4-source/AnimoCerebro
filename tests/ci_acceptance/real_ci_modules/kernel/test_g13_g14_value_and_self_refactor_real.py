from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import requests
from fastapi import FastAPI, Request

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _capability_doc_app(*, suffix: str) -> FastAPI:
    app = FastAPI()

    @app.get("/docs/self-refactor-validator.json")
    def self_refactor_doc(request: Request) -> dict[str, Any]:
        base = str(request.base_url).rstrip("/")
        return {
            "tool_name": f"g14_self_refactor_validator_{suffix}",
            "version": "1.0.0",
            "description": "Validate bounded self-refactor proposals using a real HTTP verifier.",
            "usage_example": {"proposal_kind": "single_file_replacement"},
            "input_schema": {"type": "object", "required": ["proposal_kind"]},
            "output_schema": {"type": "object", "required": ["allowed"]},
            "verification_endpoint": f"{base}/tools/self-refactor/verify",
            "verification_cases": [
                {
                    "input": {"proposal_kind": "single_file_replacement"},
                    "expected_output": {"allowed": True, "scope": "bounded"},
                }
            ],
        }

    @app.post("/tools/self-refactor/verify")
    def verify(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload == {"proposal_kind": "single_file_replacement"}
        return {"allowed": True, "scope": "bounded", "source": "real_http_verifier"}

    return app


def _register_self_refactor_capability(kernel_service: Any, session_id: str, suffix: str) -> str:
    with live_http_server(_capability_doc_app(suffix=suffix)) as doc_url:
        learned = kernel_service.learn_dynamic_tool_capability(
            session_id=session_id,
            documentation_url=f"{doc_url}/docs/self-refactor-validator.json",
            source_kind="real_document",
            timeout_seconds=2,
        )
    assert learned["registered"] is True
    assert learned["capability_registration"]["verification_status"] == "real_verified"
    return learned["capability_id"]


def test_g13_value_engine_blocks_budgeted_capabilities_ranks_authorized_goal_and_query_is_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g13-service-{suffix}")

    decision = kernel_service.evaluate_value_engine(
        session_id=session_id,
        candidate_goals=[
            {
                "goal_id": f"safe-continuity-{suffix}",
                "title": "preserve continuity under low budget",
                "expected_value": 0.62,
                "urgency": 0.7,
                "risk": 0.12,
                "cost": 0.15,
                "continuity": 0.95,
                "authorized": True,
                "audit_passed": True,
                "rollback_ready": True,
            },
            {
                "goal_id": f"unauthorized-curiosity-{suffix}",
                "title": "run high-frequency curiosity without approval",
                "expected_value": 0.98,
                "urgency": 0.9,
                "risk": 0.82,
                "cost": 0.8,
                "creativity": 0.95,
                "requires_authorization": True,
                "authorized": False,
                "audit_passed": True,
                "rollback_ready": True,
                "capability": "G24",
            },
        ],
        resource_state={
            "compute_remaining_ratio": 0.1,
            "token_remaining_ratio": 0.12,
            "time_remaining_ratio": 0.5,
            "budget_pressure": "high",
        },
        risk_state={"risk_level": "high", "entropy": 0.74},
        requested_capabilities=["G14", "G24"],
    )
    queried = kernel_service.query_value_engine_decision(
        session_id=session_id,
        decision_id=decision["decision_id"],
    )

    assert decision["feature_code"] == "G13"
    assert decision["thought_mode"] == "fast"
    assert decision["budget_gate"]["status"] == "blocked"
    assert decision["budget_gate"]["thought_cost_profile"]["minimum_remaining_ratio"] == 0.1
    assert decision["budget_gate"]["thought_cost_profile"]["budget_pressure"] == "high"
    assert set(decision["budget_gate"]["blocked_capabilities"]) == {"G14", "G24"}
    assert decision["recommended_goal_id"] == f"safe-continuity-{suffix}"
    assert decision["ranked_goals"][0]["goal_id"] == f"safe-continuity-{suffix}"
    assert decision["ranked_goals"][0]["hard_boundary_blocked"] is False
    assert decision["ranked_goals"][-1]["goal_id"] == f"unauthorized-curiosity-{suffix}"
    assert decision["ranked_goals"][-1]["hard_boundary_reasons"] == ["authorization_boundary"]
    assert queried["query_visible"] is True
    assert queried["ranked_goals"] == decision["ranked_goals"]
    memory_ref = next(ref for ref in decision["evidence_refs"] if ref["type"] == "memory")
    memory = real_ci_runtime.memory_service.get_record(memory_ref["memory_id"])
    assert memory is not None
    assert memory.target_id == decision["decision_id"]


def test_g13_weight_drift_rolls_back_to_conservative_profile_and_api_requests_query_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g13-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    runtime_app = FastAPI()
    runtime_app.include_router(api_router)

    with live_http_server(runtime_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/runtime/value-engine/evaluate",
            json={
                "session_id": session_id,
                "candidate_goals": [
                    {
                        "goal_id": f"stable-goal-{suffix}",
                        "expected_value": 0.7,
                        "urgency": 0.4,
                        "risk": 0.2,
                        "cost": 0.2,
                        "continuity": 0.9,
                        "authorized": True,
                        "audit_passed": True,
                        "rollback_ready": True,
                    }
                ],
                "resource_state": {
                    "compute_remaining_ratio": 0.8,
                    "token_remaining_ratio": 0.8,
                    "time_remaining_ratio": 0.8,
                },
                "risk_state": {"risk_level": "medium", "entropy": 0.3},
                "weight_profile": {
                    "risk_tolerance": 0.95,
                    "cost_sensitivity": 0.05,
                    "creativity_bias": 0.95,
                    "continuity_bias": 0.02,
                },
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        decision = response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/value-engine/decisions/{decision['decision_id']}",
            params={"session_id": session_id},
            timeout=20,
        )

    assert decision["weight_audit"]["status"] == "rejected"
    assert decision["weight_snapshot"]["active_weight_plugin_id"] == "default_conservative_weight"
    assert decision["weight_snapshot"]["weight_fallback_occurred"] is True
    assert decision["budget_gate"]["status"] == "approved"
    assert decision["recommended_goal_id"] == f"stable-goal-{suffix}"
    assert query_response.status_code == 200, query_response.text
    queried = query_response.json()
    assert queried["query_visible"] is True
    assert queried["weight_snapshot"] == decision["weight_snapshot"]


def test_g14_self_refactor_merges_after_g12_g13_g25_sandbox_and_query_checks_file(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g14-service-{suffix}")
    capability_id = _register_self_refactor_capability(kernel_service, session_id, suffix)
    target = tmp_path / "calc_module.py"
    original = "def score():\n    return 1\n"
    replacement = "def score():\n    return 2\n"
    target.write_text(original, encoding="utf-8")

    proposal = kernel_service.submit_self_refactor_proposal(
        session_id=session_id,
        workspace_root=str(tmp_path),
        target_path=str(target),
        bottleneck_evidence={"metric": "score_staleness", "before": 1, "expected": 2},
        change_summary="Replace stale score constant after bottleneck evidence.",
        replacement={"find": original, "replace": replacement},
        sandbox_commands=[[sys.executable, "-m", "py_compile", "calc_module.py"]],
        capability_id=capability_id,
        resource_state={
            "compute_remaining_ratio": 0.9,
            "token_remaining_ratio": 0.9,
            "time_remaining_ratio": 0.9,
        },
        risk_state={"risk_level": "medium", "entropy": 0.2},
    )
    queried = kernel_service.query_self_refactor_proposal(
        session_id=session_id,
        proposal_id=proposal["proposal_id"],
    )

    assert proposal["feature_code"] == "G14"
    assert proposal["status"] == "merged"
    assert proposal["g12_approval"]["status"] == "approved"
    assert proposal["g13_decision"]["recommended_goal_id"] == proposal["proposal_id"]
    assert proposal["g25_approval"]["g18_self_shaping_blocked"] is False
    assert proposal["sandbox"]["status"] == "passed"
    assert proposal["post_merge_verification"]["status"] == "passed"
    assert proposal["evidence_bundle"]["all_required_evidence_present"] is True
    assert proposal["coding_completion_gate"]["allowed_to_merge"] is True
    assert proposal["coding_completion_gate"]["missing_evidence"] == []
    assert proposal["read_after_write"]["contains_replacement"] is True
    assert target.read_text(encoding="utf-8") == replacement
    assert queried["query_visible"] is True
    assert queried["status"] == "merged"
    memory_ref = next(ref for ref in proposal["evidence_refs"] if ref["type"] == "memory")
    memory = real_ci_runtime.memory_service.get_record(memory_ref["memory_id"])
    assert memory is not None
    assert memory.target_id == proposal["proposal_id"]


def test_g14_self_refactor_freezes_protected_path_and_keeps_file_unchanged(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g14-freeze-{suffix}")
    protected_dir = tmp_path / "src" / "zentex" / "safety"
    protected_dir.mkdir(parents=True)
    target = protected_dir / "guard.py"
    original = "SAFE = True\n"
    target.write_text(original, encoding="utf-8")

    proposal = kernel_service.submit_self_refactor_proposal(
        session_id=session_id,
        workspace_root=str(tmp_path),
        target_path=str(target),
        bottleneck_evidence={"metric": "none", "reason": "protected path test"},
        change_summary="Attempt to edit protected safety module.",
        replacement={"find": original, "replace": "SAFE = False\n"},
        sandbox_commands=[[sys.executable, "-m", "py_compile", "src/zentex/safety/guard.py"]],
        capability_id="not-used-because-protected-path-freezes-first",
    )
    queried = kernel_service.query_self_refactor_proposal(
        session_id=session_id,
        proposal_id=proposal["proposal_id"],
    )

    assert proposal["status"] == "frozen"
    assert proposal["merged"] is False
    assert proposal["freeze_reason"] == "protected_path:src/zentex/safety"
    assert target.read_text(encoding="utf-8") == original
    assert queried["status"] == "frozen"


def test_g14_self_refactor_api_requests_merge_then_query_and_file_contains_change(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g14-api-{suffix}")
    capability_id = _register_self_refactor_capability(kernel_service, session_id, suffix)
    target = tmp_path / "api_module.py"
    original = "VALUE = 'old-path'\n"
    replacement = "VALUE = 'new-path'\n"
    target.write_text(original, encoding="utf-8")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    runtime_app = FastAPI()
    runtime_app.include_router(api_router)

    with live_http_server(runtime_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/runtime/self-refactor/proposals",
            json={
                "session_id": session_id,
                "workspace_root": str(tmp_path),
                "target_path": str(target),
                "bottleneck_evidence": {"metric": "branch_misprediction", "before": "old-path"},
                "change_summary": "Switch API module constant after bounded performance evidence.",
                "replacement": {"find": original, "replace": replacement},
                "sandbox_commands": [[sys.executable, "-m", "py_compile", "api_module.py"]],
                "capability_id": capability_id,
                "resource_state": {
                    "compute_remaining_ratio": 0.95,
                    "token_remaining_ratio": 0.95,
                    "time_remaining_ratio": 0.95,
                },
                "risk_state": {"risk_level": "medium", "entropy": 0.2},
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        proposal = response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/self-refactor/proposals/{proposal['proposal_id']}",
            params={"session_id": session_id},
            timeout=20,
        )

    assert proposal["status"] == "merged"
    assert proposal["sandbox"]["receipts"][0]["passed"] is True
    assert proposal["post_merge_verification"]["receipts"][0]["passed"] is True
    assert target.read_text(encoding="utf-8") == replacement
    assert query_response.status_code == 200, query_response.text
    queried = query_response.json()
    assert queried["query_visible"] is True
    assert queried["proposal_id"] == proposal["proposal_id"]
    assert queried["read_after_write"]["contains_replacement"] is True


def test_g14_self_refactor_rolls_back_when_real_sandbox_command_fails(
    real_ci_runtime,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g14-rollback-{suffix}")
    capability_id = _register_self_refactor_capability(kernel_service, session_id, suffix)
    target = tmp_path / "broken_module.py"
    original = "def stable():\n    return 'ok'\n"
    target.write_text(original, encoding="utf-8")

    proposal = kernel_service.submit_self_refactor_proposal(
        session_id=session_id,
        workspace_root=str(tmp_path),
        target_path=str(target),
        bottleneck_evidence={"metric": "syntax_guard", "case": "sandbox failure"},
        change_summary="Proposal must roll back when real syntax verification fails.",
        replacement={"find": original, "replace": "def stable(:\n    return 'broken'\n"},
        sandbox_commands=[[sys.executable, "-m", "py_compile", "broken_module.py"]],
        capability_id=capability_id,
    )

    assert proposal["status"] == "rolled_back"
    assert proposal["rollback"]["performed"] is True
    assert proposal["rollback"]["reason"] == "sandbox_failed"
    assert proposal["sandbox"]["status"] == "failed"
    assert proposal["evidence_bundle"]["all_required_evidence_present"] is False
    assert proposal["coding_completion_gate"]["allowed_to_merge"] is False
    assert "post_merge_verification" in proposal["coding_completion_gate"]["missing_evidence"]
    assert proposal["sandbox"]["receipts"][0]["passed"] is False
    assert target.read_text(encoding="utf-8") == original
    queried = kernel_service.query_self_refactor_proposal(
        session_id=session_id,
        proposal_id=proposal["proposal_id"],
    )
    assert queried["status"] == "rolled_back"
