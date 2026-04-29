from __future__ import annotations

import requests
import pytest
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix
from zentex.agents.manager import AgentAsset, AgentStatus, AgentTrustLevel
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _agent_app(*, agent_id: str, capability: str, confidence: float, cost: float) -> FastAPI:
    app = FastAPI()

    @app.get("/status")
    def status() -> dict:
        return {"status": "ok", "agent_id": agent_id}

    @app.post("/bid")
    def bid(payload: dict) -> dict:
        assert payload["feature_code"] == "G7"
        assert payload["task_id"]
        required = set(payload["required_capabilities"])
        if capability not in required:
            return {"accept": False, "reason": "capability_not_available"}
        return {
            "accept": True,
            "bid_id": f"bid-{agent_id}-{payload['conflict_id']}",
            "confidence": confidence,
            "cost": cost,
            "estimated_seconds": 5,
            "evidence": {"capability": capability, "transport": "real_http"},
        }

    return app


def _register_agent(agent_service, *, agent_id: str, endpoint: str, capability: str, confidence: float) -> AgentAsset:
    asset = AgentAsset(
        agent_id=agent_id,
        name=agent_id,
        agent_name=agent_id,
        version="1.0.0",
        function_description=f"Real HTTP bidding agent for {capability}",
        endpoint=endpoint,
        auth_token="ci-token",
        role_tag="worker",
        trust_level=AgentTrustLevel.TRUSTED,
        status=AgentStatus.IDLE,
        scope=[capability],
        capabilities=[{"name": capability, "confidence": confidence}],
        latency_ms=20,
        success_rate=confidence,
    )
    agent_service.manager.add_asset(asset)
    return asset


def _assert_conflict(payload: dict, *, task_id: str, selected_agent_id: str, status: str) -> None:
    assert payload["feature_code"] == "G7"
    assert payload["task_id"] == task_id
    assert payload["status"] == status
    assert payload["transport"] == "http"
    assert payload["selected_agent_id"] == selected_agent_id
    assert payload["bid_count"] >= 1
    assert payload["broadcast_count"] >= payload["bid_count"]
    assert payload["adjudication"]["order"][0] == "capability_match_score"
    assert any(bid["agent_id"] == selected_agent_id for bid in payload["bids"])
    assert payload["task"]["metadata"]["g7_inter_agent_conflicts"]


def _assert_persisted_task(task, *, conflict_id: str, selected_agent_id: str) -> None:
    records = task.metadata["g7_inter_agent_conflicts"]
    matches = [item for item in records if item["conflict_id"] == conflict_id]
    assert matches, f"G7 conflict {conflict_id} is not persisted on task metadata"
    assert matches[0]["selected_agent_id"] == selected_agent_id


async def _create_g7_task(real_ci_runtime, *, suffix: str):
    payload = task_payload(suffix=suffix, title_prefix="g7-inter-agent", source_module="g7_real_ci")
    return await real_ci_runtime.task_service.create_task(payload)


