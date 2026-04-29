from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.router import api_router


def _cluster_adapter_app(brain_scope: str, snapshot_version: int) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "cluster-core-adapter"}

    @app.post("/state-sync/check")
    def state_sync(payload: dict) -> dict:
        return {
            "state_sync_ok": payload["brain_scope"] == brain_scope,
            "brain_scope": brain_scope,
            "snapshot_version": snapshot_version,
        }

    return app


def test_g39_g46_deployment_modes_real_requests_configure_query_and_cluster_sync() -> None:
    suffix = unique_suffix()
    app = FastAPI()
    app.include_router(api_router)
    cluster_scope = f"cluster-scope-{suffix}"

    with live_http_server(_cluster_adapter_app(cluster_scope, 7)) as adapter_url:
        with live_http_server(app) as base_url:
            single_response = requests.post(
                f"{base_url}/api/web/deployment-mode/configure",
                json={
                    "deployment_mode": "single_prod",
                    "brain_scope": f"single-scope-{suffix}",
                    "configured_by": "real-test",
                },
                timeout=20,
            )
            assert single_response.status_code == 200, single_response.text
            single_state = single_response.json()
            assert single_state["deployment_mode"] == "single_prod"
            assert single_state["in_process_services"] is True
            assert single_state["adapter_count"] == 0

            single_check = requests.post(f"{base_url}/api/web/deployment-mode/sync-check", timeout=20)
            assert single_check.status_code == 200, single_check.text
            assert single_check.json()["ready"] is True
            queried_single = requests.get(f"{base_url}/api/web/deployment-mode/state", timeout=20).json()
            assert queried_single["last_sync_check"]["deployment_mode"] == "single_prod"

            invalid_response = requests.post(
                f"{base_url}/api/web/deployment-mode/configure",
                json={
                    "deployment_mode": "cluster_core",
                    "brain_scope": cluster_scope,
                    "configured_by": "real-test",
                    "adapters": [],
                },
                timeout=20,
            )
            assert invalid_response.status_code == 400
            assert "requires at least one remote adapter" in invalid_response.text

            cluster_response = requests.post(
                f"{base_url}/api/web/deployment-mode/configure",
                json={
                    "deployment_mode": "cluster_core",
                    "brain_scope": cluster_scope,
                    "configured_by": "real-test",
                    "adapters": [
                        {
                            "adapter_id": f"adapter-{suffix}",
                            "base_url": adapter_url,
                            "adapter_kind": "http",
                            "expected_brain_scope": cluster_scope,
                        }
                    ],
                },
                timeout=20,
            )
            assert cluster_response.status_code == 200, cluster_response.text
            cluster_state = cluster_response.json()
            assert cluster_state["deployment_mode"] == "cluster_core"
            assert cluster_state["in_process_services"] is False
            assert cluster_state["adapter_count"] == 1

            cluster_check = requests.post(f"{base_url}/api/web/deployment-mode/sync-check", timeout=20)
            assert cluster_check.status_code == 200, cluster_check.text
            checked = cluster_check.json()
            assert checked["ready"] is True
            assert checked["adapter_results"][0]["healthy"] is True
            assert checked["adapter_results"][0]["state_sync_ok"] is True
            assert checked["adapter_results"][0]["remote_snapshot_version"] == 7


def test_g42_openclaw_bridge_real_requests_call_query_and_fail_closed() -> None:
    suffix = unique_suffix()
    app = FastAPI()
    app.include_router(api_router)
    request_id = f"openclaw-{suffix}"

    with live_http_server(app) as base_url:
        call_response = requests.post(
            f"{base_url}/api/web/openclaw/bridge/call",
            json={
                "host_id": f"host-{suffix}",
                "request_id": request_id,
                "action": "nine_question_query",
                "payload": {"question": "Should this host task become a Zentex objective?"},
            },
            timeout=20,
        )
        assert call_response.status_code == 200, call_response.text
        result = call_response.json()
        assert result["accepted"] is True
        assert result["request_id"] == request_id
        assert result["result"]["route"] == "zentex.nine_questions"
        assert "nine_question_frame" in result["result"]["available_outputs"]

        audit_response = requests.get(f"{base_url}/api/web/openclaw/bridge/audit/{request_id}", timeout=20)
        assert audit_response.status_code == 200, audit_response.text
        audit = audit_response.json()
        assert audit["request_id"] == request_id
        assert audit["result"] == result["result"]

        invalid_response = requests.post(
            f"{base_url}/api/web/openclaw/bridge/call",
            json={
                "host_id": f"host-{suffix}",
                "request_id": f"bad-{suffix}",
                "action": "task_submit",
                "payload": {},
            },
            timeout=20,
        )
        assert invalid_response.status_code == 400
        assert "payload.title" in invalid_response.text

        missing_audit = requests.get(f"{base_url}/api/web/openclaw/bridge/audit/missing-{suffix}", timeout=20)
        assert missing_audit.status_code == 404
