from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.governance.test_trace_observability_real import (
    _healthy_payload,
)
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


TEST_CATEGORIES = (
    "unit",
    "integration",
    "main_chain",
    "replay",
    "error_response",
    "real_acceptance",
)
FAULT_CATEGORIES = (
    "trace_break",
    "span_missing",
    "clock_drift",
    "error_code_missing",
    "error_stage_wrong",
    "replay_data_missing",
    "audit_ref_lost",
    "fake_success_internal_failure",
)


def _raw_error(module: str, raw_error_type: str, trace_id: str, task_id: str, suffix: str) -> dict:
    return {
        "module": module,
        "raw_error_type": raw_error_type,
        "raw_message": f"{module} {raw_error_type} real acceptance raw detail {suffix}",
        "trace_id": trace_id,
        "related_refs": {
            "request_id": f"request-{trace_id}",
            "task_id": task_id,
            "decision_id": f"decision-{trace_id}",
            "receipt_id": f"receipt-{trace_id}-{module}",
            "plugin_id": f"plugin-{suffix}" if module == "plugin" else None,
            "agent_id": f"agent-{suffix}" if module == "agent" else None,
            "server_id": f"mcp-{suffix}" if module == "mcp" else None,
        },
        "evidence_refs": [f"audit:{trace_id}:{module}", f"replay:{trace_id}:{module}"],
        "source_status_code": 409,
    }


def _test_evidence(suffix: str) -> list[dict]:
    rows = []
    for category in TEST_CATEGORIES:
        rows.append(
            {
                "category": category,
                "name": f"{category} real acceptance {suffix}",
                "command": "python3 -m pytest tests/ci_acceptance/real_ci_modules/governance",
                "passed": True,
                "used_real_service": True,
                "used_requests": category == "real_acceptance",
                "checked_business_result": category in {"main_chain", "real_acceptance"},
                "checked_persisted_state": category in {"replay", "real_acceptance"},
                "checked_audit_chain": category in {"error_response", "real_acceptance"},
                "evidence_refs": [f"test:{category}:{suffix}"],
            }
        )
    return rows


def _fault_evidence(suffix: str) -> list[dict]:
    return [
        {
            "category": category,
            "name": f"{category} injected {suffix}",
            "injected": True,
            "observed_expected_result": True,
            "evidence_refs": [f"fault:{category}:{suffix}"],
        }
        for category in FAULT_CATEGORIES
    ]


def _make_broken_payload(suffix: str) -> dict:
    broken = _healthy_payload(f"acceptance-broken-{suffix}")
    broken["spans"] = [
        span for span in broken["spans"] if span["stage"] not in {"safety_review", "reflection"}
    ]
    broken["spans"][2]["parent_span_id"] = "missing-parent-span"
    broken["spans"][3]["input_summary"] = "ok"
    broken["spans"][3]["evidence_refs"] = []
    broken["spans"][4]["status"] = "failed"
    broken["spans"][4]["error_code"] = "timeout.execution"
    broken["spans"][4]["retry_count"] = 3
    broken["spans"][4]["duration_ms"] = 1500
    return broken


