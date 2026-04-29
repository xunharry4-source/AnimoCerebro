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
from zentex.cognition.curiosity import CuriosityBudget, CuriosityEngine, EpistemicUncertainty
from zentex.memory.service import MemoryService


@contextmanager
def _live_http_server(app: FastAPI) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
    config = uvicorn.Config(app, host=host, port=port, log_level="critical", lifespan="off", access_log=False)
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


def test_g24_idle_cycle_generates_low_risk_curiosity_task_and_result_is_consolidated_to_memory(tmp_path) -> None:
    suffix = unique_suffix()
    engine = CuriosityEngine()
    memory_service = MemoryService(storage_root=tmp_path / f"g24-memory-{suffix}")
    uncertainty = EpistemicUncertainty(
        topic=f"unknown-file-format-{suffix}",
        description="Workspace contains a file extension that is not understood yet.",
        confidence=0.2,
        knowledge_gap_score=0.9,
        expected_learning_value=0.8,
        risk_level="low",
        estimated_tokens=180,
        estimated_compute_units=0.2,
        evidence_refs=[f"workspace://{suffix}/artifact.bin"],
        source="workspace_scanner",
    )

    report = engine.run_idle_cycle(
        uncertainties=[uncertainty],
        budget=CuriosityBudget(remaining_tokens=1000, remaining_compute_units=2.0),
        active_external_task_count=0,
    )
    task = report.generated_tasks[0]
    queried_task = engine.get_task(task.task_id)

    assert report.status == "tasks_generated"
    assert report.reason == "curiosity_drive_triggered_by_idle_uncertainty"
    assert queried_task is not None
    assert queried_task.status == "planned"
    assert queried_task.target_topics == [f"unknown-file-format-{suffix}"]
    assert queried_task.trigger_source == "idle_heartbeat"
    assert queried_task.learning_direction == "g24_curiosity"
    assert queried_task.budget_decision.approved is True
    assert queried_task.budget_decision.reason == "approved_low_risk_idle_curiosity"
    assert queried_task.budget_decision.estimated_tokens == 180

    result = engine.complete_task(
        task_id=task.task_id,
        findings=f"{suffix} artifact is a length-prefixed binary fixture; parser should inspect header bytes first.",
        confidence_delta=0.42,
        evidence_refs=[f"analysis://{suffix}/header-inspection"],
        memory_service=memory_service,
    )
    completed_task = engine.get_task(task.task_id)
    memory_record = memory_service.get_record(result.memory_id or "")
    recall_hits = memory_service.recall(f"length-prefixed binary fixture {suffix}", target_id=task.task_id, limit=5)

    assert completed_task is not None
    assert completed_task.status == "completed"
    assert completed_task.memory_id == result.memory_id
    assert completed_task.result_id == result.result_id
    assert memory_record is not None
    assert memory_record.target_id == task.task_id
    assert memory_record.trace_id == task.task_id
    assert memory_record.source_kind == "g24_curiosity"
    assert "g24" in memory_record.tags
    assert any(hit.memory_id == result.memory_id for hit in recall_hits)


