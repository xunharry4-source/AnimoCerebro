from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import threading
import time

import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.execution.adapters import LedgerActuatorAdapter
from zentex.execution.models import ExecutionMode, ExecutionRequest
from zentex.execution.orchestrator import ExecutionOrchestrator
from zentex.execution.router import ActuationRouter, ProtocolManifest
from zentex.execution.service import ExecutionService
from zentex.safety.cloud_audit_server import CloudAuditServerConfig, create_cloud_audit_app
from zentex.safety.cloud_auditor import CloudAuditorClient, CloudAuditorConfig


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


def _execution_service(cloud_auditor: CloudAuditorClient | None = None) -> ExecutionService:
    router = ActuationRouter()
    ledger = LedgerActuatorAdapter()
    router.register_adapter(ledger)
    router.register_protocol(ProtocolManifest(protocol_id="internal_agent_contract", adapter_id=ledger.adapter_id, priority=1))
    return ExecutionService(
        orchestrator=ExecutionOrchestrator(router=router, cloud_auditor=cloud_auditor or CloudAuditorClient()),
        ledger_adapter=ledger,
    )


def test_g22_modes_preserve_no_side_effect_until_real_execution_and_receipt_is_queryable() -> None:
    suffix = unique_suffix()
    service = _execution_service()
    key = f"g22-ledger-{suffix}"

    simulated = service.execute_action(
        ExecutionRequest(
            action_type="ledger_set",
            parameters={"key": key, "value": "simulate-value"},
            execution_mode=ExecutionMode.SIMULATE,
            protocol_id="internal_agent_contract",
        )
    )
    assert simulated.status == "simulated"
    assert simulated.side_effect_committed is False
    assert service.get_ledger_value(key) is None

    dry_run = service.execute_action(
        ExecutionRequest(
            action_type="ledger_set",
            parameters={"key": key, "value": "dry-run-value"},
            execution_mode=ExecutionMode.DRY_RUN,
            protocol_id="internal_agent_contract",
        )
    )
    assert dry_run.status == "dry_run"
    assert dry_run.side_effect_committed is False
    assert service.get_ledger_value(key) is None

    real = service.execute_action(
        ExecutionRequest(
            action_type="ledger_set",
            parameters={"key": key, "value": "real-value"},
            execution_mode=ExecutionMode.REAL,
            protocol_id="internal_agent_contract",
        )
    )
    queried_receipt = service.get_receipt(real.receipt_id)
    assert queried_receipt is not None
    assert real.status == "succeeded"
    assert real.side_effect_committed is True
    assert queried_receipt.evidence_payload["after"] == "real-value"
    assert service.get_ledger_value(key) == "real-value"


def test_g22_high_risk_real_action_requires_cloud_audit_and_does_not_execute_on_unconfigured_auditor() -> None:
    service = _execution_service()
    receipt = service.execute_action(
        ExecutionRequest(
            action_type="self_modify",
            parameters={"patch": "change identity constraints"},
            execution_mode=ExecutionMode.REAL,
            risk_level="critical",
            requires_cloud_audit=True,
        )
    )

    assert receipt.status == "cloud_audit_required"
    assert receipt.side_effect_committed is False
    assert receipt.cloud_decision_status == "review_required"
    assert "Cloud auditor not configured" in str(receipt.error_message)


def test_g22_explicit_cloud_audit_requirement_rejects_unconfigured_degraded_decision_without_side_effect() -> None:
    suffix = unique_suffix()
    service = _execution_service()
    key = f"g22-cloud-required-{suffix}"

    receipt = service.execute_action(
        ExecutionRequest(
            action_type="ledger_set",
            parameters={"key": key, "value": "must-not-commit"},
            execution_mode=ExecutionMode.REAL,
            risk_level="medium",
            requires_cloud_audit=True,
            protocol_id="internal_agent_contract",
        )
    )

    assert receipt.status == "cloud_audit_required"
    assert receipt.side_effect_committed is False
    assert receipt.cloud_decision_status == "approved"
    assert receipt.evidence_payload["cloud_constraints"]["degraded_mode"] is True
    assert "degraded cloud audit decisions cannot authorize execution" in str(receipt.error_message)
    assert service.get_ledger_value(key) is None


