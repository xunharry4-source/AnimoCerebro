from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.governance.test_trace_observability_real import (
    STAGES,
    _healthy_payload,
)
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def test_feature67_trace_replay_api_reconstructs_queries_diff_and_blocks_unsafe_sandbox(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    healthy = _healthy_payload(f"replay-{suffix}")
    failed = _healthy_payload(f"replay-failed-{suffix}")
    failed["spans"][5]["status"] = "failed"
    failed["spans"][5]["error_code"] = "timeout.execution"
    failed["spans"][5]["retry_count"] = 3
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        capabilities = requests.get(f"{base_url}/api/web/trace-replay/capabilities", timeout=10)
        assert capabilities.status_code == 200
        capability_payload = capabilities.json()
        assert capability_payload["lookup_keys"] == ["trace_id", "task_id", "request_id", "decision_id", "agent_id"]
        assert capability_payload["views"] == [
            "call_tree",
            "timeline",
            "state_machine",
            "error_distribution",
            "evidence",
        ]
        assert "sandbox" in capability_payload["modes"]
        assert "production side effects are never enabled by replay APIs" in capability_payload["safety_rules"]

        healthy_observation = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=healthy,
            timeout=10,
        )
        assert healthy_observation.status_code == 200
        healthy_report = healthy_observation.json()
        assert healthy_report["observability_status"] == "healthy"
        assert len(healthy_report["source_spans"]) == len(STAGES)

        failed_observation = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=failed,
            timeout=10,
        )
        assert failed_observation.status_code == 200
        failed_report = failed_observation.json()
        assert failed_report["observability_status"] == "broken"

        replay_response = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={"trace_id": healthy["trace_id"], "mode": "read_only"},
            timeout=10,
        )
        assert replay_response.status_code == 200
        replay = replay_response.json()
        assert replay["trace_id"] == healthy["trace_id"]
        assert replay["source_observation_id"] == healthy_report["observation_id"]
        assert replay["mode"] == "read_only"
        assert replay["executable_actions_enabled"] is False
        assert replay["production_side_effects_enabled"] is False
        assert replay["reconstruction_status"] == "complete"
        assert replay["warnings"] == []
        assert [row["stage"] for row in replay["timeline"]] == list(STAGES)
        assert replay["timeline"][0]["span_id"] == healthy["spans"][0]["span_id"]
        assert replay["call_tree"][0]["children"][0]["span_id"] == healthy["spans"][1]["span_id"]
        assert replay["state_machine"][0]["transition_count"] == len(STAGES)
        assert replay["state_machine"][0]["final_state"] == "memory_writeback:success"
        assert replay["error_distribution"] == {
            "by_stage": {},
            "by_module": {},
            "by_error_code": {},
            "failure_chain": [],
        }
        assert replay["evidence_bundle"]["complete"] is True
        assert replay["evidence_bundle"]["refs_by_kind"]["replay"]
        assert replay["evidence_bundle"]["refs_by_kind"]["audit"]
        assert replay["key_decision_points"][0]["stage"] == "safety_review"
        assert replay["postmortem_report"]["root_cause"] == "no_failure_detected"
        assert replay["postmortem_report"]["regression_tests_needed"] == [
            "requests_api_replay_read_after_write",
            "healthy_trace_replay_regression",
        ]

        fetched = requests.get(
            f"{base_url}/api/web/trace-replay/replays/{replay['replay_id']}",
            timeout=10,
        )
        assert fetched.status_code == 200
        assert fetched.json() == replay

        by_task = requests.get(
            f"{base_url}/api/web/trace-replay/replays",
            params={"task_id": healthy["spans"][0]["task_id"]},
            timeout=10,
        )
        assert by_task.status_code == 200
        assert [item["replay_id"] for item in by_task.json()] == [replay["replay_id"]]

        sandbox_rejected = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={"trace_id": healthy["trace_id"], "mode": "sandbox"},
            timeout=10,
        )
        assert sandbox_rejected.status_code == 409
        assert sandbox_rejected.json()["detail"] == "sandbox replay requires sandbox_confirmation=true"

        sandbox_replay = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={
                "trace_id": healthy["trace_id"],
                "mode": "sandbox",
                "sandbox_confirmation": True,
            },
            timeout=10,
        )
        assert sandbox_replay.status_code == 200
        sandbox_payload = sandbox_replay.json()
        assert sandbox_payload["mode"] == "sandbox"
        assert sandbox_payload["production_side_effects_enabled"] is False
        assert sandbox_payload["executable_actions_enabled"] is False

        diff_response = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={
                "trace_id": healthy["trace_id"],
                "mode": "diff",
                "compare_trace_id": failed["trace_id"],
            },
            timeout=10,
        )
        assert diff_response.status_code == 200
        diff_payload = diff_response.json()
        assert diff_payload["mode"] == "diff"
        assert diff_payload["diff_report"]["left_trace_id"] == healthy["trace_id"]
        assert diff_payload["diff_report"]["right_trace_id"] == failed["trace_id"]
        assert diff_payload["diff_report"]["status_changed"] is True
        assert "timeout.execution" in diff_payload["diff_report"]["right_only_errors"]
        assert any("execution" in item for item in diff_payload["diff_report"]["added_steps"])
        assert any("execution" in item for item in diff_payload["diff_report"]["missing_steps"])

        failed_replay_response = requests.post(
            f"{base_url}/api/web/trace-replay/replays",
            json={"trace_id": failed["trace_id"], "mode": "read_only"},
            timeout=10,
        )
        assert failed_replay_response.status_code == 200
        failed_replay = failed_replay_response.json()
        assert failed_replay["reconstruction_status"] == "complete"
        assert failed_replay["postmortem_report"]["root_cause"] == "execution::cli::timeout.execution"
        assert failed_replay["error_distribution"]["by_stage"] == {"execution": 1}
        assert failed_replay["error_distribution"]["by_error_code"]["timeout.execution"] == 1
        assert failed_replay["postmortem_report"]["failure_chain"][0]["span_id"] == failed["spans"][5]["span_id"]

    audit_payloads = [
        entry["payload"]
        for entry in acceptance_app.state.transcript_store.entries[before_audit_count:]
    ]
    assert any(
        payload["event"] == "trace_replay_built"
        and payload["trace_id"] == healthy["trace_id"]
        and payload["mode"] == "read_only"
        and payload["reconstruction_status"] == "complete"
        and payload["production_side_effects_enabled"] is False
        for payload in audit_payloads
    )
    assert any(
        payload["event"] == "trace_replay_built"
        and payload["trace_id"] == failed["trace_id"]
        and payload["root_cause"] == "execution::cli::timeout.execution"
        for payload in audit_payloads
    )
