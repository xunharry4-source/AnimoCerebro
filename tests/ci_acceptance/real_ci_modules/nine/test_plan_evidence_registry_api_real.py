from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
from pathlib import Path
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


@contextmanager
def _live_http_server(app: FastAPI) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="critical",
        lifespan="off",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("uvicorn live request server failed to start")
    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _write_evidence_file(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_plan_evidence_manifest_api_registers_generated_manifest_without_completion_credit(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    checksum = f"generated-verification-checksum-{suffix}"
    manifest = {
        "source_kind": "generated_verification",
        "source_uri": f"task-service://generated-verification/{suffix}",
        "environment": "local_acceptance_db",
        "checksum": checksum,
        "captured_at": "2026-04-29T00:00:00+08:00",
        "owner": "ci",
        "evidence_count": 5,
        "evidence_fields": ["task_id", "task_outcome", "metadata_readback"],
    }

    with _live_http_server(acceptance_app) as base_url:
        register_response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/evidence-manifests",
            json=manifest,
            timeout=10,
        )
        query_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/evidence-manifests",
            timeout=10,
        )

    assert register_response.status_code == 200
    payload = register_response.json()
    assert payload["evidence_manifest_status"] == "registered"
    assert payload["counts_toward_completion"] is False
    assert payload["manifest"]["source_kind"] == "generated_verification"
    assert payload["manifest"]["checksum"] == checksum
    assert payload["manifest"]["evidence_count"] == 5

    rows = acceptance_app.state.learning_service.query_overall_records(
        limit=20,
        trace_id=payload["learning_trace_id"],
    )
    matches = [
        row
        for row in rows
        if row.detail.get("learning_kind") == "plan_evidence_manifest"
        and row.detail.get("checksum") == checksum
    ]
    assert len(matches) == 1
    assert matches[0].detail["manifest"]["source_uri"] == manifest["source_uri"]
    assert matches[0].detail["counts_toward_completion"] is False

    assert query_response.status_code == 200
    summary = query_response.json()
    missing_completion_kinds = set(summary["missing_completion_evidence_kinds"])
    completion_kinds = set(summary["completion_evidence_kinds"])
    assert summary["evidence_summary_status"] == ("complete" if not missing_completion_kinds else "incomplete")
    assert summary["generated_manifest_count"] >= 1
    assert "generated_verification" not in completion_kinds
    assert missing_completion_kinds.isdisjoint(completion_kinds)
    assert any(item["checksum"] == checksum for item in summary["manifests"])