def test_g24_budget_and_risk_gate_blocks_task_and_prevents_result_write(tmp_path) -> None:
    suffix = unique_suffix()
    engine = CuriosityEngine()
    memory_service = MemoryService(storage_root=tmp_path / f"g24-blocked-memory-{suffix}")
    costly = EpistemicUncertainty(
        topic=f"large-corpus-scan-{suffix}",
        description="Scan a large repository corpus to reduce uncertainty.",
        confidence=0.1,
        knowledge_gap_score=0.95,
        expected_learning_value=0.9,
        risk_level="medium",
        estimated_tokens=5000,
        estimated_compute_units=4.0,
        evidence_refs=[f"workspace://{suffix}/large-corpus"],
    )
    risky = EpistemicUncertainty(
        topic=f"production-behavior-probe-{suffix}",
        description="Probe a production-like system to learn its response.",
        confidence=0.1,
        knowledge_gap_score=0.95,
        expected_learning_value=0.9,
        risk_level="high",
        estimated_tokens=50,
        estimated_compute_units=0.1,
        evidence_refs=[f"prod://{suffix}/probe"],
    )

    report = engine.run_idle_cycle(
        uncertainties=[costly, risky],
        budget=CuriosityBudget(remaining_tokens=100, remaining_compute_units=1.0, max_tokens_per_task=200),
        active_external_task_count=0,
    )
    tasks = {task.target_topics[0]: task for task in report.generated_tasks}

    assert tasks[f"large-corpus-scan-{suffix}"].status == "blocked"
    assert tasks[f"large-corpus-scan-{suffix}"].blocked_reason == "blocked_by_g17_token_budget"
    assert tasks[f"production-behavior-probe-{suffix}"].status == "blocked"
    assert tasks[f"production-behavior-probe-{suffix}"].blocked_reason == "blocked_high_risk_curiosity_requires_non_autonomous_review"
    with pytest.raises(ValueError, match="not executable"):
        engine.complete_task(
            task_id=tasks[f"large-corpus-scan-{suffix}"].task_id,
            findings="This must not be written.",
            confidence_delta=0.1,
            evidence_refs=[f"analysis://{suffix}/blocked"],
            memory_service=memory_service,
        )
    assert memory_service.recall("This must not be written", target_id=tasks[f"large-corpus-scan-{suffix}"].task_id) == []


def test_g24_cycle_budget_is_consumed_across_generated_tasks_and_blocks_later_write(tmp_path) -> None:
    suffix = unique_suffix()
    engine = CuriosityEngine()
    memory_service = MemoryService(storage_root=tmp_path / f"g24-cumulative-budget-{suffix}")
    first = EpistemicUncertainty(
        topic=f"priority-gap-{suffix}",
        description="Inspect the highest value unknown contract first.",
        confidence=0.1,
        knowledge_gap_score=0.95,
        expected_learning_value=0.9,
        risk_level="low",
        estimated_tokens=180,
        estimated_compute_units=0.2,
        evidence_refs=[f"workspace://{suffix}/priority"],
    )
    second = EpistemicUncertainty(
        topic=f"later-gap-{suffix}",
        description="Inspect a second unknown contract only if budget remains.",
        confidence=0.2,
        knowledge_gap_score=0.9,
        expected_learning_value=0.8,
        risk_level="low",
        estimated_tokens=180,
        estimated_compute_units=0.2,
        evidence_refs=[f"workspace://{suffix}/later"],
    )

    report = engine.run_idle_cycle(
        uncertainties=[second, first],
        budget=CuriosityBudget(remaining_tokens=250, remaining_compute_units=1.0, max_tokens_per_task=250),
        active_external_task_count=0,
    )
    tasks = {task.target_topics[0]: task for task in report.generated_tasks}

    assert report.status == "tasks_generated"
    assert tasks[f"priority-gap-{suffix}"].status == "planned"
    assert tasks[f"priority-gap-{suffix}"].budget_decision.remaining_tokens == 250
    assert tasks[f"later-gap-{suffix}"].status == "blocked"
    assert tasks[f"later-gap-{suffix}"].budget_decision.remaining_tokens == 70
    assert tasks[f"later-gap-{suffix}"].blocked_reason == "blocked_by_g17_token_budget"
    with pytest.raises(ValueError, match="not executable"):
        engine.complete_task(
            task_id=tasks[f"later-gap-{suffix}"].task_id,
            findings="Blocked cumulative-budget task must not write memory.",
            confidence_delta=0.1,
            evidence_refs=[f"analysis://{suffix}/blocked-cumulative"],
            memory_service=memory_service,
        )
    assert memory_service.recall(
        "Blocked cumulative-budget task must not write memory",
        target_id=tasks[f"later-gap-{suffix}"].task_id,
    ) == []


