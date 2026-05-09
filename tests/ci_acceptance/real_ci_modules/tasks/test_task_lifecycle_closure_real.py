from __future__ import annotations

import requests
import pytest
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.tasks.models import TaskStatus


@pytest.mark.asyncio
async def test_task_management_closure_detects_real_state_audit_recovery_and_fault_matrix(real_ci_runtime) -> None:
    suffix = unique_suffix()
    created_ids = []

    stale = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}-stale", title_prefix="closure-stale")
        | {"metadata": {"source_module": "feature61", "stale_timeout": 0}}
    )
    created_ids.append(stale.task_id)
    await real_ci_runtime.task_service.update_task_status(stale.task_id, TaskStatus.IN_PROGRESS, remarks="feature61 stale probe")

    retry = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}-retry", title_prefix="closure-retry")
        | {"metadata": {"source_module": "feature61", "attempt_count": 4}}
    )
    created_ids.append(retry.task_id)

    suspended = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}-suspended", title_prefix="closure-suspended")
        | {"metadata": {"source_module": "feature61"}}
    )
    created_ids.append(suspended.task_id)
    await real_ci_runtime.task_service.suspend_task(
        suspended.task_id,
        reason="feature61 recovery validation",
        recovery_conditions=["operator approval recorded"],
    )

    blocked = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}-blocked", title_prefix="closure-blocked")
        | {"metadata": {"source_module": "feature61", "blocked_reason": "waiting on dependency"}}
    )
    created_ids.append(blocked.task_id)
    await real_ci_runtime.task_service.update_task_status(blocked.task_id, TaskStatus.BLOCKED, remarks="waiting on dependency")

    try:
        report = real_ci_runtime.task_service.diagnose_task_management_closure(stale_after_seconds=0)
        assert report["metrics"]["total_tasks"] >= 4
        assert report["checks"]["state_machine_legal_transitions"] is True
        assert report["checks"]["dependency_cycle_detection"] is True
        assert report["checks"]["idempotent_replay_detection"] is True

        issues_by_task = {
            (issue["task_id"], issue["type"])
            for issue in report["issues"]
            if issue.get("task_id") in {stale.task_id, retry.task_id, suspended.task_id, blocked.task_id}
        }
        assert (stale.task_id, "stale_task") in issues_by_task
        assert (stale.task_id, "owner_lost") in issues_by_task
        assert (retry.task_id, "retry_budget_exceeded") in issues_by_task
        assert (suspended.task_id, "recovery_condition_missing") not in issues_by_task
        assert (blocked.task_id, "recovery_condition_missing") not in issues_by_task

        fault = real_ci_runtime.task_service.run_task_fault_injection_matrix(stale_after_seconds=0)
        assert fault["passed"] is True
        assert {case["name"] for case in fault["cases"]} >= {
            "stale_timeout_detector_ran",
            "retry_budget_detector_ran",
            "dependency_cycle_detector_ran",
            "recovery_and_audit_detectors_ran",
        }

        transcript_rows = real_ci_runtime.task_service.transcript_store.query_by_session("task-management-audit", limit=500)
        actions = [row.payload.get("action") for row in transcript_rows if row.payload]
        assert "TASK_MANAGEMENT_CLOSURE_DIAGNOSED" in actions
        assert "TASK_MANAGEMENT_FAULT_MATRIX_EXECUTED" in actions
    finally:
        current = real_ci_runtime.task_service.get_task(suspended.task_id)
        if current is not None and current.status == TaskStatus.SUSPENDED:
            await real_ci_runtime.task_service.resume_task(suspended.task_id, remarks="ci cleanup")
        real_ci_runtime.task_service.bulk_delete(created_ids, force=True)


@pytest.mark.asyncio
async def test_task_management_closure_api_uses_requests_and_checks_real_query_results(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    task_service = acceptance_app.state.task_service
    created_ids = []

    stale = await task_service.create_task(
        task_payload(suffix=f"{suffix}-api-stale", title_prefix="closure-api-stale")
        | {"metadata": {"source_module": "feature61-api", "stale_timeout": 0}}
    )
    created_ids.append(stale.task_id)
    await task_service.update_task_status(stale.task_id, TaskStatus.IN_PROGRESS, remarks="feature61 api stale probe")

    retry = await task_service.create_task(
        task_payload(suffix=f"{suffix}-api-retry", title_prefix="closure-api-retry")
        | {"metadata": {"source_module": "feature61-api", "attempt_count": 5}}
    )
    created_ids.append(retry.task_id)

    try:
        with live_http_server(acceptance_app) as base_url:
            diagnostic = requests.get(
                f"{base_url}/api/web/tasks/diagnostics/closure",
                params={"stale_after_seconds": 0},
                timeout=10,
            )
            assert diagnostic.status_code == 200, diagnostic.text
            payload = diagnostic.json()
            assert payload["checks"]["state_machine_legal_transitions"] is True
            assert payload["checks"]["dependency_cycle_detection"] is True
            assert payload["metrics"]["total_tasks"] >= 2
            issue_pairs = {
                (issue.get("task_id"), issue.get("type"))
                for issue in payload["issues"]
                if issue.get("task_id") in {stale.task_id, retry.task_id}
            }
            assert (stale.task_id, "stale_task") in issue_pairs
            assert (retry.task_id, "retry_budget_exceeded") in issue_pairs

            fault = requests.post(
                f"{base_url}/api/web/tasks/diagnostics/fault-injection",
                params={"stale_after_seconds": 0},
                timeout=10,
            )
            assert fault.status_code == 200, fault.text
            fault_payload = fault.json()
            assert fault_payload["passed"] is True
            assert any(case["name"] == "retry_budget_detector_ran" for case in fault_payload["cases"])
    finally:
        task_service.bulk_delete(created_ids, force=True)
