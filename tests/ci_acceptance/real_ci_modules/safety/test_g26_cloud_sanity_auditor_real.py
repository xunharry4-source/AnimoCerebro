from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import time
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.safety.cloud_auditor import CloudAuditorClient, CloudAuditorConfig


API_KEY = "g26-api-key"
API_SECRET = "g26-secret"


def _request_signature(payload: dict[str, Any], secret: str = API_SECRET) -> str:
    timestamp = int(datetime.fromisoformat(payload["timestamp"]).timestamp())
    canonical = f"{payload['action_type']}|{payload['request_id']}|{timestamp}"
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


def _decision_signature(decision: dict[str, Any], secret: str = API_SECRET) -> str:
    timestamp = int(datetime.fromisoformat(decision["created_at"]).timestamp())
    canonical = f"{decision['decision_id']}|{decision['request_id']}|{timestamp}|{decision['status']}"
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


@contextmanager
def _cloud_audit_server(*, valid_signature: bool = True, status: str = "approved") -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
            received.append(
                {
                    "path": self.path,
                    "api_key": self.headers.get("X-Zentex-Api-Key"),
                    "signature": self.headers.get("X-Zentex-Signature"),
                    "payload": payload,
                    "expected_signature": _request_signature(payload),
                }
            )
            if self.headers.get("X-Zentex-Api-Key") != API_KEY:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"bad api key"}')
                return
            if self.headers.get("X-Zentex-Signature") != _request_signature(payload):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"bad signature"}')
                return

            created_at = datetime.now(timezone.utc).isoformat()
            decision = {
                "decision_id": f"decision-{payload['request_id']}",
                "request_id": payload["request_id"],
                "policy_version": "cloud-policy-test-2026-04-29",
                "status": status,
                "reason": "signed cloud decision from local real HTTP service",
                "constraints": {
                    "cloud_policy_checked": True,
                    "risk_level": payload["risk_level"],
                },
                "expires_at": None,
                "signature": "",
                "created_at": created_at,
            }
            decision["signature"] = _decision_signature(decision) if valid_signature else "hmac-sha256=bad"
            body = json.dumps(decision).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}/v1/decide", received
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


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


def test_g26_cloud_client_sends_signed_real_http_request_and_accepts_signed_response() -> None:
    suffix = unique_suffix()
    with _cloud_audit_server(valid_signature=True, status="approved") as (endpoint, received):
        client = CloudAuditorClient(
            CloudAuditorConfig(endpoint=endpoint, api_key=API_KEY, api_secret=API_SECRET, timeout_seconds=2),
            brain_scope=f"g26-{suffix}",
        )
        decision = client.audit_action(
            "self_modify",
            {"patch": f"guarded-change-{suffix}"},
            risk_level="high",
            context={"trace_id": suffix},
            use_cache=False,
        )

    assert decision.status == "approved"
    assert decision.policy_version == "cloud-policy-test-2026-04-29"
    assert decision.constraints["cloud_policy_checked"] is True
    assert decision.constraints["risk_level"] == "high"
    assert len(received) == 1
    assert received[0]["path"] == "/v1/decide"
    assert received[0]["api_key"] == API_KEY
    assert received[0]["signature"] == received[0]["expected_signature"]
    assert received[0]["payload"]["action_payload"] == {"patch": f"guarded-change-{suffix}"}
    assert client.get_decision(decision.decision_id).request_id == decision.request_id
    assert client.get_request_history()[0].client_signature == received[0]["expected_signature"]
    assert client.get_degradation_history() == []