def test_g24_active_external_task_prevents_idle_curiosity_generation() -> None:
    suffix = unique_suffix()
    engine = CuriosityEngine()
    uncertainty = EpistemicUncertainty(
        topic=f"deferred-gap-{suffix}",
        description="This should wait while external tasks are active.",
        confidence=0.1,
        knowledge_gap_score=0.95,
        expected_learning_value=0.9,
        risk_level="low",
        estimated_tokens=50,
        estimated_compute_units=0.1,
        evidence_refs=[f"workspace://{suffix}/deferred"],
    )

    report = engine.run_idle_cycle(
        uncertainties=[uncertainty],
        budget=CuriosityBudget(remaining_tokens=1000, remaining_compute_units=1.0),
        active_external_task_count=1,
    )

    assert report.status == "idle_not_available"
    assert report.reason == "external_task_active"
    assert report.generated_tasks == []
    assert engine.list_tasks() == []


def test_g24_curiosity_api_uses_requests_and_read_after_write_checks_task_and_memory(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.curiosity_engine = CuriosityEngine()

    with _live_http_server(acceptance_app) as base_url:
        cycle_response = requests.post(
            f"{base_url}/api/web/curiosity/cycles",
            json={
                "uncertainties": [
                    {
                        "topic": f"api-unknown-contract-{suffix}",
                        "description": "API response contract is not yet understood.",
                        "confidence": 0.15,
                        "knowledge_gap_score": 0.92,
                        "expected_learning_value": 0.85,
                        "risk_level": "low",
                        "estimated_tokens": 90,
                        "estimated_compute_units": 0.1,
                        "evidence_refs": [f"api://{suffix}/contract"],
                        "source": "api_contract_scanner",
                    }
                ],
                "budget": {
                    "remaining_tokens": 800,
                    "remaining_compute_units": 1.0,
                    "max_tokens_per_task": 500,
                    "max_compute_units_per_task": 0.5,
                },
                "active_external_task_count": 0,
                "trigger_source": "idle_heartbeat",
            },
            timeout=10,
        )
        assert cycle_response.status_code == 200
        cycle = cycle_response.json()
        task_id = cycle["generated_tasks"][0]["task_id"]

        task_response = requests.get(f"{base_url}/api/web/curiosity/tasks/{task_id}", timeout=10)
        result_response = requests.post(
            f"{base_url}/api/web/curiosity/tasks/{task_id}/results",
            json={
                "findings": f"{suffix} API contract requires explicit status and evidence fields.",
                "confidence_delta": 0.5,
                "evidence_refs": [f"analysis://{suffix}/api-contract"],
            },
            timeout=10,
        )
        completed_response = requests.get(f"{base_url}/api/web/curiosity/tasks/{task_id}", timeout=10)
        memory_response = requests.get(f"{base_url}/api/web/curiosity/tasks/{task_id}/memory-record", timeout=10)

    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "planned"
    assert task["target_topics"] == [f"api-unknown-contract-{suffix}"]
    assert task["budget_decision"]["approved"] is True
    assert task["budget_decision"]["estimated_tokens"] == 90

    assert result_response.status_code == 200
    result = result_response.json()
    assert result["task_id"] == task_id
    assert result["memory_id"]
    assert result["reusable_for_decisions"] is True

    assert completed_response.status_code == 200
    completed = completed_response.json()
    assert completed["status"] == "completed"
    assert completed["memory_id"] == result["memory_id"]
    assert completed["result_id"] == result["result_id"]

    assert memory_response.status_code == 200
    memory = memory_response.json()
    assert memory["task_id"] == task_id
    assert memory["memory_id"] == result["memory_id"]
    assert memory["source"] == "g24_curiosity"
    assert memory["trace_id"] == task_id
    assert memory["target_id"] == task_id
    assert f"{suffix} API contract requires explicit status and evidence fields." in memory["content"]
    assert "g24" in memory["tags"]
