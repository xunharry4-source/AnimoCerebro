from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import socket
import socketserver
import threading
from typing import Any
from uuid import uuid4

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.autonomy.autonomous_loop import AutonomousControlLoop, Stimulus
from zentex.core.i18n import I18nLocaleError, render_cli_translation, translate
from zentex.llm.model_provider_runtime import ModelProviderRuntime, ProviderEndpointConfig
from zentex.memory.managed_memory import ManagedMemoryRecord, SQLiteManagedMemoryStore
from zentex.safety.cloud_audit_server import CloudAuditServerConfig, create_cloud_audit_app
from zentex.safety.cloud_auditor import CloudAuditorClient, CloudAuditorConfig
from zentex.safety.notifications import (
    EmergencyNotificationSystem,
    NotificationChannelProfile,
    NotificationReceiptStore,
    RiskNotificationEvent,
)


@contextmanager
def _real_model_provider() -> Iterator[tuple[str, str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received.append({"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")})
            body = json.dumps({"ok": True, "detail": "local live provider healthy"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            received.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "payload": payload,
                }
            )
            if self.headers.get("Authorization") != "Bearer g28-key":
                self.send_response(401)
                self.end_headers()
                return
            if payload.get("prompt") == "return invalid json":
                body = json.dumps({"output_text": "not-json"}).encode("utf-8")
            elif payload.get("prompt") == "return empty":
                body = json.dumps({"output_text": ""}).encode("utf-8")
            else:
                body = json.dumps({"json": {"role": "risk_supervisor", "goal": payload["context"]["goal"]}}).encode("utf-8")
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
        base = f"http://{host}:{port}"
        yield f"{base}/generate", f"{base}/healthz", received
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def _real_webhook_server(status: int = 200) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            received.append(
                {
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "payload": json.loads(self.rfile.read(length).decode("utf-8")),
                }
            )
            self.send_response(status)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}/hook", received
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def _real_smtp_server() -> Iterator[tuple[str, list[str]]]:
    messages: list[str] = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            self.wfile.write(b"220 localhost\r\n")
            data_lines: list[str] = []
            in_data = False
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if in_data:
                    if text == ".":
                        messages.append("\n".join(data_lines))
                        data_lines.clear()
                        in_data = False
                        self.wfile.write(b"250 queued\r\n")
                    else:
                        data_lines.append(text)
                    continue
                command = text.upper()
                if command.startswith("DATA"):
                    in_data = True
                    self.wfile.write(b"354 end with dot\r\n")
                elif command.startswith("QUIT"):
                    self.wfile.write(b"221 bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 ok\r\n")

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        host, port = server.server_address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"smtp://{host}:{port}/supervisor@example.local", messages
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_g27_i18n_catalog_and_cli_locale_are_strict_and_bilingual() -> None:
    zh = translate("system.health", locale="zh-CN", params={"status": "正常"})
    en = render_cli_translation(["--locale", "en", "--key", "system.health", "--param", "status=healthy"])

    assert zh.message == "系统健康：正常"
    assert en.locale == "en-US"
    assert en.message == "System health: healthy"
    with pytest.raises(I18nLocaleError):
        translate("system.health", locale="fr-FR", params={"status": "ok"})


def test_g27_i18n_api_uses_requests_and_returns_exact_translation(acceptance_app: FastAPI) -> None:
    with live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/i18n/translate",
            json={"message_key": "notification.sent", "locale": "en", "params": {"event_id": "evt-g27"}},
            timeout=10,
        )
        missing = requests.post(
            f"{base_url}/api/web/i18n/translate",
            json={"message_key": "unknown.key", "locale": "en", "params": {}},
            timeout=10,
        )

    assert response.status_code == 200
    assert response.json() == {
        "locale": "en-US",
        "message_key": "notification.sent",
        "message": "Notification sent: evt-g27",
    }
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "missing_catalog_entry"


