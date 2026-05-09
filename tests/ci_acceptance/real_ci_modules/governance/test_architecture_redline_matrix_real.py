from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def test_architecture_redline_matrix_queries_and_enforces_llm_plugin_testing_rules_real_requests(
    acceptance_app: FastAPI,
) -> None:
    before_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        matrix = requests.get(f"{base_url}/api/web/architecture-redlines/matrix", timeout=10)
        assert matrix.status_code == 200
        matrix_payload = matrix.json()
        assert matrix_payload["status"] == "ready"
        assert matrix_payload["rule_count"] >= 8
        assert "role_inference" in matrix_payload["llm_mandatory_operations"]
        assert "question_body_assembly" in matrix_payload["llm_not_required_operations"]
        assert {"llm_boundary", "plugin_boundary", "architecture_boundary", "testing_integrity"}.issubset(
            set(matrix_payload["by_category"].keys())
        )

        allowed = requests.post(
            f"{base_url}/api/web/architecture-redlines/evaluate",
            json={
                "operation_type": "goal_generation",
                "trace_id": "feature47-allowed-goal-generation",
                "claims": {
                    "used_live_llm": True,
                    "llm_provider_configured": True,
                    "provider_error": False,
                    "used_rule_fallback": False,
                },
                "evidence_refs": ["transcript://feature47/live-llm"],
            },
            timeout=10,
        )
        assert allowed.status_code == 200, allowed.text
        allowed_payload = allowed.json()
        assert allowed_payload["allowed"] is True
        assert allowed_payload["decision"] == "allow"
        assert allowed_payload["violations"] == []
        assert "llm-live-required" in allowed_payload["checked_rule_ids"]

        missing_llm = requests.post(
            f"{base_url}/api/web/architecture-redlines/enforce",
            json={
                "operation_type": "role_inference",
                "trace_id": "feature47-missing-llm",
                "claims": {
                    "used_live_llm": False,
                    "llm_provider_configured": False,
                    "provider_error": True,
                    "used_rule_fallback": True,
                },
            },
            timeout=10,
        )
        assert missing_llm.status_code == 409
        missing_detail = missing_llm.json()["detail"]
        assert missing_detail["allowed"] is False
        assert missing_detail["decision"] == "block"
        missing_rule_ids = {item["rule_id"] for item in missing_detail["violations"]}
        assert {"llm-live-required", "llm-no-rule-disguise"}.issubset(missing_rule_ids)
        assert any("Provider failure" in item["message"] for item in missing_detail["violations"])

        cognitive_tool = requests.post(
            f"{base_url}/api/web/architecture-redlines/enforce",
            json={
                "operation_type": "cognitive_tool",
                "trace_id": "feature47-mutating-cognitive-tool",
                "claims": {
                    "mapped_domain": "cognitive",
                    "read_only": False,
                    "side_effect_free": False,
                    "mutates_state": True,
                    "has_rollback": True,
                    "has_degrade": True,
                    "has_audit": True,
                },
            },
            timeout=10,
        )
        assert cognitive_tool.status_code == 409
        cognitive_detail = cognitive_tool.json()["detail"]
        cognitive_rules = {item["rule_id"] for item in cognitive_detail["violations"]}
        assert "cognitive-tool-readonly" in cognitive_rules
        assert "execution-tool-domain-separation" in cognitive_rules

        fake_completion = requests.post(
            f"{base_url}/api/web/architecture-redlines/enforce",
            json={
                "operation_type": "test_evidence",
                "trace_id": "feature47-fake-completion",
                "claims": {
                    "completion_type": "REAL",
                    "happy_path_only": True,
                    "has_failure_path": False,
                    "has_timeout_path": False,
                    "has_disconnect_path": False,
                    "has_degradation_path": False,
                    "real_external_call": True,
                    "real_side_effect_verification": False,
                    "real_audit_chain": False,
                },
            },
            timeout=10,
        )
        assert fake_completion.status_code == 409
        fake_detail = fake_completion.json()["detail"]
        assert fake_detail["violations"][0]["rule_id"] == "real-test-evidence"
        assert "Happy-path-only" in fake_detail["violations"][0]["message"]

        audit = requests.get(f"{base_url}/api/web/architecture-redlines/audit", timeout=10)
        assert audit.status_code == 200
        audit_payload = audit.json()
        assert audit_payload["count"] >= 4
        by_trace = {item["trace_id"]: item for item in audit_payload["items"]}
        assert by_trace["feature47-allowed-goal-generation"]["allowed"] is True
        assert by_trace["feature47-missing-llm"]["allowed"] is False
        assert "llm-live-required" in by_trace["feature47-missing-llm"]["violation_rule_ids"]
        assert "real-test-evidence" in by_trace["feature47-fake-completion"]["violation_rule_ids"]

    assert len(acceptance_app.state.transcript_store.entries) >= before_count + 4


def test_architecture_redline_matrix_rejects_host_takeover_and_confirms_audit_query_real_requests(
    acceptance_app: FastAPI,
) -> None:
    with live_http_server(acceptance_app) as base_url:
        takeover = requests.post(
            f"{base_url}/api/web/architecture-redlines/enforce",
            json={
                "operation_type": "host_integration",
                "trace_id": "feature47-host-takeover",
                "claims": {
                    "takes_final_execution_authority": True,
                    "takes_final_reply_authority": True,
                    "host_independent": False,
                },
            },
            timeout=10,
        )
        assert takeover.status_code == 409
        detail = takeover.json()["detail"]
        rules = {item["rule_id"] for item in detail["violations"]}
        assert {"zentex-brain-not-executor", "host-independent"}.issubset(rules)

        audit = requests.get(f"{base_url}/api/web/architecture-redlines/audit", timeout=10)
        assert audit.status_code == 200
        matching = [item for item in audit.json()["items"] if item["trace_id"] == "feature47-host-takeover"]
        assert matching
        assert matching[-1]["decision"] == "block"
        assert "host-independent" in matching[-1]["violation_rule_ids"]