@pytest.mark.asyncio
async def test_g7_inter_agent_service_broadcasts_adjudicates_ejects_and_reassigns_real_http(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g7-service-{suffix}")
    task = await _create_g7_task(real_ci_runtime, suffix=suffix)
    real_ci_runtime.agent_service.manager.clear_assets()

    best_app = _agent_app(agent_id=f"g7-best-{suffix}", capability="code-review", confidence=0.94, cost=4)
    backup_app = _agent_app(agent_id=f"g7-backup-{suffix}", capability="code-review", confidence=0.72, cost=8)
    with live_http_server(best_app) as best_url, live_http_server(backup_app) as backup_url:
        best = _register_agent(
            real_ci_runtime.agent_service,
            agent_id=f"g7-best-{suffix}",
            endpoint=best_url,
            capability="code-review",
            confidence=0.94,
        )
        backup = _register_agent(
            real_ci_runtime.agent_service,
            agent_id=f"g7-backup-{suffix}",
            endpoint=backup_url,
            capability="code-review",
            confidence=0.72,
        )
        down = _register_agent(
            real_ci_runtime.agent_service,
            agent_id=f"g7-down-{suffix}",
            endpoint="http://127.0.0.1:9",
            capability="code-review",
            confidence=0.99,
        )

        created = await kernel_service.create_inter_agent_conflict(
            session_id=session_id,
            task_id=task.task_id,
            task_payload={"title": task.title, "acceptance": ["return bid evidence"], "suffix": suffix},
            required_capabilities=["code-review"],
            timeout_seconds=1.0,
        )

        _assert_conflict(created, task_id=task.task_id, selected_agent_id=best.agent_id, status="assigned")
        assert created["broadcast_count"] == 3
        assert created["bid_count"] == 2
        assert any(item["agent_id"] == down.agent_id and item["status"] == "transport_failed" for item in created["failed_agents"])
        assert real_ci_runtime.agent_service.manager.get_asset(down.agent_id).status == AgentStatus.OFFLINE

        queried = kernel_service.query_inter_agent_conflict(
            session_id=session_id,
            conflict_id=created["conflict_id"],
            task_id=task.task_id,
        )
        _assert_conflict(queried, task_id=task.task_id, selected_agent_id=best.agent_id, status="assigned")
        _assert_persisted_task(
            real_ci_runtime.task_service.get_task(task.task_id),
            conflict_id=created["conflict_id"],
            selected_agent_id=best.agent_id,
        )

        reassigned = await kernel_service.reassign_inter_agent_conflict(
            session_id=session_id,
            conflict_id=created["conflict_id"],
            task_id=task.task_id,
            failed_agent_id=best.agent_id,
            failure_reason="selected agent returned an execution receipt failure",
        )
        _assert_conflict(reassigned, task_id=task.task_id, selected_agent_id=backup.agent_id, status="reassigned")
        assert real_ci_runtime.agent_service.manager.get_asset(best.agent_id).status == AgentStatus.OFFLINE
        _assert_persisted_task(
            real_ci_runtime.task_service.get_task(task.task_id),
            conflict_id=created["conflict_id"],
            selected_agent_id=backup.agent_id,
        )

    entries = kernel_service.get_transcript(session_id, limit=300)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G7"}
    assert {"g7_inter_agent_negotiated", "g7_inter_agent_reassigned"} <= event_types


@pytest.mark.asyncio
async def test_g7_inter_agent_api_requests_create_query_and_reassign_real_http(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g7-api-{suffix}")
    task = await _create_g7_task(real_ci_runtime, suffix=f"api-{suffix}")
    real_ci_runtime.agent_service.manager.clear_assets()
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    best_app = _agent_app(agent_id=f"g7-api-best-{suffix}", capability="analysis", confidence=0.91, cost=3)
    backup_app = _agent_app(agent_id=f"g7-api-backup-{suffix}", capability="analysis", confidence=0.63, cost=7)
    with live_http_server(best_app) as best_url, live_http_server(backup_app) as backup_url, live_http_server(app) as base_url:
        best = _register_agent(
            real_ci_runtime.agent_service,
            agent_id=f"g7-api-best-{suffix}",
            endpoint=best_url,
            capability="analysis",
            confidence=0.91,
        )
        backup = _register_agent(
            real_ci_runtime.agent_service,
            agent_id=f"g7-api-backup-{suffix}",
            endpoint=backup_url,
            capability="analysis",
            confidence=0.63,
        )

        create_response = requests.post(
            f"{base_url}/api/web/runtime/inter-agent/conflicts",
            json={
                "session_id": session_id,
                "task_id": task.task_id,
                "task_payload": {"title": task.title, "suffix": suffix},
                "required_capabilities": ["analysis"],
                "timeout_seconds": 1.0,
            },
            timeout=20,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()

        query_response = requests.get(
            f"{base_url}/api/web/runtime/inter-agent/conflicts/{created['conflict_id']}",
            params={"session_id": session_id, "task_id": task.task_id},
            timeout=20,
        )
        reassign_response = requests.post(
            f"{base_url}/api/web/runtime/inter-agent/conflicts/{created['conflict_id']}/reassign",
            json={
                "session_id": session_id,
                "task_id": task.task_id,
                "failed_agent_id": best.agent_id,
                "failure_reason": "API test execution receipt failed",
            },
            timeout=20,
        )

    _assert_conflict(created, task_id=task.task_id, selected_agent_id=best.agent_id, status="assigned")
    assert query_response.status_code == 200, query_response.text
    _assert_conflict(query_response.json(), task_id=task.task_id, selected_agent_id=best.agent_id, status="assigned")

    assert reassign_response.status_code == 200, reassign_response.text
    reassigned = reassign_response.json()
    _assert_conflict(reassigned, task_id=task.task_id, selected_agent_id=backup.agent_id, status="reassigned")
    assert real_ci_runtime.agent_service.manager.get_asset(best.agent_id).status == AgentStatus.OFFLINE
    _assert_persisted_task(
        real_ci_runtime.task_service.get_task(task.task_id),
        conflict_id=created["conflict_id"],
        selected_agent_id=backup.agent_id,
    )