@pytest.mark.asyncio
async def test_plan_evidence_manifest_api_rejects_generated_uri_for_completion_evidence(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    checksum = f"fake-production-checksum-{suffix}"
    manifest = {
        "source_kind": "real_production_history",
        "source_uri": f"generated://fake-production-history/{suffix}",
        "environment": "local_acceptance_db",
        "checksum": checksum,
        "captured_at": "2026-04-29T00:00:00+08:00",
        "owner": "ci",
        "evidence_count": 100,
        "evidence_fields": ["task_id", "manual_review", "observation_day"],
    }

    with _live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/evidence-manifests",
            json=manifest,
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "plan_evidence_manifest_failed"
    reasons = {failure["reason"] for failure in detail["failures"]}
    assert "completion_evidence_source_uri_not_real_external" in reasons
    assert "generated_or_test_evidence_cannot_satisfy_completion_gate" in reasons
    rows = acceptance_app.state.learning_service.query_overall_records(limit=200)
    assert all(row.detail.get("checksum") != checksum for row in rows)


@pytest.mark.asyncio
async def test_plan_evidence_manifest_api_rejects_wrong_kind_prefix_and_incomplete_payload(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    checksum = f"wrong-kind-prefix-checksum-{suffix}"
    manifest = {
        "source_kind": "real_production_history",
        "source_uri": f"llm-provider://reflection-quality/{suffix}",
        "environment": "production",
        "checksum": checksum,
        "captured_at": "2026-04-29T00:00:00+08:00",
        "owner": "ci",
        "evidence_count": 1,
        "evidence_fields": ["provider_key", "model", "quality_score"],
    }

    with _live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/evidence-manifests",
            json=manifest,
            timeout=10,
        )
        summary_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/evidence-manifests",
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "plan_evidence_manifest_failed"
    reasons = {failure["reason"] for failure in detail["failures"]}
    assert "completion_evidence_source_uri_kind_mismatch" in reasons
    assert "completion_evidence_count_below_required" in reasons
    assert "completion_evidence_required_fields_missing" in reasons
    missing_field_failures = [
        failure for failure in detail["failures"] if failure["reason"] == "completion_evidence_required_fields_missing"
    ]
    assert missing_field_failures
    assert set(missing_field_failures[0]["missing_fields"]) == {
        "manual_review",
        "q8_trace_id",
        "task_id",
        "task_outcome",
    }

    rows = acceptance_app.state.learning_service.query_overall_records(limit=200)
    assert all(row.detail.get("checksum") != checksum for row in rows)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["completion_evidence_requirements"]["real_production_history"]["minimum_evidence_count"] == 100
    assert "task_outcome" in summary["completion_evidence_requirements"]["real_production_history"]["required_fields"]
    assert all(item.get("checksum") != checksum for item in summary["manifests"])


@pytest.mark.asyncio
async def test_plan_remaining_work_api_reports_all_real_blockers_and_fails_when_required(
    acceptance_app: FastAPI,
) -> None:
    with _live_http_server(acceptance_app) as base_url:
        query_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/remaining-work",
            timeout=10,
        )
        strict_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/remaining-work",
            params={"require_complete": "true"},
            timeout=10,
        )

    assert query_response.status_code == 200
    report = query_response.json()
    remaining_ids = {item["work_id"] for item in report["remaining_items"]}
    assert report["remaining_work_status"] == ("complete" if not remaining_ids else "incomplete")
    assert report["full_plan_completion_claimed"] is (not remaining_ids)
    assert report["remaining_count"] == len(remaining_ids)
    assert report["required_evidence_kind_count"] == 6
    all_work_ids = {
        "real_production_history",
        "natural_week_observation",
        "online_q8_prompt_baseline",
        "prompt_audit_report_set",
        "phase_d_shadow_canary_rollback",
        "llm_reflection_quality",
        "browser_e2e_validation",
        "frontend_build_validation",
        "full_pytest_regression",
    }
    assert remaining_ids.issubset(all_work_ids)
    non_manifest_status = {item["work_id"]: item["status"] for item in report["non_manifest_items"]}
    assert set(non_manifest_status) == {
        "browser_e2e_validation",
        "frontend_build_validation",
        "full_pytest_regression",
    }
    production_item = next(item for item in report["evidence_items"] if item["work_id"] == "real_production_history")
    assert production_item["minimum_evidence_count"] == 100
    assert set(production_item["required_fields"]) == {
        "manual_review",
        "q8_trace_id",
        "task_id",
        "task_outcome",
    }
    if production_item["status"] == "remaining":
        assert production_item["reason"] == "completion_evidence_manifest_missing"
    else:
        assert production_item["registered_completion_manifest_count"] >= 1
        assert production_item["reason"] is None
    if non_manifest_status["browser_e2e_validation"] == "remaining":
        browser_item = next(item for item in report["non_manifest_items"] if item["work_id"] == "browser_e2e_validation")
        assert browser_item["reason"] == "real_execution_evidence_missing"
        assert "真实浏览器" in browser_item["required_evidence"]

    if remaining_ids:
        assert strict_response.status_code == 409
        detail = strict_response.json()["detail"]
        assert detail["error"] == "plan_remaining_work_not_complete"
        assert detail["failures"][0]["reason"] == "plan_remaining_work_not_complete"
        assert detail["failures"][0]["remaining_count"] == report["remaining_count"]
        assert set(detail["failures"][0]["remaining_work_ids"]) == remaining_ids
        assert detail["report"]["full_plan_completion_claimed"] is False
    else:
        assert strict_response.status_code == 200
        assert strict_response.json()["full_plan_completion_claimed"] is True


