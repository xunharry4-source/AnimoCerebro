from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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


@pytest.mark.asyncio
async def test_plan_verification_data_api_writes_real_taskservice_records_and_queries_them(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    session_id = f"plan-verification-api-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/verification-data",
            params={"session_id": session_id, "sample_count": 5},
            timeout=20,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verification_data_status"] == "generated"
    assert payload["session_id"] == session_id
    assert payload["sample_count"] == 5
    assert payload["persisted_task_count"] == 5
    assert payload["persisted_outcome_count"] == 5
    assert payload["metadata_verified_count"] == 5
    assert payload["real_database"] is True
    assert payload["source"] == "generated_verification"
    assert payload["production_history_claimed"] is False
    assert payload["full_plan_completion_claimed"] is False
    assert payload["contract_summary"]["question_count"] == 9
    assert payload["contract_summary"]["consistency_errors"] == []
    assert len(payload["receipts"]) == 5
    assert all(receipt["source"] == "generated_verification" for receipt in payload["receipts"])
    assert all(receipt["production_history_claimed"] is False for receipt in payload["receipts"])
    assert all(receipt["outcome_passed"] is True for receipt in payload["receipts"])

    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    generated_tasks = [
        task
        for task in tasks
        if task.metadata.get("plan_verification_evidence", {}).get("source") == "generated_verification"
    ]
    assert len(generated_tasks) == 5
    for task in generated_tasks:
        evidence = task.metadata["plan_verification_evidence"]
        assert evidence["production_history_claimed"] is False
        assert evidence["natural_week_observation_claimed"] is False
        assert evidence["phase_d_real_activation_claimed"] is False
        assert evidence["question_contract_count"] == 9
        assert evidence["cross_q_consistency_errors"] == []
        assert task.metadata["q8_prompt_v2_metrics"]["source"] == "generated_verification"
        assert task.metadata["phase_d_verification"]["real_shadow_canary_activation_claimed"] is False
        outcome = acceptance_app.state.task_service.get_task_outcome(task.task_id)
        assert outcome is not None
        assert outcome["overall_passed"] is True
        assert outcome["actual_outcome"]["task_id"] == task.task_id
        assert outcome["actual_outcome"]["production_history_claimed"] is False


@pytest.mark.asyncio
async def test_prompt_contract_and_completion_gate_apis_are_real_requests_and_fail_closed_for_missing_external_evidence(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    session_id = f"plan-completion-gate-api-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        write_response = requests.post(
            f"{base_url}/api/web/nine-questions/plan/verification-data",
            params={"session_id": session_id, "sample_count": 2},
            timeout=20,
        )
        contracts_response = requests.get(
            f"{base_url}/api/web/nine-questions/prompt-contracts",
            timeout=10,
        )
        gate_response = requests.get(
            f"{base_url}/api/web/nine-questions/plan/completion-gate",
            params={"session_id": session_id, "expected_generated_count": 2},
            timeout=10,
        )

    assert write_response.status_code == 200
    assert contracts_response.status_code == 200
    contracts = contracts_response.json()
    assert contracts["contract_status"] == "passed"
    assert contracts["question_count"] == 9
    assert contracts["consistency_errors"] == []
    assert contracts["questions"]["q8"]["max_total_prompt_chars"] == 4000
    assert {item["field_name"] for item in contracts["questions"]["q9"]["output_fields"]} == {
        "evaluation_profile",
        "evolution_profile",
        "escalation_profile",
    }

    gate_payload = gate_response.json()
    if gate_response.status_code == 409:
        detail = gate_payload["detail"]
        assert detail["error"] == "plan_completion_gate_failed"
        assert detail["session_id"] == session_id
        report = detail["report"]
    else:
        assert gate_response.status_code == 200
        report = gate_payload
    expected_gate_status = "failed" if gate_response.status_code == 409 else "passed"
    assert report["gate_status"] == expected_gate_status
    assert report["generated_verification_count"] == 2
    assert report["production_history_claimed"] is False
    assert report["full_plan_completion_claimed"] is False
    assert len(report["receipts"]) == 2
    assert all(receipt["source"] == "generated_verification" for receipt in report["receipts"])
    if gate_response.status_code == 409:
        reasons = {failure["reason"] for failure in detail["failures"]}
        expected_reasons = {blocker["reason"] for blocker in report["blockers"]} | {
            blocker["reason"] for blocker in report["execution_blockers"]
        }
        assert expected_reasons
        assert expected_reasons.issubset(reasons)
        assert report["evidence_summary"]["missing_completion_evidence_kinds"] or report["execution_blockers"]
    else:
        assert report["blockers"] == []
        assert report["execution_blockers"] == []
