from __future__ import annotations

import requests
from fastapi import FastAPI, Header, HTTPException

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.agents.governance import (
    RoleAgentGovernanceManager,
    RoleOverrideRequest,
    TaskRoleInferenceRequest,
)
from zentex.llm.model_provider_runtime import ModelProviderRuntime, ProviderEndpointConfig


def _agent_app(
    *,
    agent_id: str,
    token: str,
    capability: str,
    permission: str,
    boundary: str,
    status_value: str = "online",
    omit_receipt_id: bool = False,
) -> FastAPI:
    app = FastAPI()
    receipts: dict[str, dict] = {}

    capability_row = {
        "name": capability,
        "boundaries": [boundary],
        "execution_domains": ["analysis"],
        "permission_scope": [permission],
        "confidence": 0.91,
    }

    @app.post("/handshake")
    def handshake(payload: dict, authorization: str = Header(default="")) -> dict:
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="bad token")
        if payload["agent_id"] != agent_id:
            raise HTTPException(status_code=409, detail="agent id mismatch")
        return {"agent_id": agent_id, "version": "1.0.0", "capabilities": [capability_row]}

    @app.get("/status")
    def status() -> dict:
        return {"agent_id": agent_id, "status": status_value}

    @app.post("/tasks")
    def tasks(payload: dict, authorization: str = Header(default="")) -> dict:
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="bad token")
        receipt_id = f"receipt-{payload['task_id']}"
        receipts[receipt_id] = {
            "receipt_id": receipt_id,
            "task_id": payload["task_id"],
            "status": "completed",
            "accepted_capability": capability,
            "objective": payload["objective"],
        }
        if omit_receipt_id:
            return {"task_id": payload["task_id"], "status": "accepted_without_receipt"}
        return receipts[receipt_id]

    @app.get("/receipts/{receipt_id}")
    def receipt(receipt_id: str) -> dict:
        if receipt_id not in receipts:
            raise HTTPException(status_code=404, detail="missing receipt")
        return receipts[receipt_id]

    return app


def _doc_app() -> FastAPI:
    app = FastAPI()

    @app.get("/agent-doc")
    def agent_doc() -> str:
        return (
            "Agent doc: supports financial-review over analysis domain. "
            "Permission scope is finance.read. Boundary is read-only financial reports. "
            "Use /handshake, /tasks, /status, /receipts/{receipt_id}."
        )

    return app


