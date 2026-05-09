from __future__ import annotations

import requests
import pytest
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _g5_payload(*, session_id: str, task_id: str, suffix: str) -> dict:
    return {
        "session_id": session_id,
        "task_id": task_id,
        "gap_type": "permission",
        "required_asset": f"/restricted/g5/{suffix}",
        "observed_error": f"PermissionError: [Errno 13] Permission denied: /restricted/g5/{suffix}",
        "recovery_conditions": [
            f"grant-read-access:/restricted/g5/{suffix}",
            "operator-confirms-host-boundary",
        ],
        "task_context": {
            "source": "g5-real-ci",
            "blocked_operation": "read protected workspace directory",
        },
        "proposed_tradeoff": "Wait for explicit host permission and preserve task progress.",
        "priority": 2,
    }


def _assert_created(payload: dict, *, task_id: str) -> None:
    assert payload["feature_code"] == "G5"
    assert payload["task"]["task_id"] == task_id
    assert payload["task"]["status"] == "suspended"
    assert payload["duplicate_prevented"] is False

    negotiation = payload["negotiation"]
    assert negotiation["feature_code"] == "G5"
    assert negotiation["target_task_id"] == task_id
    assert negotiation["gap_type"] == "permission"
    assert negotiation["required_asset"]
    assert negotiation["status"] == "pending"
    assert "PermissionError" in negotiation["observed_error"]
    assert negotiation["recovery_conditions"]

    suspended = payload["suspended_task"]
    assert suspended["task_id"] == task_id
    assert suspended["original_status"] == "todo"
    assert "G5 permission gap" in suspended["suspension_reason"]
    assert suspended["recovery_conditions"] == negotiation["recovery_conditions"]
    assert suspended["suspension_context"]["negotiation_id"] == negotiation["negotiation_id"]
    assert suspended["suspension_context"]["feature_code"] == "G5"


def _assert_query_has(query: dict, *, task_id: str, negotiation_id: str, status: str) -> dict:
    assert query["feature_code"] == "G5"
    assert query["negotiation_count"] >= 1
    matches = [
        item
        for item in query["negotiations"]
        if item["task"]["task_id"] == task_id
        and item["negotiation"]["negotiation_id"] == negotiation_id
    ]
    assert matches, f"G5 negotiation {negotiation_id} not query-visible"
    record = matches[0]
    assert record["negotiation"]["status"] == status
    assert record["negotiation"]["target_task_id"] == task_id
    return record


def _assert_g5_transcript(kernel_service, *, session_id: str, negotiation_id: str, expected_event: str) -> None:
    entries = kernel_service.get_transcript(session_id, limit=300)
    matches = [
        entry
        for entry in entries
        if entry["payload"].get("feature_code") == "G5"
        and entry["payload"].get("entry_type") == expected_event
        and entry["payload"].get("negotiation_id") == negotiation_id
    ]
    assert matches, f"G5 transcript event {expected_event} missing for {negotiation_id}"


async def _create_task(real_ci_runtime, *, suffix: str):
    return await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="g5-resource-negotiation", source_module="g5_real_ci")
    )


