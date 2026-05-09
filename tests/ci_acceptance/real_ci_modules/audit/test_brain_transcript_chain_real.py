from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _span(
    *,
    trace_id: str,
    span_id: str,
    event_type: str,
    causal_parent_id: str,
    output_summary: str,
    origin_trace_id: str | None = None,
    risk_level: str = "low",
    blocked: bool = False,
) -> dict[str, object]:
    order = {
        "think_loop_started": 0,
        "phase_completed": 1,
        "memory_recalled": 2,
        "safety_gate_blocked": 3,
        "delegation_sent": 1,
        "delegation_received": 0,
        "delegation_receipt": 1,
        "action_receipt": 4,
    }.get(event_type, 8)
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "event_type": event_type,
        "causal_parent_id": causal_parent_id,
        "origin_trace_id": origin_trace_id,
        "session_id": "feature48-session",
        "turn_id": "feature48-turn",
        "brain_scope": "local",
        "decision_type": "risk_decision",
        "risk_level": risk_level,
        "started_at": f"2026-04-29T12:00:0{order}+00:00",
        "finished_at": f"2026-04-29T12:00:1{order}+00:00",
        "duration_ms": 10 + len(span_id),
        "input_summary": event_type,
        "output_summary": output_summary,
        "blocked": blocked,
        "payload": {"evidence": f"payload:{span_id}", "event_type": event_type},
    }