def _provider_app(*, expected_token: str) -> FastAPI:
    app = FastAPI()
    app.state.calls = []

    @app.post("/llm")
    def llm(payload: dict, authorization: str = Header(default="")) -> dict:
        if authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="bad provider token")
        app.state.calls.append(payload)
        document_text = payload["context"]["document_text"]
        assert "financial-review" in document_text
        return {
            "json": {
                "capabilities": [
                    {
                        "name": "financial-review",
                        "boundaries": ["read-only financial reports"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.read"],
                        "confidence": 0.94,
                    }
                ],
                "protocol": {
                    "handshake_path": "/handshake",
                    "capabilities_path": "/capabilities",
                    "task_path": "/tasks",
                    "status_path": "/status",
                    "receipt_path_template": "/receipts/{receipt_id}",
                },
                "limitations": ["no write operations"],
                "interaction_summary": "Use authenticated JSON calls for financial review tasks.",
            }
        }

    return app


def test_g35_role_override_requires_confirmation_and_keeps_identity_role() -> None:
    manager = RoleAgentGovernanceManager(identity_role="Zentex continuity identity")
    try:
        manager.override_active_role(
            RoleOverrideRequest(
                new_active_role="financial auditor",
                role_description="Audit financial reports.",
                reason="user requested audit mode",
                operator_id="operator-a",
                confirmation_phrase="wrong",
            )
        )
    except ValueError as exc:
        assert "CONFIRM_ROLE_OVERRIDE" in str(exc)
    else:
        raise AssertionError("role override without confirmation must fail")

    state = manager.override_active_role(
        RoleOverrideRequest(
            new_active_role="financial auditor",
            role_description="Audit financial reports.",
            reason="user requested audit mode",
            operator_id="operator-a",
            confirmation_phrase="CONFIRM_ROLE_OVERRIDE",
        )
    )
    inferred = manager.infer_task_role(
        TaskRoleInferenceRequest(
            task_id="task-g35-role",
            objective="review reporting risk",
            required_capabilities=["finance"],
            risk_level="high",
        )
    )

    assert state.identity_role == "Zentex continuity identity"
    assert state.active_role == "financial auditor"
    assert state.recompute_required is True
    assert inferred.task_role == "risk-bounded task reviewer"
    assert [event.action for event in manager.list_audit_events()] == [
        "active_role_override",
        "task_role_inferred",
    ]


def test_g35_api_uses_requests_for_doc_llm_handshake_schedule_task_receipt_and_conflict(
    acceptance_app: FastAPI,
) -> None:
    provider_app = _provider_app(expected_token="provider-token")
    doc_app = _doc_app()
    primary_agent = _agent_app(
        agent_id="agent-finance-a",
        token="agent-token-a",
        capability="financial-review",
        permission="finance.read",
        boundary="read-only financial reports",
    )
    conflict_agent = _agent_app(
        agent_id="agent-finance-b",
        token="agent-token-b",
        capability="financial-review",
        permission="finance.write",
        boundary="can propose write actions",
    )

    runtime = ModelProviderRuntime()
    with (
        live_http_server(provider_app) as provider_url,
        live_http_server(doc_app) as doc_url,
        live_http_server(primary_agent) as primary_url,
        live_http_server(conflict_agent) as conflict_url,
    ):
        provider_config = runtime.register_provider(
            ProviderEndpointConfig(
                provider_id="g35-provider",
                provider_name="g35-live-doc-understanding",
                endpoint=f"{provider_url}/llm",
                api_key="provider-token",
                model="g35-doc-model",
            )
        )
        acceptance_app.state.role_agent_governance_manager = RoleAgentGovernanceManager(
            model_provider_runtime=runtime,
            default_llm_provider_id=provider_config.provider_id,
        )
        with live_http_server(acceptance_app) as base_url:
            role_before = requests.get(f"{base_url}/api/web/role-agent-governance/roles", timeout=10)
            override_bad = requests.post(
                f"{base_url}/api/web/role-agent-governance/roles/active-override",
                json={
                    "new_active_role": "financial auditor",
                    "role_description": "Audit financial risk.",
                    "reason": "operator selected audit role",
                    "operator_id": "operator-web",
                    "confirmation_phrase": "bad",
                },
                timeout=10,
            )
            override_ok = requests.post(
                f"{base_url}/api/web/role-agent-governance/roles/active-override",
                json={
                    "new_active_role": "financial auditor",
                    "role_description": "Audit financial risk.",
                    "reason": "operator selected audit role",
                    "operator_id": "operator-web",
                    "confirmation_phrase": "CONFIRM_ROLE_OVERRIDE",
                },
                timeout=10,
            )
            register_primary = requests.post(
                f"{base_url}/api/web/role-agent-governance/agents/register",
                json={
                    "agent_id": "agent-finance-a",
                    "display_name": "Finance Review Agent A",
                    "version": "1.0.0",
                    "endpoint": primary_url,
                    "auth_token": "agent-token-a",
                    "scope": ["finance.read"],
                    "requested_trust_level": "trusted",
                    "document_url": f"{doc_url}/agent-doc",
                    "operator_id": "operator-web",
                },
                timeout=10,
            )
            register_conflict = requests.post(
                f"{base_url}/api/web/role-agent-governance/agents/register",
                json={
                    "agent_id": "agent-finance-b",
                    "display_name": "Finance Review Agent B",
                    "version": "1.0.0",
                    "endpoint": conflict_url,
                    "auth_token": "agent-token-b",
                    "scope": ["finance.write"],
                    "requested_trust_level": "limited",
                    "capabilities": [
                        {
                            "name": "financial-review",
                            "boundaries": ["can propose write actions"],
                            "execution_domains": ["analysis"],
                            "permission_scope": ["finance.write"],
                            "confidence": 0.9,
                        }
                    ],
                    "operator_id": "operator-web",
                },
                timeout=10,
            )
            agents_response = requests.get(f"{base_url}/api/web/role-agent-governance/agents", timeout=10)
            monitored = requests.post(
                f"{base_url}/api/web/role-agent-governance/agents/agent-finance-a/monitor",
                timeout=10,
            )
            schedule_response = requests.post(
                f"{base_url}/api/web/role-agent-governance/agents/schedule",
                json={
                    "task_id": "task-g35-finance",
                    "objective": "Review finance report for risk.",
                    "required_capabilities": ["financial-review"],
                    "required_permissions": ["finance.read"],
                    "execution_domain": "analysis",
                    "priority": 8,
                    "risk_level": "high",
                    "payload": {"report_id": "report-001"},
                },
                timeout=10,
            )
            receipt_response = requests.post(
                f"{base_url}/api/web/role-agent-governance/agents/agent-finance-a/test-task",
                json={
                    "task_id": "task-g35-finance",
                    "objective": "Review finance report for risk.",
                    "required_capabilities": ["financial-review"],
                    "required_permissions": ["finance.read"],
                    "execution_domain": "analysis",
                    "priority": 8,
                    "risk_level": "high",
                    "payload": {"report_id": "report-001"},
                },
                timeout=10,
            )
            receipt_id = receipt_response.json()["receipt_id"]
            receipt_query = requests.get(
                f"{base_url}/api/web/role-agent-governance/agents/agent-finance-a/receipts/{receipt_id}",
                timeout=10,
            )
            conflicts_response = requests.get(f"{base_url}/api/web/role-agent-governance/conflicts", timeout=10)
            outcome_response = requests.post(
                f"{base_url}/api/web/role-agent-governance/outcomes",
                json={
                    "agent_id": "agent-finance-a",
                    "task_id": "task-g35-finance",
                    "result_status": "succeeded",
                    "score": 0.93,
                    "evidence": {"receipt_id": receipt_id, "verified": True},
                },
                timeout=10,
            )
            outcomes_query = requests.get(
                f"{base_url}/api/web/role-agent-governance/outcomes",
                params={"agent_id": "agent-finance-a"},
                timeout=10,
            )
            interface_response = requests.get(
                f"{base_url}/api/web/role-agent-governance/external-interface",
                timeout=10,
            )
            audit_response = requests.get(f"{base_url}/api/web/role-agent-governance/audit", timeout=10)

    assert role_before.status_code == 200
    assert role_before.json()["identity_role"] == "Zentex Agent"
    assert override_bad.status_code == 400
    assert override_bad.json()["detail"]["error"] == "role_override_failed"
    assert override_ok.status_code == 200
    assert override_ok.json()["identity_role"] == "Zentex Agent"
    assert override_ok.json()["active_role"] == "financial auditor"
    assert register_primary.status_code == 200
    primary_payload = register_primary.json()
    assert primary_payload["trust_level"] == "trusted"
    assert primary_payload["status"] == "online"
    assert primary_payload["handshake"]["verified"] is True
    assert primary_payload["document_profile"]["provider_call_id"].startswith("llm-call-")
    assert primary_payload["document_profile"]["capabilities"][0]["name"] == "financial-review"
    assert register_conflict.status_code == 200
    assert agents_response.status_code == 200
    assert {row["agent_id"] for row in agents_response.json()} == {"agent-finance-a", "agent-finance-b"}
    assert monitored.json()["status"] == "online"
    schedule = schedule_response.json()
    assert schedule["status"] == "assigned"
    assert schedule["selected_agent_id"] == "agent-finance-a"
    assert any(row["agent_id"] == "agent-finance-b" for row in schedule["blocked_candidates"])
    assert receipt_response.status_code == 200
    assert receipt_response.json()["status"] == "completed"
    assert receipt_query.json()["verified_remote_receipt"]["status"] == "completed"
    assert conflicts_response.json()[0]["capability"] == "financial-review"
    assert conflicts_response.json()[0]["conflict_type"] == "capability_boundary_or_permission_mismatch"
    assert outcome_response.status_code == 200
    assert outcomes_query.json()[0]["evidence"]["receipt_id"] == receipt_id
    assert interface_response.json()["required_auth"] == "Authorization: Bearer <agent token>"
    assert [row["action"] for row in audit_response.json()] == [
        "active_role_override",
        "agent_registered",
        "agent_registered",
        "agent_status_updated",
        "agent_scheduled",
        "agent_test_task_submitted",
        "agent_receipt_verified",
        "collaboration_outcome_recorded",
    ]


def test_g35_api_rejects_agent_document_without_active_llm_provider(acceptance_app: FastAPI) -> None:
    acceptance_app.state.role_agent_governance_manager = RoleAgentGovernanceManager()
    with live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "agent-doc-required",
                "display_name": "Doc Required Agent",
                "version": "1.0.0",
                "endpoint": "http://127.0.0.1:9",
                "auth_token": "agent-token",
                "scope": ["analysis.read"],
                "requested_trust_level": "limited",
                "document_url": "http://127.0.0.1:9/agent-doc",
                "operator_id": "operator-web",
            },
            timeout=10,
        )
        agents_response = requests.get(f"{base_url}/api/web/role-agent-governance/agents", timeout=10)

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "agent_registration_failed"
    assert "ModelProviderRuntime" in response.json()["detail"]["message"]
    assert agents_response.json() == []


