from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any

import requests
from fastapi import FastAPI, Request

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


API_KEY = "g8-api-key"
API_SECRET = "g8-secret"


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


def _cloud_app(*, received: list[dict[str, Any]], status: str = "approved") -> FastAPI:
    app = FastAPI()

    @app.post("/v1/decide")
    async def decide(request: Request) -> dict[str, Any]:
        payload = await request.json()
        received.append(
            {
                "api_key": request.headers.get("X-Zentex-Api-Key"),
                "signature": request.headers.get("X-Zentex-Signature"),
                "expected_signature": _request_signature(payload),
                "payload": payload,
            }
        )
        assert request.headers.get("X-Zentex-Api-Key") == API_KEY
        assert request.headers.get("X-Zentex-Signature") == _request_signature(payload)
        created_at = datetime.now(timezone.utc).isoformat()
        decision = {
            "decision_id": f"g8-cloud-{payload['request_id']}",
            "request_id": payload["request_id"],
            "policy_version": "g8-cloud-policy-real-http",
            "status": status,
            "reason": "G8 real cloud audit decision",
            "constraints": {"cloud_policy_checked": True, "risk_level": payload["risk_level"]},
            "expires_at": None,
            "signature": "",
            "created_at": created_at,
        }
        decision["signature"] = _decision_signature(decision)
        return decision

    return app


def _assert_query_matches(query: dict, original: dict) -> None:
    assert query["feature_code"] == "G8"
    assert query["decision_id"] == original["decision_id"]
    assert query["action_type"] == original["action_type"]
    assert query["status"] == original["status"]
    assert query["query_visible"] is True


def test_g8_safety_gate_service_validates_queries_confirms_and_cloud_audits_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g8-service-{suffix}")

    allowed = kernel_service.validate_safety_gate_action(
        session_id=session_id,
        action_type="get_status",
        action_payload={"target": "runtime", "parameters": {"scope": suffix}},
        risk_level="low",
        execution_mode="real",
    )
    assert allowed["feature_code"] == "G8"
    assert allowed["status"] == "allowed"
    assert allowed["allowed"] is True
    assert allowed["execution_allowed"] is True
    _assert_query_matches(
        kernel_service.query_safety_gate_decision(session_id=session_id, decision_id=allowed["decision_id"]),
        allowed,
    )

    pending = kernel_service.validate_safety_gate_action(
        session_id=session_id,
        action_type="delete_file",
        action_payload={"target": f"/tmp/g8-delete-{suffix}", "parameters": {"recursive": False}},
        risk_level="high",
        execution_mode="dry_run",
    )
    assert pending["status"] == "requires_confirmation"
    assert pending["execution_allowed"] is False
    assert pending["constraints"]["requires_dual_confirmation"] is True
    _assert_query_matches(
        kernel_service.query_safety_gate_decision(session_id=session_id, decision_id=pending["decision_id"]),
        pending,
    )
    confirmed = kernel_service.confirm_safety_gate_decision(
        session_id=session_id,
        decision_id=pending["decision_id"],
        confirmed_by="g8-real-ci-operator",
        confirmation_context={"ticket": suffix},
    )
    assert confirmed["status"] == "allowed"
    assert confirmed["execution_allowed"] is True
    assert confirmed["constraints"]["confirmed_by"] == "g8-real-ci-operator"
    assert kernel_service.query_safety_gate_decision(
        session_id=session_id,
        decision_id=confirmed["decision_id"],
    )["status"] == "allowed"

    alias_blocked = kernel_service.validate_safety_gate_action(
        session_id=session_id,
        action_type="rm",
        action_payload={"target": f"/tmp/g8-alias-{suffix}", "parameters": {"force": True}},
        risk_level="high",
        execution_mode="dry_run",
    )
    assert alias_blocked["status"] == "blocked"
    assert alias_blocked["execution_allowed"] is False
    assert alias_blocked["action_type"] == "delete_file"
    assert alias_blocked["bypass_attempts"][0]["attempt_type"] == "alias_call"
    assert alias_blocked["replanning_feedback"]["blocked_action"] == "delete_file"

    identity_review = kernel_service.validate_safety_gate_action(
        session_id=session_id,
        action_type="update_identity_kernel",
        action_payload={"target": "src/zentex/kernel/identity_kernel.py", "parameters": {"role_name": "unsafe"}},
        risk_level="critical",
        execution_mode="real",
    )
    assert identity_review["status"] == "requires_human_review"
    assert identity_review["execution_allowed"] is False
    assert identity_review["redline_category"] == "identity_write"
    assert identity_review["cloud_audit_required"] is True

    missing_cloud = kernel_service.validate_safety_gate_action(
        session_id=session_id,
        action_type="execute_command",
        action_payload={"target": "host", "command": "deploy", "parameters": {"suffix": suffix}},
        risk_level="high",
        execution_mode="real",
    )
    assert missing_cloud["status"] == "requires_cloud_audit"
    assert missing_cloud["execution_allowed"] is False
    assert missing_cloud["cloud_audit_required"] is True
    assert "cloud audit approval" in missing_cloud["reason"].lower()

    received: list[dict[str, Any]] = []
    with live_http_server(_cloud_app(received=received)) as cloud_url:
        cloud_approved = kernel_service.validate_safety_gate_action(
            session_id=session_id,
            action_type="execute_command",
            action_payload={"target": "host", "command": "deploy", "parameters": {"suffix": suffix}},
            risk_level="high",
            execution_mode="real",
            cloud_audit_config={
                "endpoint": f"{cloud_url}/v1/decide",
                "api_key": API_KEY,
                "api_secret": API_SECRET,
                "timeout_seconds": 2,
            },
        )
    assert cloud_approved["status"] == "allowed"
    assert cloud_approved["execution_allowed"] is True
    assert cloud_approved["cloud_decision"]["status"] == "approved"
    assert received[0]["signature"] == received[0]["expected_signature"]
    assert received[0]["payload"]["action_payload"]["command"] == "deploy"

    entries = kernel_service.get_transcript(session_id, limit=400)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G8"}
    assert {"g8_safety_gate_action_validated", "g8_safety_gate_action_confirmed"} <= event_types