def test_g22_real_cloud_audit_http_approval_allows_requested_real_execution_and_receipt_query() -> None:
    suffix = unique_suffix()
    api_key = f"g22-key-{suffix}"
    api_secret = f"g22-secret-{suffix}"
    cloud_app = create_cloud_audit_app(
        CloudAuditServerConfig(api_keys={api_key: api_secret}, policy_version=f"g22-policy-{suffix}")
    )
    key = f"g22-cloud-approved-{suffix}"

    with _live_http_server(cloud_app) as cloud_url:
        auditor = CloudAuditorClient(
            CloudAuditorConfig(
                endpoint=f"{cloud_url}/api/v1/sanity",
                api_key=api_key,
                api_secret=api_secret,
                timeout_seconds=3,
            )
        )
        service = _execution_service(auditor)
        receipt = service.execute_action(
            ExecutionRequest(
                action_type="ledger_set",
                parameters={"key": key, "value": {"approved_by": f"g22-policy-{suffix}"}},
                execution_mode=ExecutionMode.REAL,
                risk_level="medium",
                requires_cloud_audit=True,
                protocol_id="internal_agent_contract",
            )
        )
        queried_receipt = service.get_receipt(receipt.receipt_id)

    assert receipt.status == "succeeded"
    assert receipt.cloud_decision_status == "approved"
    assert receipt.side_effect_committed is True
    assert queried_receipt is not None
    assert queried_receipt.receipt_id == receipt.receipt_id
    assert queried_receipt.evidence_payload["after"] == {"approved_by": f"g22-policy-{suffix}"}
    assert auditor.get_request_history()[0].action_type == "ledger_set"
    assert auditor.get_decision_history()[0].policy_version == f"g22-policy-{suffix}"
    assert service.get_ledger_value(key) == {"approved_by": f"g22-policy-{suffix}"}


def test_g22_unregistered_protocol_returns_failed_receipt_and_does_not_commit_side_effect() -> None:
    suffix = unique_suffix()
    service = _execution_service()
    key = f"g22-missing-protocol-{suffix}"

    receipt = service.execute_action(
        ExecutionRequest(
            action_type="ledger_set",
            parameters={"key": key, "value": "must-not-commit"},
            execution_mode=ExecutionMode.REAL,
            risk_level="low",
            protocol_id="host_adapter_http",
        )
    )
    queried_receipt = service.get_receipt(receipt.receipt_id)

    assert queried_receipt is not None
    assert receipt.status == "failed"
    assert receipt.side_effect_committed is False
    assert receipt.evidence_payload["error_type"] == "KeyError"
    assert "Protocol host_adapter_http is not registered" in str(receipt.error_message)
    assert service.get_ledger_value(key) is None


def test_g22_execution_api_uses_requests_and_read_after_write_checks_ledger_and_receipt(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.execution_service = _execution_service()
    key = f"g22-api-ledger-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        execute_response = requests.post(
            f"{base_url}/api/web/execution/actions",
            json={
                "action_type": "ledger_set",
                "parameters": {"key": key, "value": {"suffix": suffix, "committed": True}},
                "execution_mode": "real",
                "risk_level": "low",
                "protocol_id": "internal_agent_contract",
            },
            timeout=10,
        )
        assert execute_response.status_code == 200
        receipt = execute_response.json()
        receipt_response = requests.get(f"{base_url}/api/web/execution/receipts/{receipt['receipt_id']}", timeout=10)
        ledger_response = requests.get(f"{base_url}/api/web/execution/ledger/{key}", timeout=10)

    assert receipt["status"] == "succeeded"
    assert receipt["side_effect_committed"] is True
    assert receipt_response.status_code == 200
    assert receipt_response.json()["receipt_id"] == receipt["receipt_id"]
    assert receipt_response.json()["evidence_payload"]["after"] == {"suffix": suffix, "committed": True}
    assert ledger_response.status_code == 200
    assert ledger_response.json()["value"] == {"suffix": suffix, "committed": True}