def test_g35_feature62_api_requests_diagnostics_enforcement_fault_matrix_and_query_checks(
    acceptance_app: FastAPI,
) -> None:
    acceptance_app.state.role_agent_governance_manager = RoleAgentGovernanceManager()
    trusted_agent = _agent_app(
        agent_id="feature62-trusted",
        token="trusted-token",
        capability="financial-review",
        permission="finance.read",
        boundary="read-only financial reports",
    )
    conflict_agent = _agent_app(
        agent_id="feature62-conflict",
        token="conflict-token",
        capability="financial-review",
        permission="finance.write",
        boundary="write-capable finance reports",
    )
    over_scope_agent = _agent_app(
        agent_id="feature62-overscope",
        token="overscope-token",
        capability="financial-review",
        permission="finance.admin",
        boundary="admin finance scope",
    )
    offline_agent = _agent_app(
        agent_id="feature62-offline",
        token="offline-token",
        capability="ops-review",
        permission="ops.read",
        boundary="read-only ops reports",
        status_value="offline",
    )
    missing_ack_agent = _agent_app(
        agent_id="feature62-missing-ack",
        token="ack-token",
        capability="ack-review",
        permission="ack.read",
        boundary="ack receipt validation",
        omit_receipt_id=True,
    )
    false_capability_agent = _agent_app(
        agent_id="feature62-false-capability",
        token="false-token",
        capability="financial-review",
        permission="finance.read",
        boundary="read-only financial reports",
    )

    with (
        live_http_server(trusted_agent) as trusted_url,
        live_http_server(conflict_agent) as conflict_url,
        live_http_server(over_scope_agent) as overscope_url,
        live_http_server(offline_agent) as offline_url,
        live_http_server(missing_ack_agent) as ack_url,
        live_http_server(false_capability_agent) as false_capability_url,
        live_http_server(acceptance_app) as base_url,
    ):
        register_trusted = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-trusted",
                "display_name": "Feature 62 Trusted Agent",
                "version": "1.0.0",
                "endpoint": trusted_url,
                "auth_token": "trusted-token",
                "scope": ["finance.read"],
                "requested_trust_level": "trusted",
                "capabilities": [
                    {
                        "name": "financial-review",
                        "boundaries": ["read-only financial reports"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.read"],
                        "confidence": 0.95,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        register_conflict = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-conflict",
                "display_name": "Feature 62 Conflict Agent",
                "version": "1.0.0",
                "endpoint": conflict_url,
                "auth_token": "conflict-token",
                "scope": ["finance.write"],
                "requested_trust_level": "limited",
                "capabilities": [
                    {
                        "name": "financial-review",
                        "boundaries": ["write-capable finance reports"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.write"],
                        "confidence": 0.91,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        register_overscope = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-overscope",
                "display_name": "Feature 62 Overscope Agent",
                "version": "1.0.0",
                "endpoint": overscope_url,
                "auth_token": "overscope-token",
                "scope": [],
                "requested_trust_level": "limited",
                "capabilities": [
                    {
                        "name": "financial-review",
                        "boundaries": ["admin finance scope"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.admin"],
                        "confidence": 0.88,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        register_offline = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-offline",
                "display_name": "Feature 62 Offline Agent",
                "version": "1.0.0",
                "endpoint": offline_url,
                "auth_token": "offline-token",
                "scope": ["ops.read"],
                "requested_trust_level": "limited",
                "capabilities": [
                    {
                        "name": "ops-review",
                        "boundaries": ["read-only ops reports"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["ops.read"],
                        "confidence": 0.8,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        register_ack = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-missing-ack",
                "display_name": "Feature 62 Missing Ack Agent",
                "version": "1.0.0",
                "endpoint": ack_url,
                "auth_token": "ack-token",
                "scope": ["ack.read"],
                "requested_trust_level": "limited",
                "capabilities": [
                    {
                        "name": "ack-review",
                        "boundaries": ["ack receipt validation"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["ack.read"],
                        "confidence": 0.8,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        duplicate_register = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-trusted",
                "display_name": "Duplicate Trusted Agent",
                "version": "1.0.0",
                "endpoint": trusted_url,
                "auth_token": "trusted-token",
                "scope": ["finance.read"],
                "requested_trust_level": "trusted",
                "capabilities": [
                    {
                        "name": "financial-review",
                        "boundaries": ["read-only financial reports"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.read"],
                        "confidence": 0.95,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        false_capability_register = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/register",
            json={
                "agent_id": "feature62-false-capability",
                "display_name": "Feature 62 False Capability Agent",
                "version": "1.0.0",
                "endpoint": false_capability_url,
                "auth_token": "false-token",
                "scope": ["finance.read"],
                "requested_trust_level": "limited",
                "capabilities": [
                    {
                        "name": "invented-capability",
                        "boundaries": ["fake"],
                        "execution_domains": ["analysis"],
                        "permission_scope": ["finance.read"],
                        "confidence": 0.99,
                    }
                ],
                "operator_id": "feature62",
            },
            timeout=10,
        )
        monitor_offline = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-offline/monitor",
            timeout=10,
        )
        schedule_offline = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/schedule",
            json={
                "task_id": "feature62-offline-task",
                "objective": "Route ops review.",
                "required_capabilities": ["ops-review"],
                "required_permissions": ["ops.read"],
                "execution_domain": "analysis",
                "priority": 5,
                "risk_level": "medium",
            },
            timeout=10,
        )
        ack_loss = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-missing-ack/test-task",
            json={
                "task_id": "feature62-ack-task",
                "objective": "Trigger missing receipt.",
                "required_capabilities": ["ack-review"],
                "required_permissions": ["ack.read"],
                "execution_domain": "analysis",
                "priority": 5,
                "risk_level": "medium",
            },
            timeout=10,
        )
        schedule_trusted = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/schedule",
            json={
                "task_id": "feature62-trusted-task",
                "objective": "Route trusted finance review.",
                "required_capabilities": ["financial-review"],
                "required_permissions": ["finance.read"],
                "execution_domain": "analysis",
                "priority": 8,
                "risk_level": "high",
            },
            timeout=10,
        )
        trusted_task = requests.post(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-trusted/test-task",
            json={
                "task_id": "feature62-trusted-task",
                "objective": "Route trusted finance review.",
                "required_capabilities": ["financial-review"],
                "required_permissions": ["finance.read"],
                "execution_domain": "analysis",
                "priority": 8,
                "risk_level": "high",
            },
            timeout=10,
        )
        trusted_receipt = requests.get(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-trusted/receipts/{trusted_task.json()['receipt_id']}",
            timeout=10,
        )
        for index in range(2):
            failed_outcome = requests.post(
                f"{base_url}/api/web/role-agent-governance/outcomes",
                json={
                    "agent_id": "feature62-trusted",
                    "task_id": f"feature62-drift-{index}",
                    "result_status": "failed",
                    "score": 0.2,
                    "evidence": {"reason": "real failed outcome evidence"},
                },
                timeout=10,
            )
            assert failed_outcome.status_code == 200, failed_outcome.text
        diagnostics = requests.get(
            f"{base_url}/api/web/role-agent-governance/closure/diagnostics",
            params={"heartbeat_freshness_seconds": 300},
            timeout=10,
        )
        enforce = requests.post(
            f"{base_url}/api/web/role-agent-governance/closure/enforce",
            params={"heartbeat_freshness_seconds": 300},
            timeout=10,
        )
        fault = requests.post(
            f"{base_url}/api/web/role-agent-governance/closure/fault-injection",
            params={"heartbeat_freshness_seconds": 300},
            timeout=10,
        )
        trusted_after = requests.get(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-trusted",
            timeout=10,
        )
        overscope_after = requests.get(
            f"{base_url}/api/web/role-agent-governance/agents/feature62-overscope",
            timeout=10,
        )
        agents_after = requests.get(f"{base_url}/api/web/role-agent-governance/agents", timeout=10)
        audit = requests.get(f"{base_url}/api/web/role-agent-governance/audit", timeout=10)

    for response in [register_trusted, register_conflict, register_overscope, register_offline, register_ack]:
        assert response.status_code == 200, response.text
    assert register_overscope.json()["trust_level"] == "pending"
    assert duplicate_register.status_code == 400
    assert "already registered" in duplicate_register.json()["detail"]["message"]
    assert false_capability_register.status_code == 400
    assert "do not match" in false_capability_register.json()["detail"]["message"]
    assert monitor_offline.status_code == 200
    assert monitor_offline.json()["status"] == "offline"
    assert schedule_offline.status_code == 200
    assert schedule_offline.json()["status"] == "blocked"
    offline_block = [
        row for row in schedule_offline.json()["blocked_candidates"]
        if row["agent_id"] == "feature62-offline"
    ]
    assert offline_block and offline_block[0]["reasons"] == ["status:offline"]
    assert ack_loss.status_code == 409
    assert "missing receipt_id" in ack_loss.json()["detail"]["message"]
    assert schedule_trusted.status_code == 200
    assert schedule_trusted.json()["status"] == "assigned"
    assert schedule_trusted.json()["selected_agent_id"] == "feature62-trusted"
    assert trusted_task.status_code == 200
    assert trusted_task.json()["receipt_id"] == "receipt-feature62-trusted-task"
    assert trusted_receipt.status_code == 200
    assert trusted_receipt.json()["verified_remote_receipt"]["status"] == "completed"

    diagnostic_payload = diagnostics.json()
    assert diagnostics.status_code == 200, diagnostics.text
    issue_types = {issue["type"] for issue in diagnostic_payload["issues"]}
    assert {"heartbeat_stale", "trust_level_drift", "scope_overreach", "capability_conflict"} <= issue_types
    assert diagnostic_payload["checks"]["capability_handshake_detection"] is True
    assert diagnostic_payload["checks"]["dispatch_evidence"] is True
    assert diagnostic_payload["metrics"]["agent_count"] == 5

    enforce_payload = enforce.json()
    assert enforce.status_code == 200, enforce.text
    actions = {(action["agent_id"], action["action"]) for action in enforce_payload["actions"]}
    assert ("feature62-trusted", "trust_downgraded") in actions
    assert ("feature62-overscope", "scope_quarantined") in actions

    assert trusted_after.json()["trust_level"] == "limited"
    assert trusted_after.json()["status"] == "degraded"
    assert overscope_after.json()["trust_level"] == "pending"
    assert overscope_after.json()["status"] == "degraded"
    assert {row["agent_id"] for row in agents_after.json()} == {
        "feature62-trusted",
        "feature62-conflict",
        "feature62-overscope",
        "feature62-offline",
        "feature62-missing-ack",
    }

    fault_payload = fault.json()
    assert fault.status_code == 200, fault.text
    assert fault_payload["passed"] is True
    assert {case["name"] for case in fault_payload["cases"]} >= {
        "heartbeat_lost_detector_ran",
        "duplicate_registration_detector_ran",
        "false_capability_detector_ran",
        "role_or_capability_conflict_detector_ran",
        "ack_loss_and_audit_detector_ran",
        "scope_boundary_detector_ran",
    }
    audit_actions = [row["action"] for row in audit.json()]
    assert "agent_test_task_failed" in audit_actions
    assert "agent_governance_closure_diagnosed" in audit_actions
    assert "agent_governance_closure_enforced" in audit_actions
    assert "agent_fault_matrix_executed" in audit_actions