def test_g26_invalid_response_signature_is_rejected_and_degraded_without_fake_approval() -> None:
    suffix = unique_suffix()
    with _cloud_audit_server(valid_signature=False, status="approved") as (endpoint, _received):
        client = CloudAuditorClient(
            CloudAuditorConfig(endpoint=endpoint, api_key=API_KEY, api_secret=API_SECRET, timeout_seconds=2),
            brain_scope=f"g26-bad-signature-{suffix}",
        )
        decision = client.audit_action("credential_rotation", {"scope": suffix}, risk_level="critical", use_cache=False)

    assert decision.status == "review_required"
    assert decision.policy_version == "local-fallback-1.0"
    assert decision.constraints["degraded_mode"] is True
    assert decision.constraints["requires_local_review"] is True
    assert decision.constraints["disable_self_modify"] is True
    assert "Decision signature verification failed" in client.get_degradation_history()[0].reason


def test_g26_missing_credentials_are_explicit_degradation_and_boundary_is_queryable() -> None:
    suffix = unique_suffix()
    client = CloudAuditorClient(brain_scope=f"g26-unconfigured-{suffix}")
    decision = client.audit_action("self_modify", {"patch": suffix}, risk_level="high")
    boundary = client.get_boundary_definition()

    assert decision.status == "review_required"
    assert "Cloud auditor not configured" in decision.reason
    assert decision.constraints["degraded_mode"] is True
    assert client.degradation_count == 1
    assert boundary.high_risk_requires_cloud_audit is True
    assert boundary.missing_credentials_fail_closed is True
    assert boundary.invalid_response_signature_rejected is True
    assert "CloudAuditorClient request signing" in boundary.open_source_components
    assert "remote independent policy decision service" in boundary.cloud_components


def test_g26_cloud_sanity_auditor_api_uses_requests_and_read_after_write_checks_decision_and_degradation(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    with _cloud_audit_server(valid_signature=True, status="approved") as (cloud_endpoint, received):
        acceptance_app.state.cloud_sanity_auditor_client = CloudAuditorClient()
        with _live_http_server(acceptance_app) as base_url:
            config_response = requests.post(
                f"{base_url}/api/web/cloud-sanity-auditor/config",
                json={
                    "endpoint": cloud_endpoint,
                    "api_key": API_KEY,
                    "api_secret": API_SECRET,
                    "timeout_seconds": 2,
                },
                timeout=10,
            )
            boundary_response = requests.get(f"{base_url}/api/web/cloud-sanity-auditor/boundary", timeout=10)
            audit_response = requests.post(
                f"{base_url}/api/web/cloud-sanity-auditor/audit-actions",
                json={
                    "action_type": "self_modify",
                    "action_payload": {"patch": f"api-patch-{suffix}"},
                    "risk_level": "high",
                    "context": {"trace_id": suffix},
                    "use_cache": False,
                },
                timeout=10,
            )
            assert audit_response.status_code == 200
            decision = audit_response.json()
            decision_response = requests.get(
                f"{base_url}/api/web/cloud-sanity-auditor/decisions/{decision['decision_id']}",
                timeout=10,
            )
            decisions_response = requests.get(f"{base_url}/api/web/cloud-sanity-auditor/decisions", timeout=10)
            requests_response = requests.get(f"{base_url}/api/web/cloud-sanity-auditor/requests", timeout=10)
            degradations_response = requests.get(f"{base_url}/api/web/cloud-sanity-auditor/degradations", timeout=10)

    assert config_response.status_code == 200
    assert config_response.json()["is_configured"] is True
    assert boundary_response.status_code == 200
    assert boundary_response.json()["high_risk_requires_cloud_audit"] is True
    assert decision["status"] == "approved"
    assert decision["constraints"]["cloud_policy_checked"] is True
    assert decision_response.status_code == 200
    assert decision_response.json()["decision_id"] == decision["decision_id"]
    assert decision_response.json()["request_id"] == decision["request_id"]
    assert decisions_response.status_code == 200
    assert [row["decision_id"] for row in decisions_response.json()] == [decision["decision_id"]]
    assert requests_response.status_code == 200
    assert requests_response.json()[0]["action_payload"] == {"patch": f"api-patch-{suffix}"}
    assert degradations_response.status_code == 200
    assert degradations_response.json() == []
    assert received[0]["signature"] == received[0]["expected_signature"]