def test_g8_safety_gate_api_requests_validate_query_confirm_and_cloud_audit_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g8-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)
    received: list[dict[str, Any]] = []

    with live_http_server(_cloud_app(received=received)) as cloud_url, live_http_server(app) as base_url:
        alias_response = requests.post(
            f"{base_url}/api/web/runtime/safety-gate/actions",
            json={
                "session_id": session_id,
                "action_type": "rm",
                "action_payload": {"target": f"/tmp/g8-api-{suffix}", "parameters": {"force": True}},
                "risk_level": "high",
                "execution_mode": "dry_run",
            },
            timeout=20,
        )
        assert alias_response.status_code == 200, alias_response.text
        alias_blocked = alias_response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/safety-gate/decisions/{alias_blocked['decision_id']}",
            params={"session_id": session_id},
            timeout=20,
        )
        pending_response = requests.post(
            f"{base_url}/api/web/runtime/safety-gate/actions",
            json={
                "session_id": session_id,
                "action_type": "delete_file",
                "action_payload": {"target": f"/tmp/g8-api-confirm-{suffix}", "parameters": {"recursive": False}},
                "risk_level": "high",
                "execution_mode": "dry_run",
            },
            timeout=20,
        )
        assert pending_response.status_code == 200, pending_response.text
        pending = pending_response.json()
        confirm_response = requests.post(
            f"{base_url}/api/web/runtime/safety-gate/decisions/{pending['decision_id']}/confirm",
            json={
                "session_id": session_id,
                "confirmed_by": "g8-api-operator",
                "confirmation_context": {"ticket": suffix},
            },
            timeout=20,
        )
        cloud_response = requests.post(
            f"{base_url}/api/web/runtime/safety-gate/actions",
            json={
                "session_id": session_id,
                "action_type": "execute_command",
                "action_payload": {"target": "host", "command": "deploy", "parameters": {"suffix": suffix}},
                "risk_level": "high",
                "execution_mode": "real",
                "cloud_audit_config": {
                    "endpoint": f"{cloud_url}/v1/decide",
                    "api_key": API_KEY,
                    "api_secret": API_SECRET,
                    "timeout_seconds": 2,
                },
            },
            timeout=20,
        )

    assert alias_blocked["status"] == "blocked"
    assert alias_blocked["action_type"] == "delete_file"
    assert alias_blocked["bypass_attempts"][0]["attempt_type"] == "alias_call"
    assert query_response.status_code == 200, query_response.text
    _assert_query_matches(query_response.json(), alias_blocked)

    assert pending["status"] == "requires_confirmation"
    assert confirm_response.status_code == 200, confirm_response.text
    confirmed = confirm_response.json()
    assert confirmed["status"] == "allowed"
    assert confirmed["execution_allowed"] is True
    assert confirmed["confirmed_from_decision_id"] == pending["decision_id"]

    assert cloud_response.status_code == 200, cloud_response.text
    cloud_approved = cloud_response.json()
    assert cloud_approved["status"] == "allowed"
    assert cloud_approved["execution_allowed"] is True
    assert cloud_approved["cloud_decision"]["status"] == "approved"
    assert received[0]["signature"] == received[0]["expected_signature"]