@pytest.mark.asyncio
async def test_plan_execution_evidence_api_registers_real_execution_records_and_updates_remaining_work(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    suffix = unique_suffix()
    browser_log = tmp_path / f"browser-e2e-{suffix}.log"
    browser_trace = tmp_path / f"browser-trace-{suffix}.zip"
    build_log = tmp_path / f"frontend-build-{suffix}.log"
    build_artifact = tmp_path / f"frontend-build-{suffix}.txt"
    pytest_log = tmp_path / f"pytest-regression-{suffix}.log"
    browser_digest = _write_evidence_file(
        browser_log,
        "Playwright real browser assertions passed: phase_b_gate_visible phase_m_gate_visible waiting_evidence_not_marked_complete",
    )
    browser_trace.write_text("trace artifact", encoding="utf-8")
    build_digest = _write_evidence_file(build_log, "npm run build exit_code=0")
    build_artifact.write_text("vite build artifact", encoding="utf-8")
    pytest_digest = _write_evidence_file(pytest_log, "pytest target regression 22 passed")

    evidence_payloads = [
        {
            "evidence_kind": "browser_e2e_validation",
            "environment": "local_real_browser",
            "captured_at": "2026-04-29T00:00:00+08:00",
            "owner": "ci",
            "command": "npx playwright test q8-v1-evidence-gates",
            "exit_code": 0,
            "output_digest": browser_digest,
            "output_log_uri": str(browser_log),
            "url": "http://127.0.0.1:5173/nine-questions/q8",
            "assertions": [
                "phase_b_gate_visible",
                "phase_m_gate_visible",
                "waiting_evidence_not_marked_complete",
            ],
            "screenshot_or_trace_uri": str(browser_trace),
        },
        {
            "evidence_kind": "frontend_build_validation",
            "environment": "local_frontend_build",
            "captured_at": "2026-04-29T00:00:00+08:00",
            "owner": "ci",
            "command": "npm run build",
            "exit_code": 0,
            "output_digest": build_digest,
            "output_log_uri": str(build_log),
            "checked_files": ["src/admin-portal/src/pages/nine-questions/q8/Q8Detail.tsx"],
            "artifact_uri": str(build_artifact),
        },
        {
            "evidence_kind": "full_pytest_regression",
            "environment": "local_pytest_regression",
            "captured_at": "2026-04-29T00:00:00+08:00",
            "owner": "ci",
            "command": "pytest tests/ci_acceptance/real_ci_modules/nine -q",
            "exit_code": 0,
            "output_digest": pytest_digest,
            "output_log_uri": str(pytest_log),
            "test_count": 22,
            "failure_count": 0,
            "duration_seconds": 7.75,
        },
    ]

    with _live_http_server(acceptance_app) as base_url:
        register_responses = [
            requests.post(
                f"{base_url}/api/web/nine-questions/plan/execution-evidence",
                json=payload,
                timeout=10,
            )
            for payload in evidence_payloads
        ]
        summary_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/execution-evidence",
            timeout=10,
        )
        remaining_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/remaining-work",
            timeout=10,
        )

    assert [response.status_code for response in register_responses] == [200, 200, 200]
    for response, payload in zip(register_responses, evidence_payloads):
        body = response.json()
        assert body["execution_evidence_status"] == "registered"
        assert body["evidence"]["evidence_kind"] == payload["evidence_kind"]
        assert body["evidence"]["output_digest"] == payload["output_digest"]
        rows = acceptance_app.state.learning_service.query_overall_records(
            limit=20,
            trace_id=body["learning_trace_id"],
        )
        assert any(
            row.detail.get("learning_kind") == "plan_execution_evidence"
            and row.detail.get("output_digest") == payload["output_digest"]
            for row in rows
        )

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["execution_evidence_summary_status"] == "complete"
    assert set(summary["completed_execution_evidence_kinds"]) == {
        "browser_e2e_validation",
        "frontend_build_validation",
        "full_pytest_regression",
    }

    assert remaining_response.status_code == 200
    remaining = remaining_response.json()
    non_manifest_status = {item["work_id"]: item["status"] for item in remaining["non_manifest_items"]}
    assert non_manifest_status == {
        "browser_e2e_validation": "completed",
        "frontend_build_validation": "completed",
        "full_pytest_regression": "completed",
    }
    remaining_ids = {item["work_id"] for item in remaining["remaining_items"]}
    assert "browser_e2e_validation" not in remaining_ids
    assert "frontend_build_validation" not in remaining_ids
    assert "full_pytest_regression" not in remaining_ids
    assert remaining["remaining_count"] == len(remaining_ids)


@pytest.mark.asyncio
async def test_plan_execution_evidence_api_rejects_failed_or_missing_artifact_without_write(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    suffix = unique_suffix()
    output_log = tmp_path / f"failed-build-{suffix}.log"
    digest = _write_evidence_file(output_log, "npm run build failed")
    missing_artifact = tmp_path / f"missing-artifact-{suffix}.txt"
    payload = {
        "evidence_kind": "frontend_build_validation",
        "environment": "local_frontend_build",
        "captured_at": "2026-04-29T00:00:00+08:00",
        "owner": "ci",
        "command": "npm run build",
        "exit_code": 2,
        "output_digest": digest,
        "output_log_uri": str(output_log),
        "checked_files": ["src/admin-portal/src/pages/nine-questions/q8/Q8Detail.tsx"],
        "artifact_uri": str(missing_artifact),
    }

    with _live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/execution-evidence",
            json=payload,
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "plan_execution_evidence_failed"
    reasons = {failure["reason"] for failure in detail["failures"]}
    assert "execution_exit_code_not_zero" in reasons
    assert "frontend_build_artifact_file_missing" in reasons
    rows = acceptance_app.state.learning_service.query_overall_records(limit=200)
    assert all(row.detail.get("output_digest") != digest for row in rows)