def test_g28_model_provider_runtime_real_http_fail_closed_health_and_call_queries(acceptance_app: FastAPI) -> None:
    with _real_model_provider() as (endpoint, health_endpoint, received):
        runtime = ModelProviderRuntime()
        config = runtime.register_provider(
            ProviderEndpointConfig(
                provider_id="g28-provider",
                provider_name="local-real-provider",
                endpoint=endpoint,
                health_endpoint=health_endpoint,
                api_key="g28-key",
                model="g28-json-model",
            )
        )
        health_first = runtime.health_probe(config.provider_id)
        health_cached = runtime.health_probe(config.provider_id)
        record = runtime.generate_json(
            config.provider_id,
            prompt="infer role",
            context={"goal": "protect audit boundary"},
            caller_context={"source_module": "g28-test", "invocation_phase": "role_inference"},
        )

        acceptance_app.state.model_provider_runtime = ModelProviderRuntime()
        with live_http_server(acceptance_app) as base_url:
            register_response = requests.post(
                f"{base_url}/api/web/model-provider-runtime/providers",
                json={
                    "provider_id": "g28-api-provider",
                    "provider_name": "local-real-provider",
                    "endpoint": endpoint,
                    "health_endpoint": health_endpoint,
                    "api_key": "g28-key",
                    "model": "g28-json-model",
                },
                timeout=10,
            )
            api_call = requests.post(
                f"{base_url}/api/web/model-provider-runtime/providers/g28-api-provider/generate-json",
                json={
                    "prompt": "infer role api",
                    "context": {"goal": "query api output"},
                    "caller_context": {"source_module": "g28-api", "invocation_phase": "goal_generation"},
                },
                timeout=10,
            )
            calls = requests.get(f"{base_url}/api/web/model-provider-runtime/calls", timeout=10)

    assert health_first.available is True
    assert health_cached.cached is True
    assert record.output == {"role": "risk_supervisor", "goal": "protect audit boundary"}
    assert runtime.get_call(record.call_id).output == record.output
    assert received[0]["auth"] == "Bearer g28-key"
    assert register_response.status_code == 200
    assert api_call.status_code == 200
    assert api_call.json()["output"] == {"role": "risk_supervisor", "goal": "query api output"}
    assert calls.status_code == 200
    assert calls.json()[0]["call_id"] == api_call.json()["call_id"]


def test_g28_invalid_provider_output_is_classified_without_fallback() -> None:
    with _real_model_provider() as (endpoint, health_endpoint, _received):
        runtime = ModelProviderRuntime()
        runtime.register_provider(
            ProviderEndpointConfig(
                provider_id="g28-invalid",
                provider_name="local-real-provider",
                endpoint=endpoint,
                health_endpoint=health_endpoint,
                api_key="g28-key",
                model="g28-json-model",
            )
        )
        with pytest.raises(Exception):
            runtime.generate_json(
                "g28-invalid",
                prompt="return invalid json",
                context={"goal": "must not fallback"},
                caller_context={"source_module": "g28-test"},
            )
        failed = runtime.list_calls()[0]

    assert failed.status == "failed"
    assert failed.classification == "invalid_json"
    assert failed.output is None


def test_g29_sqlite_managed_memory_real_write_query_governance_and_api(acceptance_app: FastAPI, tmp_path) -> None:
    store = SQLiteManagedMemoryStore(tmp_path / "g29-memory.sqlite3")
    record = store.remember(
        ManagedMemoryRecord(
            trace_id="trace-g29",
            request_id="request-g29",
            source_event_id="event-g29",
            memory_type="lesson",
            topic="cloud-audit",
            role="supervisor",
            risk_level="high",
            content="Cloud audit rejection must notify the supervisor and block self modification.",
        )
    )
    query = store.query(query_text="audit notify supervisor", topic="cloud-audit", risk_level="high")
    updated = store.update_governance(record.memory_id, visibility="hidden", trust_level="suspect", reason="operator challenged evidence")
    hidden_query = store.query(query_text="audit notify supervisor", topic="cloud-audit", risk_level="high")

    acceptance_app.state.managed_memory_store = SQLiteManagedMemoryStore(tmp_path / "g29-api.sqlite3")
    with live_http_server(acceptance_app) as base_url:
        create_response = requests.post(
            f"{base_url}/api/web/managed-memory/records",
            json={
                "trace_id": "trace-g29-api",
                "request_id": "request-g29-api",
                "source_event_id": "event-g29-api",
                "memory_type": "procedure",
                "topic": "notification",
                "role": "operator",
                "risk_level": "medium",
                "content": "Send webhook then query receipts before closing the incident.",
            },
            timeout=10,
        )
        memory_id = create_response.json()["memory_id"]
        query_response = requests.get(
            f"{base_url}/api/web/managed-memory/records",
            params={"query_text": "webhook receipts", "topic": "notification", "role": "operator"},
            timeout=10,
        )
        patch_response = requests.patch(
            f"{base_url}/api/web/managed-memory/records/{memory_id}/governance",
            json={"status": "archived", "reason": "verified obsolete"},
            timeout=10,
        )
        audit_response = requests.get(f"{base_url}/api/web/managed-memory/records/{memory_id}/audit", timeout=10)

    assert query[0].record.memory_id == record.memory_id
    assert "matched_terms=" in query[0].explanation
    assert updated.visibility == "hidden"
    assert hidden_query == []
    assert len(store.list_audit_events(record.memory_id)) == 2
    assert create_response.status_code == 200
    assert query_response.json()[0]["record"]["memory_id"] == memory_id
    assert patch_response.json()["status"] == "archived"
    assert [row["action"] for row in audit_response.json()] == ["remember", "governance_update"]