def test_brain_transcript_chain_appends_queries_replays_and_audits_real_requests(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex
    trace_id = f"feature48-trace-{suffix}"
    root_id = f"feature48-root-{suffix}"
    phase_id = f"feature48-phase-{suffix}"
    memory_id = f"feature48-memory-{suffix}"
    blocked_id = f"feature48-blocked-{suffix}"
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    spans = [
        _span(
            trace_id=trace_id,
            span_id=root_id,
            event_type="think_loop_started",
            causal_parent_id="ROOT",
            output_summary="ThinkLoop root started",
        ),
        _span(
            trace_id=trace_id,
            span_id=phase_id,
            event_type="phase_completed",
            causal_parent_id=root_id,
            output_summary="Phase 1 completed",
        ),
        _span(
            trace_id=trace_id,
            span_id=memory_id,
            event_type="memory_recalled",
            causal_parent_id=phase_id,
            output_summary="Memory evidence recalled",
            risk_level="medium",
        ),
        _span(
            trace_id=trace_id,
            span_id=blocked_id,
            event_type="safety_gate_blocked",
            causal_parent_id=memory_id,
            output_summary="Unsafe execution blocked",
            risk_level="high",
            blocked=True,
        ),
    ]

    with live_http_server(acceptance_app) as base_url:
        for span in spans:
            response = requests.post(f"{base_url}/api/web/brain-transcript-chain/spans", json=span, timeout=10)
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "created"
            assert payload["idempotent"] is False
            assert payload["span"]["span_id"] == span["span_id"]

        duplicate = requests.post(f"{base_url}/api/web/brain-transcript-chain/spans", json=spans[-1], timeout=10)
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "existing"
        assert duplicate.json()["idempotent"] is True

        conflicting = dict(spans[-1])
        conflicting["output_summary"] = "conflicting rewrite attempt"
        conflict = requests.post(f"{base_url}/api/web/brain-transcript-chain/spans", json=conflicting, timeout=10)
        assert conflict.status_code == 409
        assert "already exists with different content" in conflict.json()["detail"]

        orphan = _span(
            trace_id=trace_id,
            span_id=f"feature48-orphan-{suffix}",
            event_type="action_receipt",
            causal_parent_id=f"missing-parent-{suffix}",
            output_summary="orphan should be rejected",
        )
        orphan_response = requests.post(f"{base_url}/api/web/brain-transcript-chain/spans", json=orphan, timeout=10)
        assert orphan_response.status_code == 409
        assert "causal_parent_id" in orphan_response.json()["detail"]

        trace = requests.get(f"{base_url}/api/web/brain-transcript-chain/traces/{trace_id}", timeout=10)
        assert trace.status_code == 200
        trace_payload = trace.json()
        assert trace_payload["trace_id"] == trace_id
        assert trace_payload["span_count"] == 4
        assert trace_payload["root_span_ids"] == [root_id]
        assert len(trace_payload["edges"]) == 3
        assert trace_payload["critical_path_span_ids"] == [root_id, phase_id, memory_id, blocked_id]
        assert blocked_id in trace_payload["blocked_span_ids"]
        assert blocked_id in trace_payload["audit_span_ids"]
        assert [item["span_id"] for item in trace_payload["timeline"]] == [root_id, phase_id, memory_id, blocked_id]

        replay = requests.get(f"{base_url}/api/web/brain-transcript-chain/replay/{trace_id}", timeout=10)
        assert replay.status_code == 200
        replay_payload = replay.json()
        assert replay_payload["mode"] == "timeline"
        assert replay_payload["executable_actions_enabled"] is False
        assert [item["span_id"] for item in replay_payload["sequence"]] == [root_id, phase_id, memory_id, blocked_id]

        descendants = requests.get(
            f"{base_url}/api/web/brain-transcript-chain/spans/{root_id}/descendants",
            timeout=10,
        )
        assert descendants.status_code == 200
        descendants_payload = descendants.json()
        assert descendants_payload["descendant_count"] == 3
        assert [item["span_id"] for item in descendants_payload["descendants"]] == [phase_id, memory_id, blocked_id]

        search = requests.get(
            f"{base_url}/api/web/brain-transcript-chain/search",
            params={"trace_id": trace_id, "risk_level": "high"},
            timeout=10,
        )
        assert search.status_code == 200
        search_payload = search.json()
        assert search_payload["span_count"] == 1
        assert search_payload["trace_count"] == 1
        assert search_payload["items"][0]["trace_id"] == trace_id
        assert search_payload["items"][0]["risk_levels"] == ["high"]

    appended_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    assert len(appended_audits) == 4
    audit_payloads = [entry["payload"] for entry in appended_audits]
    assert {item["span_id"] for item in audit_payloads} == {root_id, phase_id, memory_id, blocked_id}
    assert all(item["event_type"] == "brain_transcript_chain_span_appended" for item in audit_payloads)


def test_brain_transcript_chain_merges_cross_brain_traces_and_diffs_real_requests(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex
    origin_trace_id = f"feature48-origin-{suffix}"
    local_trace_id = f"feature48-local-{suffix}"
    compare_trace_id = f"feature48-compare-{suffix}"
    origin_root_id = f"feature48-origin-root-{suffix}"
    delegation_sent_id = f"feature48-delegation-sent-{suffix}"
    local_root_id = f"feature48-local-root-{suffix}"
    receipt_id = f"feature48-receipt-{suffix}"
    compare_root_id = f"feature48-compare-root-{suffix}"

    with live_http_server(acceptance_app) as base_url:
        for span in [
            _span(
                trace_id=origin_trace_id,
                span_id=origin_root_id,
                event_type="think_loop_started",
                causal_parent_id="ROOT",
                output_summary="Origin root started",
            ),
            _span(
                trace_id=origin_trace_id,
                span_id=delegation_sent_id,
                event_type="delegation_sent",
                causal_parent_id=origin_root_id,
                output_summary="Delegation sent to peer brain",
                risk_level="medium",
            ),
            _span(
                trace_id=local_trace_id,
                span_id=local_root_id,
                event_type="delegation_received",
                causal_parent_id="ROOT",
                origin_trace_id=origin_trace_id,
                output_summary="Delegation accepted from origin",
                risk_level="medium",
            ),
            _span(
                trace_id=local_trace_id,
                span_id=receipt_id,
                event_type="delegation_receipt",
                causal_parent_id=local_root_id,
                origin_trace_id=origin_trace_id,
                output_summary="Delegation completed with receipt",
                risk_level="medium",
            ),
            _span(
                trace_id=compare_trace_id,
                span_id=compare_root_id,
                event_type="think_loop_started",
                causal_parent_id="ROOT",
                output_summary="Different root result after upgrade",
            ),
        ]:
            response = requests.post(f"{base_url}/api/web/brain-transcript-chain/spans", json=span, timeout=10)
            assert response.status_code == 200, response.text

        merge = requests.post(
            f"{base_url}/api/web/brain-transcript-chain/cross-brain-merge",
            json={"origin_trace_id": origin_trace_id, "local_trace_id": local_trace_id},
            timeout=10,
        )
        assert merge.status_code == 200, merge.text
        merge_payload = merge.json()
        assert merge_payload["merged_trace_ids"] == [origin_trace_id, local_trace_id]
        assert merge_payload["cross_edges"] == [
            {
                "from_span_id": delegation_sent_id,
                "to_span_id": local_root_id,
                "edge_type": "cross_brain_delegation",
            }
        ]
        assert merge_payload["local"]["nodes"][0]["origin_trace_id"] == origin_trace_id

        diff = requests.post(
            f"{base_url}/api/web/brain-transcript-chain/diff",
            json={"left_trace_id": origin_trace_id, "right_trace_id": compare_trace_id},
            timeout=10,
        )
        assert diff.status_code == 200
        diff_payload = diff.json()
        assert delegation_sent_id in diff_payload["missing_span_ids"]
        assert diff_payload["changed_spans"][0]["left_span_id"] == origin_root_id
        assert diff_payload["changed_spans"][0]["right_span_id"] == compare_root_id
        assert diff_payload["changed_spans"][0]["left_output_summary"] == "Origin root started"
        assert diff_payload["changed_spans"][0]["right_output_summary"] == "Different root result after upgrade"

        invalid_received = _span(
            trace_id=f"feature48-invalid-local-{suffix}",
            span_id=f"feature48-invalid-received-{suffix}",
            event_type="delegation_received",
            causal_parent_id="ROOT",
            output_summary="invalid missing origin",
        )
        invalid_response = requests.post(
            f"{base_url}/api/web/brain-transcript-chain/spans",
            json=invalid_received,
            timeout=10,
        )
        assert invalid_response.status_code == 409
        assert "origin_trace_id" in invalid_response.json()["detail"]