def test_feature69_observability_acceptance_api_closes_real_trace_replay_error_loop(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    healthy = _healthy_payload(f"acceptance-{suffix}")
    broken = _make_broken_payload(suffix)
    failed = _healthy_payload(f"acceptance-failed-{suffix}")
    failed["spans"][5]["status"] = "failed"
    failed["spans"][5]["error_code"] = "timeout.execution"
    failed["spans"][5]["retry_count"] = 3
    task_id = healthy["spans"][0]["task_id"]
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        healthy_observation = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=healthy,
            timeout=10,
        ).json()
        broken_observation = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=broken,
            timeout=10,
        ).json()
        failed_observation = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=failed,
            timeout=10,
        ).json()
        assert healthy_observation["observability_status"] == "healthy"
        assert broken_observation["observability_status"] == "broken"
        assert failed_observation["observability_status"] == "broken"

        healthy_replay = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={"trace_id": healthy["trace_id"], "mode": "read_only"},
            timeout=10,
        ).json()
        broken_replay = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={"trace_id": failed["trace_id"], "mode": "read_only"},
            timeout=10,
        ).json()
        diff_replay = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={
                "trace_id": healthy["trace_id"],
                "mode": "diff",
                "compare_trace_id": failed["trace_id"],
            },
            timeout=10,
        ).json()
        assert healthy_replay["reconstruction_status"] == "complete"
        assert broken_replay["postmortem_report"]["root_cause"] == "execution::cli::timeout.execution"
        assert diff_replay["diff_report"]["status_changed"] is True

        error_ids = []
        for module, raw_type in (
            ("plugin", "schema_error"),
            ("task", "invalid_state_transition"),
            ("agent", "handshake_failed"),
            ("cli", "timeout"),
            ("mcp", "bad_json"),
            ("safety", "permission_denied"),
        ):
            response = requests.post(
                f"{base_url}/api/web/unified-errors",
                json=_raw_error(module, raw_type, healthy["trace_id"], task_id, suffix),
                timeout=10,
            )
            assert response.status_code == 200
            error_ids.append(response.json()["unified_error"]["error_id"])

        matrix = requests.get(f"{base_url}/api/web/observability-acceptance/matrix", timeout=10)
        assert matrix.status_code == 200
        matrix_payload = matrix.json()
        assert matrix_payload["required_test_categories"] == list(TEST_CATEGORIES)
        assert matrix_payload["required_fault_categories"] == list(FAULT_CATEGORIES)
        assert "trace_observability_evaluated" in matrix_payload["required_audit_events"]
        assert "unified_error_mapped" in matrix_payload["required_audit_events"]

        valid_request = {
            "request_id": f"obs-acceptance-valid-{suffix}",
            "release_candidate": f"feature69-valid-{suffix}",
            "observation_ids": [
                healthy_observation["observation_id"],
                broken_observation["observation_id"],
            ],
            "replay_ids": [
                healthy_replay["replay_id"],
                broken_replay["replay_id"],
                diff_replay["replay_id"],
            ],
            "unified_error_ids": error_ids,
            "test_evidence": _test_evidence(suffix),
            "fault_evidence": _fault_evidence(suffix),
            "operator": "feature69-real-test",
        }
        valid_response = requests.post(
            f"{base_url}/api/web/observability-acceptance/evaluations",
            json=valid_request,
            timeout=10,
        )
        assert valid_response.status_code == 200
        valid_report = valid_response.json()
        assert valid_report["release_decision"] == "allowed"
        assert valid_report["observability_complete"] is True
        assert valid_report["replay_complete"] is True
        assert valid_report["error_response_complete"] is True
        assert valid_report["real_complete"] is True
        assert valid_report["blockers"] == []
        assert valid_report["completion_summary"]["submitted_observation_count"] == 2
        assert valid_report["completion_summary"]["submitted_replay_count"] == 3
        assert valid_report["completion_summary"]["submitted_unified_error_count"] == len(error_ids)
        assert "observability:fault_detection" in valid_report["passed_checks"]
        assert "replay:diff" in valid_report["passed_checks"]
        assert "errors:disposition_coverage" in valid_report["passed_checks"]
        assert "audit:required_events" in valid_report["passed_checks"]

        fetched = requests.get(
            f"{base_url}/api/web/observability-acceptance/evaluations/{valid_report['evaluation_id']}",
            timeout=10,
        )
        assert fetched.status_code == 200
        assert fetched.json() == valid_report

        listed = requests.get(f"{base_url}/api/web/observability-acceptance/evaluations", timeout=10)
        assert listed.status_code == 200
        assert valid_report["evaluation_id"] in {item["evaluation_id"] for item in listed.json()}

        invalid_request = dict(valid_request)
        invalid_request["request_id"] = f"obs-acceptance-invalid-{suffix}"
        invalid_request["release_candidate"] = f"feature69-invalid-{suffix}"
        invalid_request["observation_ids"] = [healthy_observation["observation_id"]]
        invalid_request["test_evidence"] = [
            item for item in valid_request["test_evidence"] if item["category"] != "error_response"
        ]
        invalid_request["fault_evidence"] = [
            item for item in valid_request["fault_evidence"] if item["category"] != "replay_data_missing"
        ]
        invalid_response = requests.post(
            f"{base_url}/api/web/observability-acceptance/evaluations",
            json=invalid_request,
            timeout=10,
        )
        assert invalid_response.status_code == 200
        invalid_report = invalid_response.json()
        assert invalid_report["release_decision"] == "blocked"
        assert invalid_report["real_complete"] is False
        blocker_codes = {item["code"] for item in invalid_report["blockers"]}
        assert {
            "broken_observation_missing",
            "test_error_response_missing",
            "fault_replay_data_missing_missing",
        } <= blocker_codes

    audit_payloads = [
        entry["payload"]
        for entry in acceptance_app.state.transcript_store.entries[before_audit_count:]
    ]
    assert any(
        payload.get("event") == "observability_acceptance_evaluated"
        and payload.get("release_candidate") == f"feature69-valid-{suffix}"
        and payload.get("release_decision") == "allowed"
        and payload.get("real_complete") is True
        for payload in audit_payloads
    )
    assert any(
        payload.get("event") == "observability_acceptance_evaluated"
        and payload.get("release_candidate") == f"feature69-invalid-{suffix}"
        and payload.get("release_decision") == "blocked"
        and payload.get("blocker_count") >= 3
        for payload in audit_payloads
    )