def test_g30_cloud_audit_server_real_http_signature_replay_persistence_and_client_verification(tmp_path) -> None:
    api_key = "g30-key"
    secret = "g30-secret"
    app = create_cloud_audit_app(
        CloudAuditServerConfig(
            api_keys={api_key: secret},
            policy_version="g30-policy-test",
            db_path=str(tmp_path / "cloud-audit.sqlite3"),
            deny_action_types=["forbidden_action"],
        )
    )
    with live_http_server(app) as base_url:
        client = CloudAuditorClient(
            CloudAuditorConfig(
                endpoint=f"{base_url}/api/v1/sanity",
                api_key=api_key,
                api_secret=secret,
                timeout_seconds=2,
            )
        )
        decision = client.audit_action("self_modify", {"patch": "risky"}, risk_level="critical", use_cache=False)
        stored = requests.get(f"{base_url}/api/v1/sanity/{decision.request_id}", timeout=10)
        original = client.get_request_history()[0]
        replay_response = requests.post(
            f"{base_url}/api/v1/sanity",
            json=original.model_dump(mode="json"),
            headers={"X-Zentex-Api-Key": api_key, "X-Zentex-Signature": original.client_signature},
            timeout=10,
        )
        bad_signature = requests.post(
            f"{base_url}/api/v1/sanity",
            json={
                "request_id": f"bad-{uuid4().hex[:8]}",
                "action_type": "self_modify",
                "action_payload": {},
                "risk_level": "low",
                "context": {},
                "brain_scope": "test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "client_signature": "",
            },
            headers={"X-Zentex-Api-Key": api_key, "X-Zentex-Signature": "hmac-sha256=bad"},
            timeout=10,
        )

    assert decision.status.value == "rejected"
    assert decision.policy_version == "g30-policy-test"
    assert client.get_degradation_history() == []
    assert stored.status_code == 200
    assert stored.json()["decision_id"] == decision.decision_id
    assert replay_response.status_code == 409
    assert replay_response.json()["detail"]["error"] == "replay_detected"
    assert bad_signature.status_code == 401
    assert bad_signature.json()["detail"]["error"] == "invalid_signature"


def test_g31a_autonomous_loop_state_machine_and_api_read_after_write(acceptance_app: FastAPI) -> None:
    loop = AutonomousControlLoop()
    stimulus = loop.ingest_stimulus(
        Stimulus(
            source="memory_trigger",
            event_type="degraded_mode_detected",
            description="model provider degraded after rate limit",
            risk_level="high",
            memory_refs=["mem-rate-limit"],
            agent_refs=["audit-agent"],
        )
    )
    report = loop.run_cycle(budget_level="normal")
    task = report.tasks[0]
    approved = loop.transition_task(task.task_id, "approve", reason="human accepted high risk follow-up")
    started = loop.transition_task(approved.task_id, "start", reason="begin supervised recovery")
    done = loop.transition_task(started.task_id, "complete", reason="receipt and memory writeback verified")

    acceptance_app.state.autonomous_control_loop = AutonomousControlLoop()
    with live_http_server(acceptance_app) as base_url:
        create_response = requests.post(
            f"{base_url}/api/web/autonomous-loop/stimuli",
            json={
                "source": "workspace_change",
                "event_type": "blocked_task_resolved",
                "description": "dependency restored",
                "risk_level": "medium",
                "memory_refs": ["mem-g31"],
                "agent_refs": [],
            },
            timeout=10,
        )
        cycle_response = requests.post(f"{base_url}/api/web/autonomous-loop/cycles", json={"budget_level": "normal"}, timeout=10)
        api_task_id = cycle_response.json()["tasks"][0]["task_id"]
        start_response = requests.post(
            f"{base_url}/api/web/autonomous-loop/tasks/{api_task_id}/transition",
            json={"action": "start", "reason": "ready to execute"},
            timeout=10,
        )
        tasks_response = requests.get(f"{base_url}/api/web/autonomous-loop/tasks", timeout=10)

    assert stimulus.stimulus_id == task.stimulus_id
    assert task.needs_confirmation is True
    assert task.collaboration_required is True
    assert report.nine_question_mapping["q8_what_should_i_do_now"] == [task.task_id]
    assert done.status == "done"
    assert any(event["action"] == "task_transition" for event in loop.list_audit_events())
    assert create_response.status_code == 200
    assert cycle_response.json()["tasks"][0]["status"] == "queued"
    assert start_response.json()["status"] == "in_progress"
    assert tasks_response.json()[0]["task_id"] == api_task_id


