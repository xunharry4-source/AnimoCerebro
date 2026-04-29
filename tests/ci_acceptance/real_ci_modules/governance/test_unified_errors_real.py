from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _raw_error(
    *,
    module: str,
    raw_error_type: str,
    raw_message: str,
    trace_id: str,
    task_id: str,
    stage: str | None = None,
    plugin_id: str | None = None,
    agent_id: str | None = None,
    server_id: str | None = None,
) -> dict:
    return {
        "module": module,
        "raw_error_type": raw_error_type,
        "raw_message": raw_message,
        "stage": stage,
        "trace_id": trace_id,
        "related_refs": {
            "request_id": f"request-{trace_id}",
            "task_id": task_id,
            "decision_id": f"decision-{trace_id}",
            "receipt_id": f"receipt-{trace_id}-{module}",
            "plugin_id": plugin_id,
            "agent_id": agent_id,
            "server_id": server_id,
            "replay_id": f"replay-{trace_id}",
        },
        "evidence_refs": [f"audit:{trace_id}:{module}", f"replay:{trace_id}:{module}"],
        "source_status_code": 409,
    }


def test_feature68_unified_error_api_maps_queries_statistics_and_audit_real_requests(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    trace_id = f"trace-feature68-{suffix}"
    task_id = f"task-feature68-{suffix}"
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    samples = [
        (
            _raw_error(
                module="plugin",
                raw_error_type="schema_error",
                raw_message="raw plugin schema mismatch: internal field should not leak to users",
                trace_id=trace_id,
                task_id=task_id,
                plugin_id=f"plugin-{suffix}",
            ),
            {
                "error_code": "PLUGIN_SCHEMA_INVALID",
                "error_category": "protocol",
                "error_stage": "plugin_call",
                "severity": "error",
                "retryable": False,
                "action": "manual_review",
            },
        ),
        (
            _raw_error(
                module="task",
                raw_error_type="invalid_state_transition",
                raw_message="cannot move archived task back to running",
                trace_id=trace_id,
                task_id=task_id,
            ),
            {
                "error_code": "TASK_STATE_TRANSITION_INVALID",
                "error_category": "state",
                "error_stage": "dispatch",
                "severity": "error",
                "retryable": False,
                "action": "block",
            },
        ),
        (
            _raw_error(
                module="agent",
                raw_error_type="handshake_failed",
                raw_message="agent handshake socket closed",
                trace_id=trace_id,
                task_id=task_id,
                agent_id=f"agent-{suffix}",
            ),
            {
                "error_code": "AGENT_HANDSHAKE_FAILED",
                "error_category": "dependency",
                "error_stage": "agent_negotiation",
                "severity": "error",
                "retryable": True,
                "action": "retry",
            },
        ),
        (
            _raw_error(
                module="cli",
                raw_error_type="timeout",
                raw_message="process exceeded 30 seconds",
                trace_id=trace_id,
                task_id=task_id,
                stage="cli_execution",
            ),
            {
                "error_code": "CLI_TIMEOUT",
                "error_category": "timeout",
                "error_stage": "cli_execution",
                "severity": "warning",
                "retryable": True,
                "action": "retry",
            },
        ),
        (
            _raw_error(
                module="mcp",
                raw_error_type="bad_json",
                raw_message="server returned invalid json",
                trace_id=trace_id,
                task_id=task_id,
                server_id=f"mcp-{suffix}",
            ),
            {
                "error_code": "MCP_BAD_JSON",
                "error_category": "protocol",
                "error_stage": "mcp_call",
                "severity": "error",
                "retryable": False,
                "action": "manual_review",
            },
        ),
        (
            _raw_error(
                module="safety",
                raw_error_type="permission_denied",
                raw_message="operator permission denied for external side effect",
                trace_id=trace_id,
                task_id=task_id,
            ),
            {
                "error_code": "SAFETY_PERMISSION_DENIED",
                "error_category": "auth",
                "error_stage": "safety_review",
                "severity": "critical",
                "retryable": False,
                "action": "escalate",
            },
        ),
    ]

    with live_http_server(acceptance_app) as base_url:
        catalog = requests.get(f"{base_url}/api/web/unified-errors/catalog", timeout=10)
        assert catalog.status_code == 200
        catalog_payload = catalog.json()
        assert "error_code" in catalog_payload["required_fields"]
        assert "trace_id" in catalog_payload["required_fields"]
        assert {"PLUGIN_SCHEMA_INVALID", "CLI_TIMEOUT", "MCP_BAD_JSON", "SAFETY_PERMISSION_DENIED"} <= set(
            catalog_payload["mapped_error_codes"]
        )

        created_reports = []
        for raw, expected in samples:
            response = requests.post(f"{base_url}/api/web/unified-errors", json=raw, timeout=10)
            assert response.status_code == 200
            report = response.json()
            created_reports.append(report)
            error = report["unified_error"]
            envelope = report["api_envelope"]

            assert error["error_code"] == expected["error_code"]
            assert error["error_category"] == expected["error_category"]
            assert error["error_stage"] == expected["error_stage"]
            assert error["severity"] == expected["severity"]
            assert error["retryable"] is expected["retryable"]
            assert error["trace_id"] == trace_id
            assert error["related_refs"]["task_id"] == task_id
            assert error["operator_message"].endswith(raw["raw_message"])
            assert raw["raw_message"] not in error["user_visible_message"]

            assert envelope["trace_id"] == trace_id
            assert envelope["error"]["error_code"] == expected["error_code"]
            assert envelope["error"]["error_stage"] == expected["error_stage"]
            assert envelope["error"]["retryable"] is expected["retryable"]
            assert envelope["error"]["message"] == error["user_visible_message"]
            assert raw["raw_message"] not in envelope["error"]["message"]
            assert report["disposition"]["action"] == expected["action"]
            assert report["audit_payload"]["operator_message"] == error["operator_message"]
            assert report["audit_payload"]["recovery_hint"] == error["recovery_hint"]

        first_id = created_reports[0]["unified_error"]["error_id"]
        fetched = requests.get(f"{base_url}/api/web/unified-errors/{first_id}", timeout=10)
        assert fetched.status_code == 200
        assert fetched.json() == created_reports[0]

        protocol_list = requests.get(
            f"{base_url}/api/web/unified-errors",
            params={"trace_id": trace_id, "category": "protocol"},
            timeout=10,
        )
        assert protocol_list.status_code == 200
        assert {item["unified_error"]["error_code"] for item in protocol_list.json()} == {
            "PLUGIN_SCHEMA_INVALID",
            "MCP_BAD_JSON",
        }

        retryable_list = requests.get(
            f"{base_url}/api/web/unified-errors",
            params={"trace_id": trace_id, "retryable": "true", "limit": 10, "offset": 0},
            timeout=10,
        )
        assert retryable_list.status_code == 200
        assert {item["unified_error"]["error_code"] for item in retryable_list.json()} == {
            "AGENT_HANDSHAKE_FAILED",
            "CLI_TIMEOUT",
        }

        escalate_list = requests.get(
            f"{base_url}/api/web/unified-errors",
            params={"trace_id": trace_id, "action": "escalate"},
            timeout=10,
        )
        assert escalate_list.status_code == 200
        assert [item["unified_error"]["error_code"] for item in escalate_list.json()] == [
            "SAFETY_PERMISSION_DENIED"
        ]

        paged_list = requests.get(
            f"{base_url}/api/web/unified-errors",
            params={"trace_id": trace_id, "limit": 2, "offset": 1},
            timeout=10,
        )
        assert paged_list.status_code == 200
        paged_items = paged_list.json()
        assert len(paged_items) == 2
        assert all(item["unified_error"]["trace_id"] == trace_id for item in paged_items)

        stats = requests.get(
            f"{base_url}/api/web/unified-errors/statistics",
            params={"trace_id": trace_id},
            timeout=10,
        )
        assert stats.status_code == 200
        stats_payload = stats.json()
        assert stats_payload["total_error_count"] == len(samples)
        assert stats_payload["retryable_count"] == 2
        assert stats_payload["critical_count"] == 1
        assert stats_payload["by_category"] == {
            "auth": 1,
            "dependency": 1,
            "protocol": 2,
            "state": 1,
            "timeout": 1,
        }
        assert stats_payload["by_stage"] == {
            "agent_negotiation": 1,
            "cli_execution": 1,
            "dispatch": 1,
            "mcp_call": 1,
            "plugin_call": 1,
            "safety_review": 1,
        }
        assert stats_payload["by_action"] == {
            "block": 1,
            "escalate": 1,
            "manual_review": 2,
            "retry": 2,
        }

        unknown_trace_id = f"trace-feature68-unknown-{suffix}"
        unknown_response = requests.post(
            f"{base_url}/api/web/unified-errors",
            json=_raw_error(
                module="web",
                raw_error_type="unexpected_runtime_fault",
                raw_message="unexpected runtime fault with safe user message",
                trace_id=unknown_trace_id,
                task_id=f"task-feature68-unknown-{suffix}",
                stage="web_api",
            ),
            timeout=10,
        )
        assert unknown_response.status_code == 200
        unknown_error = unknown_response.json()["unified_error"]
        assert unknown_error["error_code"] == "WEB_UNKNOWN"
        assert unknown_error["error_category"] == "unknown"
        assert unknown_error["error_stage"] == "web_api"
        assert "unexpected runtime fault" not in unknown_error["user_visible_message"]

        missing = requests.get(f"{base_url}/api/web/unified-errors/not-found-{suffix}", timeout=10)
        assert missing.status_code == 404

        invalid = requests.post(
            f"{base_url}/api/web/unified-errors",
            json={
                "module": "plugin",
                "raw_error_type": "schema_error",
                "raw_message": "invalid extra field should fail",
                "trace_id": trace_id,
                "unexpected": "forbidden",
            },
            timeout=10,
        )
        assert invalid.status_code == 422

    audit_payloads = [
        entry["payload"]
        for entry in acceptance_app.state.transcript_store.entries[before_audit_count:]
    ]
    unified_payloads = [
        payload for payload in audit_payloads if payload.get("event") == "unified_error_mapped"
    ]
    sample_trace_payloads = [payload for payload in unified_payloads if payload["trace_id"] == trace_id]
    unknown_trace_payloads = [payload for payload in unified_payloads if payload["trace_id"] == unknown_trace_id]
    assert len(sample_trace_payloads) == len(samples)
    assert len(unknown_trace_payloads) == 1
    assert unknown_trace_payloads[0]["error_code"] == "WEB_UNKNOWN"
    assert {payload["error_code"] for payload in sample_trace_payloads} == {
        "PLUGIN_SCHEMA_INVALID",
        "TASK_STATE_TRANSITION_INVALID",
        "AGENT_HANDSHAKE_FAILED",
        "CLI_TIMEOUT",
        "MCP_BAD_JSON",
        "SAFETY_PERMISSION_DENIED",
    }
    assert all(payload["operator_message"] for payload in sample_trace_payloads)
    assert all(payload["recovery_hint"] for payload in sample_trace_payloads)
