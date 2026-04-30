from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.audit.service import AuditService
from zentex.common.flow_audit import FlowAudit
from zentex.web_console.dependencies import get_kernel_service_facade
from zentex.web_console.routers import audit as audit_router


def _audit_api_app(audit_service: AuditService) -> FastAPI:
    app = FastAPI()
    app.state.audit_service = audit_service
    app.dependency_overrides[get_kernel_service_facade] = lambda: object()
    app.include_router(audit_router.router, prefix="/api/web")
    return app


def test_audit_center_start_points_are_real_root_flow_rows_and_grow_per_run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_service = AuditService(db_path=f"{tmpdir}/audit_trace.sqlite3")
        first_nine = FlowAudit.new("nine_questions", source_module="test.nine_questions.first", question_driver_refs=["q1"])
        second_nine = FlowAudit.new("nine_questions", source_module="test.nine_questions.second", question_driver_refs=["q2"])
        root_reflection = FlowAudit.new("reflection", source_module="test.reflection.root", question_driver_refs=["q3"])
        root_learning = FlowAudit.new("learning", source_module="test.learning.root", question_driver_refs=["q4"])
        child_reflection = first_nine.spawn("reflection", source_module="test.reflection.child")
        child_learning = first_nine.spawn("learning", source_module="test.learning.child")
        flows = [first_nine, second_nine, root_reflection, root_learning, child_reflection, child_learning]
        root_flows = [first_nine, second_nine, root_reflection, root_learning]
        base_time = datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)
        for index, flow in enumerate(flows):
            flow.started_at = (base_time + timedelta(minutes=index)).isoformat()

        with live_http_server(_audit_api_app(audit_service)) as base_url:
            empty_response = requests.get(f"{base_url}/api/web/audit/trace-starts?page=1&page_size=2", timeout=10)
            assert empty_response.status_code == 200, empty_response.text
            assert empty_response.json() == {
                "items": [],
                "page": 1,
                "page_size": 2,
                "total_items": 0,
                "total_pages": 1,
            }

            for flow in flows:
                audit_service.record_flow_start(flow)
                audit_service.record_flow_end(flow, status="completed")

            all_response = requests.get(f"{base_url}/api/web/audit/flow-health?limit=20", timeout=10)
            assert all_response.status_code == 200, all_response.text
            assert len(all_response.json()) == len(flows)

            list_response = requests.get(f"{base_url}/api/web/audit/trace-starts?page=1&page_size=2", timeout=10)
            assert list_response.status_code == 200, list_response.text
            first_page = list_response.json()
            rows = first_page["items"]

            second_page_response = requests.get(f"{base_url}/api/web/audit/trace-starts?page=2&page_size=2", timeout=10)
            assert second_page_response.status_code == 200, second_page_response.text
            second_page = second_page_response.json()

        assert first_page["page"] == 1
        assert first_page["page_size"] == 2
        assert first_page["total_items"] == len(root_flows)
        assert first_page["total_pages"] == 2
        assert len(first_page["items"]) == 2
        assert second_page["page"] == 2
        assert second_page["page_size"] == 2
        assert second_page["total_items"] == len(root_flows)
        assert second_page["total_pages"] == 2
        assert len(second_page["items"]) == 2
        assert {row["audit_id"] for row in first_page["items"]}.isdisjoint(
            {row["audit_id"] for row in second_page["items"]}
        )
        assert [row["audit_id"] for row in first_page["items"]] == [
            root_learning.audit_id,
            root_reflection.audit_id,
        ]
        assert [row["audit_id"] for row in second_page["items"]] == [
            second_nine.audit_id,
            first_nine.audit_id,
        ]

        all_rows = first_page["items"] + second_page["items"]
        by_id = {row["audit_id"]: row for row in all_rows}
        assert set(by_id) == {flow.audit_id for flow in root_flows}
        assert [row["flow_type"] for row in all_rows].count("nine_questions") == 2
        assert [row["flow_type"] for row in all_rows].count("reflection") == 1
        assert [row["flow_type"] for row in all_rows].count("learning") == 1
        assert child_reflection.audit_id not in by_id
        assert child_learning.audit_id not in by_id
        assert child_reflection.parent_audit_id == first_nine.audit_id
        assert child_learning.parent_audit_id == first_nine.audit_id
        for flow in root_flows:
            row = by_id[flow.audit_id]
            assert row["status"] == "completed"
            assert row["source_module"] == flow.source_module
            assert row["parent_audit_id"] in {None, ""}
            assert row["question_driver_refs"] == flow.question_driver_refs


def test_audit_graph_returns_empty_when_no_real_events_or_traces_exist() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        audit_service = AuditService(db_path=f"{tmpdir}/audit_trace.sqlite3")
        with live_http_server(_audit_api_app(audit_service)) as base_url:
            response = requests.get(f"{base_url}/api/web/audit/trace-center/nine_questions", timeout=10)
            assert response.status_code == 200, response.text
            payload = response.json()

        assert payload["mode"] == "nine_questions"
        assert payload["database_backed"] is True
        assert payload["summary"]["audit_event_count"] == 0
        assert payload["summary"]["model_trace_count"] == 0
        assert payload["lanes"] == []
        assert payload["edges"] == []