def test_g32_emergency_notifications_real_webhook_email_quiet_window_dead_letter_and_api(acceptance_app: FastAPI) -> None:
    with _real_webhook_server(status=200) as (webhook_endpoint, webhook_received), _real_smtp_server() as (smtp_endpoint, email_messages):
        system = EmergencyNotificationSystem(NotificationReceiptStore(), quiet_window_seconds=120)
        web = system.upsert_profile(NotificationChannelProfile(profile_id="web", channel="web", min_severity="low"))
        webhook = system.upsert_profile(
            NotificationChannelProfile(profile_id="webhook", channel="webhook", endpoint=webhook_endpoint, token="g32-token", min_severity="medium")
        )
        email = system.upsert_profile(NotificationChannelProfile(profile_id="email", channel="email", endpoint=smtp_endpoint, min_severity="high"))
        event = RiskNotificationEvent(
            event_type="cloud_audit_rejected",
            severity="high",
            description="cloud audit rejected self modification",
            suggested_actions=["approve", "reject", "open_console"],
            source_ref="decision-g32",
        )
        receipts = system.emit_event(event)
        suppressed = system.emit_event(event.model_copy(update={"event_id": "risk-event-quiet"}))
        action = system.quick_action(event.event_id, "reject", actor="supervisor")

        with _real_webhook_server(status=500) as (bad_webhook_endpoint, _bad_received):
            failing_system = EmergencyNotificationSystem(NotificationReceiptStore(), quiet_window_seconds=0)
            failing_system.upsert_profile(
                NotificationChannelProfile(profile_id="bad-webhook", channel="webhook", endpoint=bad_webhook_endpoint, min_severity="medium", max_retries=1)
            )
            dead_letter = failing_system.emit_event(
                RiskNotificationEvent(
                    event_type="degraded_mode",
                    severity="medium",
                    description="provider entered degraded mode",
                    source_ref="llm-g32",
                )
            )

        acceptance_app.state.emergency_notification_system = EmergencyNotificationSystem(NotificationReceiptStore(), quiet_window_seconds=120)
        with live_http_server(acceptance_app) as base_url:
            profile_response = requests.post(
                f"{base_url}/api/web/notifications/profiles",
                json={"profile_id": "api-web", "channel": "web", "min_severity": "low"},
                timeout=10,
            )
            event_response = requests.post(
                f"{base_url}/api/web/notifications/events",
                json={
                    "event_type": "circuit_breaker_open",
                    "severity": "low",
                    "description": "runtime circuit breaker opened",
                    "suggested_actions": ["open_console"],
                    "source_ref": "breaker-g32",
                },
                timeout=10,
            )
            event_id = event_response.json()[0]["event_id"]
            inbox_response = requests.get(f"{base_url}/api/web/notifications/inbox", timeout=10)
            action_response = requests.post(
                f"{base_url}/api/web/notifications/events/{event_id}/actions",
                json={"action": "open_console", "actor": "api-user"},
                timeout=10,
            )
            receipts_response = requests.get(f"{base_url}/api/web/notifications/receipts", params={"event_id": event_id}, timeout=10)

    assert {receipt.channel for receipt in receipts} == {"web", "webhook", "email"}
    assert all(receipt.status == "sent" for receipt in receipts)
    assert webhook_received[0]["auth"] == "Bearer g32-token"
    assert webhook_received[0]["payload"]["event"]["event_id"] == event.event_id
    assert "cloud audit rejected self modification" in email_messages[0]
    assert suppressed[0].status == "suppressed"
    assert action.result == "reject_recorded"
    assert dead_letter[0].status == "dead_letter"
    assert dead_letter[0].attempts == 2
    assert profile_response.status_code == 200
    assert event_response.json()[0]["channel"] == "web"
    assert inbox_response.json()[0]["event"]["source_ref"] == "breaker-g32"
    assert action_response.json()["result"] == "console_opened"
    assert receipts_response.json()[0]["event_id"] == event_id