@pytest.mark.asyncio
async def test_g5_resource_negotiation_service_suspends_queries_and_resumes_real_task(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g5-service-{suffix}")
    task = await _create_task(real_ci_runtime, suffix=suffix)

    created = await kernel_service.create_resource_negotiation_request(**_g5_payload(
        session_id=session_id,
        task_id=task.task_id,
        suffix=suffix,
    ))
    _assert_created(created, task_id=task.task_id)
    negotiation_id = created["negotiation"]["negotiation_id"]

    queried_task = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried_task is not None and queried_task.status.value == "suspended"
    assert real_ci_runtime.task_service.get_suspended_task(task.task_id) is not None
    _assert_g5_transcript(
        kernel_service,
        session_id=session_id,
        negotiation_id=negotiation_id,
        expected_event="g5_negotiation_request_created",
    )

    duplicate = await kernel_service.create_resource_negotiation_request(**_g5_payload(
        session_id=session_id,
        task_id=task.task_id,
        suffix=suffix,
    ))
    assert duplicate["duplicate_prevented"] is True
    assert duplicate["negotiation"]["negotiation_id"] == negotiation_id

    query_pending = kernel_service.query_resource_negotiation_requests(
        session_id=session_id,
        task_id=task.task_id,
        status="pending",
    )
    pending_record = _assert_query_has(
        query_pending,
        task_id=task.task_id,
        negotiation_id=negotiation_id,
        status="pending",
    )
    assert pending_record["suspended_task"]["task_id"] == task.task_id

    resolved = await kernel_service.resolve_resource_negotiation_request(
        session_id=session_id,
        negotiation_id=negotiation_id,
        approved=True,
        resolution_note="CI granted explicit read permission for the blocked asset.",
        granted_asset=created["negotiation"]["required_asset"],
    )
    assert resolved["feature_code"] == "G5"
    assert resolved["approved"] is True
    assert resolved["resumed"] is True
    assert resolved["task"]["task_id"] == task.task_id
    assert resolved["task"]["status"] == "todo"
    assert resolved["remaining_suspension"] is None

    queried_after = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried_after is not None and queried_after.status.value == "todo"
    assert real_ci_runtime.task_service.get_suspended_task(task.task_id) is None

    query_resolved = kernel_service.query_resource_negotiation_requests(
        session_id=session_id,
        task_id=task.task_id,
        status="resolved",
    )
    resolved_record = _assert_query_has(
        query_resolved,
        task_id=task.task_id,
        negotiation_id=negotiation_id,
        status="resolved",
    )
    assert resolved_record["recovery_ready"] is True
    assert resolved_record["suspended_task"] is None
    _assert_g5_transcript(
        kernel_service,
        session_id=session_id,
        negotiation_id=negotiation_id,
        expected_event="g5_negotiation_request_resolved",
    )


@pytest.mark.asyncio
async def test_g5_resource_negotiation_api_requests_create_query_resolve_and_requery(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g5-api-{suffix}")
    task = await _create_task(real_ci_runtime, suffix=f"api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        create_response = requests.post(
            f"{base_url}/api/web/runtime/resource-negotiations",
            json=_g5_payload(session_id=session_id, task_id=task.task_id, suffix=suffix),
            timeout=30,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        negotiation_id = created["negotiation"]["negotiation_id"]

        query_pending_response = requests.get(
            f"{base_url}/api/web/runtime/resource-negotiations",
            params={"session_id": session_id, "task_id": task.task_id, "status": "pending"},
            timeout=20,
        )
        resolve_response = requests.post(
            f"{base_url}/api/web/runtime/resource-negotiations/resolve",
            json={
                "session_id": session_id,
                "negotiation_id": negotiation_id,
                "approved": True,
                "resolution_note": "API test granted the blocked permission.",
                "granted_asset": created["negotiation"]["required_asset"],
            },
            timeout=30,
        )
        query_resolved_response = requests.get(
            f"{base_url}/api/web/runtime/resource-negotiations",
            params={"session_id": session_id, "task_id": task.task_id, "status": "resolved"},
            timeout=20,
        )

    _assert_created(created, task_id=task.task_id)
    assert query_pending_response.status_code == 200, query_pending_response.text
    pending_record = _assert_query_has(
        query_pending_response.json(),
        task_id=task.task_id,
        negotiation_id=negotiation_id,
        status="pending",
    )
    assert pending_record["task"]["status"] == "suspended"

    assert resolve_response.status_code == 200, resolve_response.text
    resolved = resolve_response.json()
    assert resolved["approved"] is True
    assert resolved["task"]["status"] == "todo"
    assert resolved["remaining_suspension"] is None

    assert query_resolved_response.status_code == 200, query_resolved_response.text
    resolved_record = _assert_query_has(
        query_resolved_response.json(),
        task_id=task.task_id,
        negotiation_id=negotiation_id,
        status="resolved",
    )
    assert resolved_record["recovery_ready"] is True
    assert real_ci_runtime.task_service.get_suspended_task(task.task_id) is None
    queried_task = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried_task is not None and queried_task.status.value == "todo"
