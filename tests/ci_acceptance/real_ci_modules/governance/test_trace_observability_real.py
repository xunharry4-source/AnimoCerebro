from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


STAGES = (
    "perception",
    "nine_questions",
    "dispatch",
    "tool_call",
    "safety_review",
    "execution",
    "receipt",
    "reflection",
    "memory_writeback",
)


def _span(
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    stage: str,
    actor: str,
    module: str,
    operation: str,
    status: str,
    occurred_at: str,
    duration_ms: float,
    request_id: str,
    task_id: str,
    agent_id: str | None = None,
    decision_id: str | None = None,
    evidence_refs: list[str] | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    retry_count: int = 0,
    error_code: str | None = None,
) -> dict:
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "stage": stage,
        "actor": actor,
        "module": module,
        "operation": operation,
        "input_summary": input_summary or f"{stage} accepted structured input for {task_id}",
        "output_summary": output_summary or f"{stage} produced auditable output for {task_id}",
        "status": status,
        "duration_ms": duration_ms,
        "occurred_at": occurred_at,
        "error_code": error_code,
        "error_stage": stage if error_code else None,
        "resource_usage_snapshot": {
            "cpu_percent": 12.5,
            "memory_mb": 256.0,
            "budget_units": 1.0,
        },
        "evidence_refs": evidence_refs or [f"audit:{span_id}", f"replay:{trace_id}:{span_id}"],
        "request_id": request_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "decision_id": decision_id,
        "retry_count": retry_count,
    }


def _healthy_payload(suffix: str) -> dict:
    trace_id = f"trace-feature66-{suffix}"
    request_id = f"request-feature66-{suffix}"
    task_id = f"task-feature66-{suffix}"
    decision_id = f"decision-feature66-{suffix}"
    base = datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc)
    actors = {
        "perception": "zentex",
        "nine_questions": "zentex",
        "dispatch": "zentex",
        "tool_call": "plugin",
        "safety_review": "cloud_audit",
        "execution": "cli",
        "receipt": "mcp_server",
        "reflection": "agent",
        "memory_writeback": "zentex",
    }
    modules = {
        "perception": "sensory_chain",
        "nine_questions": "nine_questions",
        "dispatch": "task_dispatch",
        "tool_call": "plugin_bus",
        "safety_review": "cloud_audit",
        "execution": "cli",
        "receipt": "mcp",
        "reflection": "agent_reflection",
        "memory_writeback": "memory",
    }
    spans = []
    previous: str | None = None
    for index, stage in enumerate(STAGES):
        span_id = f"span-{index:02d}-{stage}-{suffix}"
        spans.append(
            _span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=previous,
                stage=stage,
                actor=actors[stage],
                module=modules[stage],
                operation=f"{stage}.run",
                status="success",
                occurred_at=(base + timedelta(seconds=index)).isoformat(),
                duration_ms=25 + index,
                request_id=request_id,
                task_id=task_id,
                agent_id=f"agent-feature66-{suffix}" if actors[stage] == "agent" else None,
                decision_id=decision_id if actors[stage] == "cloud_audit" else None,
            )
        )
        previous = span_id
    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "source": "feature66-real-test",
        "spans": spans,
    }


def test_feature66_trace_observability_api_persists_queries_and_detects_real_gaps(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    healthy = _healthy_payload(suffix)
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        requirements = requests.get(f"{base_url}/api/web/trace-observability/requirements", timeout=10)
        assert requirements.status_code == 200
        matrix = requirements.json()
        assert matrix["required_stages"] == list(STAGES)
        assert {"plugin", "agent", "cli", "mcp_server", "cloud_audit"} <= set(matrix["cross_protocol_actors"])
        assert "parent_span_missing" in matrix["anomaly_checks"]

        created = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=healthy,
            timeout=10,
        )
        assert created.status_code == 200
        report = created.json()
        assert report["observability_status"] == "healthy"
        assert report["trace_id"] == healthy["trace_id"]
        assert report["span_count"] == len(STAGES)
        assert report["anomalies"] == []
        assert report["stage_coverage"] == {stage: True for stage in STAGES}
        assert report["metrics"]["trace_integrity_metrics"] == {
            "required_stage_count": len(STAGES),
            "covered_stage_count": len(STAGES),
            "critical_anomaly_count": 0,
            "integrity_score": 1.0,
        }
        assert report["metrics"]["retry_metrics"]["total_retry_count"] == 0
        assert report["metrics"]["timeout_metrics"]["timeout_count"] == 0
        assert report["metrics"]["degraded_metrics"]["degraded_count"] == 0
        assert report["metrics"]["replay_coverage_metrics"]["replay_ready_span_count"] == len(STAGES)
        assert report["call_tree"][0]["span_id"] == healthy["spans"][0]["span_id"]
        assert report["call_tree"][0]["children"][0]["span_id"] == healthy["spans"][1]["span_id"]
        assert report["searchable_refs"]["request_ids"] == [healthy["request_id"]]
        assert report["searchable_refs"]["task_ids"] == [healthy["spans"][0]["task_id"]]
        assert "stage:memory_writeback" in report["passed_requirements"]

        fetched = requests.get(
            f"{base_url}/api/web/trace-observability/traces/{report['observation_id']}",
            timeout=10,
        )
        assert fetched.status_code == 200
        assert fetched.json() == report

        by_trace = requests.get(
            f"{base_url}/api/web/trace-observability/traces",
            params={"trace_id": healthy["trace_id"]},
            timeout=10,
        )
        assert by_trace.status_code == 200
        assert [item["observation_id"] for item in by_trace.json()] == [report["observation_id"]]

        by_request = requests.get(
            f"{base_url}/api/web/trace-observability/traces",
            params={"request_id": healthy["request_id"]},
            timeout=10,
        )
        assert by_request.status_code == 200
        assert by_request.json()[0]["trace_id"] == healthy["trace_id"]

        broken = _healthy_payload(f"broken-{suffix}")
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
        broken["spans"].append(dict(broken["spans"][0]))

        failed = requests.post(
            f"{base_url}/api/web/trace-observability/traces",
            json=broken,
            timeout=10,
        )
        assert failed.status_code == 200
        failed_report = failed.json()
        assert failed_report["observability_status"] == "broken"
        codes = {item["code"] for item in failed_report["anomalies"]}
        assert {
            "required_stage_missing",
            "parent_span_missing",
            "summary_insufficient",
            "audit_ref_missing",
            "failed_or_blocked_span",
            "slow_call",
            "retry_storm",
            "duplicate_span_id",
        } <= codes
        assert failed_report["stage_coverage"]["safety_review"] is False
        assert failed_report["stage_coverage"]["reflection"] is False
        assert failed_report["metrics"]["timeout_metrics"]["timeout_count"] == 1
        assert failed_report["metrics"]["retry_metrics"]["total_retry_count"] == 3
        assert failed_report["metrics"]["trace_integrity_metrics"]["integrity_score"] == 0.0

    audit_entries = acceptance_app.state.transcript_store.entries[before_audit_count:]
    observed_payloads = [entry["payload"] for entry in audit_entries]
    assert any(
        payload["event"] == "trace_observability_evaluated"
        and payload["trace_id"] == healthy["trace_id"]
        and payload["observability_status"] == "healthy"
        for payload in observed_payloads
    )
    assert any(
        payload["event"] == "trace_observability_evaluated"
        and payload["trace_id"] == broken["trace_id"]
        and payload["observability_status"] == "broken"
        and payload["critical_anomaly_count"] >= 1
        for payload in observed_payloads
    )
