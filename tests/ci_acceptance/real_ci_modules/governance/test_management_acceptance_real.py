from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


MODULES = ["plugin", "task", "agent", "cli", "mcp"]
TEST_CATEGORIES = ["unit", "integration", "main_chain", "failure_path", "degraded_path", "rollback_path", "real_environment"]
FAULT_CATEGORIES = ["timeout", "disconnect", "permission_denied", "version_conflict", "bad_structure", "fake_health", "audit_chain_missing"]


def _module_evidence(module_name: str, suffix: str) -> dict[str, object]:
    return {
        "module_name": module_name,
        "diagnostic_report": {
            "checks": [
                {"name": "health_probe_check", "passed": True},
                {"name": "status_consistency_check", "passed": True},
                {"name": "permission_boundary_check", "passed": True},
                {"name": "audit_chain_check", "passed": True},
            ],
            "metrics": {"real_fixture": f"{module_name}-{suffix}"},
            "completion": {
                "structural_complete": True,
                "main_chain_complete": True,
                "real_completion": True,
            },
        },
        "fault_injection_report": {
            "passed": True,
            "cases": [{"name": category, "passed": True} for category in FAULT_CATEGORIES],
        },
        "test_evidence": [
            {
                "category": category,
                "name": f"{module_name}-{category}-{suffix}",
                "command": f"python3 -m pytest tests/ci_acceptance/real_ci_modules/{module_name}",
                "passed": True,
                "used_real_service": True,
                "used_requests": category == "real_environment",
                "evidence_refs": [f"tests://{module_name}/{category}/{suffix}"],
                "checked_business_result": category in {"main_chain", "real_environment"},
                "checked_persisted_state": category in {"rollback_path", "real_environment"},
                "checked_audit_chain": category in {"failure_path", "real_environment"},
            }
            for category in TEST_CATEGORIES
        ],
        "fault_evidence": [
            {
                "category": category,
                "name": f"{module_name}-{category}-fault-{suffix}",
                "injected": True,
                "observed_expected_result": True,
                "error_code": f"{module_name.upper()}_{category.upper()}",
                "evidence_refs": [f"fault://{module_name}/{category}/{suffix}"],
            }
            for category in FAULT_CATEGORIES
        ],
        "completion_claim": {
            "structural_complete": True,
            "main_chain_complete": True,
            "real_complete": True,
        },
        "source_refs": [f"feature65://{module_name}/{suffix}"],
    }


def test_feature65_management_acceptance_api_blocks_gaps_and_persists_real_evaluations(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        matrix = requests.get(f"{base_url}/api/web/management-acceptance/matrix", timeout=10)
        assert matrix.status_code == 200
        matrix_payload = matrix.json()
        assert matrix_payload["modules"] == MODULES
        assert matrix_payload["required_test_categories"] == TEST_CATEGORIES
        assert matrix_payload["required_fault_categories"] == FAULT_CATEGORIES
        assert matrix_payload["completion_tiers"] == ["structural", "main_chain", "real"]

        valid_request = {
            "request_id": f"feature65-valid-{suffix}",
            "release_candidate": f"feature65-release-{suffix}",
            "operator": "feature65-real-test",
            "modules": [_module_evidence(module, suffix) for module in MODULES],
        }
        valid_response = requests.post(
            f"{base_url}/api/web/management-acceptance/evaluations",
            json=valid_request,
            timeout=10,
        )
        assert valid_response.status_code == 200, valid_response.text
        valid_payload = valid_response.json()
        assert valid_payload["request_id"] == valid_request["request_id"]
        assert valid_payload["release_candidate"] == valid_request["release_candidate"]
        assert valid_payload["release_decision"] == "allowed"
        assert valid_payload["blockers"] == []
        assert valid_payload["completion_summary"] == {
            "required_module_count": 5,
            "submitted_module_count": 5,
            "structural_complete_count": 5,
            "main_chain_complete_count": 5,
            "real_complete_count": 5,
        }
        valid_results = {item["module_name"]: item for item in valid_payload["module_results"]}
        assert set(valid_results) == set(MODULES)
        for module_name, result in valid_results.items():
            assert result["structural_complete"] is True, module_name
            assert result["main_chain_complete"] is True, module_name
            assert result["real_complete"] is True, module_name
            assert result["blocking"] is False, module_name
            assert result["gaps"] == []
            assert "test:real_environment" in result["passed_requirements"]
            assert "verification:audit" in result["passed_requirements"]

        fetched = requests.get(
            f"{base_url}/api/web/management-acceptance/evaluations/{valid_payload['evaluation_id']}",
            timeout=10,
        )
        assert fetched.status_code == 200
        assert fetched.json() == valid_payload

        listed = requests.get(f"{base_url}/api/web/management-acceptance/evaluations", timeout=10)
        assert listed.status_code == 200
        assert any(item["evaluation_id"] == valid_payload["evaluation_id"] for item in listed.json())

        invalid_modules = [_module_evidence(module, suffix) for module in MODULES]
        invalid_modules = [dict(item) for item in invalid_modules]
        invalid_modules[2]["test_evidence"] = [
            item for item in invalid_modules[2]["test_evidence"] if item["category"] != "failure_path"
        ]
        invalid_modules[4]["fault_evidence"] = [
            item for item in invalid_modules[4]["fault_evidence"] if item["category"] != "bad_structure"
        ]
        invalid_request = {
            "request_id": f"feature65-invalid-{suffix}",
            "release_candidate": f"feature65-bad-release-{suffix}",
            "operator": "feature65-real-test",
            "modules": invalid_modules,
        }
        invalid_response = requests.post(
            f"{base_url}/api/web/management-acceptance/evaluations",
            json=invalid_request,
            timeout=10,
        )
        assert invalid_response.status_code == 200, invalid_response.text
        invalid_payload = invalid_response.json()
        assert invalid_payload["release_decision"] == "blocked"
        blocker_codes = {(item["module_name"], item["code"]) for item in invalid_payload["blockers"]}
        assert ("agent", "test_failure_path_missing") in blocker_codes
        assert ("mcp", "fault_bad_structure_missing") in blocker_codes
        invalid_results = {item["module_name"]: item for item in invalid_payload["module_results"]}
        assert invalid_results["agent"]["real_complete"] is False
        assert invalid_results["mcp"]["real_complete"] is False
        assert invalid_payload["completion_summary"]["real_complete_count"] == 3

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    audit_payloads = [entry.get("payload") or {} for entry in new_audits]
    assert any(
        payload.get("event") == "management_acceptance_evaluated"
        and payload.get("request_id") == f"feature65-valid-{suffix}"
        and payload.get("release_decision") == "allowed"
        for payload in audit_payloads
    )
    assert any(
        payload.get("event") == "management_acceptance_evaluated"
        and payload.get("request_id") == f"feature65-invalid-{suffix}"
        and payload.get("release_decision") == "blocked"
        and payload.get("blocker_count") == 2
        for payload in audit_payloads
    )
