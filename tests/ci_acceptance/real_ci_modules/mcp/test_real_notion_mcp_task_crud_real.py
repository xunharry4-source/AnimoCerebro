from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.mcp.test_real_notion_mcp_emotion_registration_real import (
    _install_real_notion_mcp_service,
    _load_real_notion_case,
    _render_placeholders,
)
from zentex.agents.auth import AgentAuthService, AgentCredentialVault
from zentex.common.database import DatabaseConnection
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.service import TaskManagementService


def _notion_headers(api_key: str, notion_version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }


def _discover_parent(case: dict[str, Any], *, api_key: str, notion_version: str) -> dict[str, str]:
    explicit_database = str(case.get("crud_parent_database_id") or "").strip()
    if explicit_database:
        return {
            "kind": "database",
            "id": explicit_database.replace("-", ""),
            "title_property": str(case.get("crud_database_title_property") or "Name"),
        }

    explicit = str(case.get("crud_parent_page_id") or "").strip()
    if explicit:
        return {"kind": "page", "id": explicit.replace("-", ""), "title_property": "title"}

    query = str(case.get("crud_parent_search_query") or "").strip()
    response = requests.post(
        "https://api.notion.com/v1/search",
        headers=_notion_headers(api_key, notion_version),
        json={
            "query": query,
            "filter": {"value": "page", "property": "object"},
            "page_size": 10,
        },
        timeout=60,
    )
    assert response.status_code == 200, response.text
    for item in response.json().get("results", []):
        if item.get("object") == "page" and not item.get("archived") and not item.get("in_trash"):
            page_id = str(item.get("id") or "").strip()
            if page_id:
                return {"kind": "page", "id": page_id.replace("-", ""), "title_property": "title"}

    pytest.fail(
        "No writable Notion parent page was discoverable for the integration token. "
        "Share a parent page with the Notion integration, or add "
        "'crud_parent_page_id' to tests/ci_acceptance/real_ci_modules/mcp/"
        "real_notion_mcp_case.local.json.",
        pytrace=False,
    )


def _parse_mcp_json_text(result_payload: dict[str, Any]) -> dict[str, Any]:
    content = result_payload["data"]["content"]
    assert isinstance(content, list) and content, result_payload
    text = content[0]["text"]
    parsed = json.loads(text)
    assert isinstance(parsed, dict), parsed
    return parsed


def _page_title(page: dict[str, Any], title_property_name: str) -> str:
    title_property = page.get("properties", {}).get(title_property_name)
    title_items = title_property.get("title") if isinstance(title_property, dict) else None
    assert isinstance(title_items, list) and title_items, page
    return "".join(str(item.get("plain_text") or "") for item in title_items)


def _notion_get_page(api_key: str, notion_version: str, page_id: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_notion_headers(api_key, notion_version),
        timeout=60,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _transcript_payloads(app: FastAPI, *, trace_id: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in app.state.transcript_store.entries:
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        if trace_id and payload.get("trace_id") != trace_id and entry.get("trace_id") != trace_id:
            continue
        if task_id and payload.get("task_id") != task_id:
            continue
        payloads.append(payload)
    return payloads


def _sync_transcript_entries_to_audit_service(app: FastAPI) -> None:
    wrapped_entries = []
    for index, entry in enumerate(app.state.transcript_store.entries):
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        wrapped_entries.append(
            SimpleNamespace(
                entry_id=str(entry.get("entry_id") or f"real-notion-audit-{index}"),
                trace_id=str(entry.get("trace_id") or payload.get("trace_id") or ""),
                session_id=str(entry.get("session_id") or ""),
                turn_id=str(entry.get("turn_id") or ""),
                entry_type=entry.get("entry_type") or "",
                timestamp=entry.get("timestamp") or datetime.now(timezone.utc),
                source=str(entry.get("source") or ""),
                payload=payload,
            )
        )
    app.state.audit_service.store.sync_from_transcript_entries(wrapped_entries)


def _create_mcp_task_via_requests(
    *,
    base_url: str,
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    phase: str,
    suffix: str,
) -> str:
    response = requests.post(
        f"{base_url}/api/web/tasks",
        json={
            "idempotency_key": f"real-notion-task-crud-{phase}-{suffix}",
            "title": f"Real Notion MCP task CRUD {phase}",
            "task_type": "system_action",
            "originator_id": "real-ci",
            "target_id": f"mcp:{server_id}:{tool_name}",
            "metadata": {
                "executor_type": "mcp",
                "mcp_server_id": server_id,
                "mcp_tool_name": tool_name,
                "arguments": arguments,
                "trace_id": f"real-notion-task-crud-{phase}-{suffix}",
                "real_test": True,
                "operator_approval": True,
                "question_id": "q8",
            },
            "contract": {
                "expected_outcome": {
                    "notion_mcp_tool": tool_name,
                    "phase": phase,
                    "remote_side_effect_verified": True,
                },
                "success_criteria": [
                    "MCP execution result contains actual_outcome",
                    "MCP execution result contains external_execution metadata",
                    "task outcome scoring passes with full confidence",
                ],
                "acceptance_conditions": [
                    "task center status is done",
                    "task outcome exists",
                    "memory writeback exists and is queryable by target task id",
                ],
                "verification_method": "rule_based",
                "risk_assessment": {"risk_level": "medium", "external_system": "notion"},
                "verification": {
                    "enabled": True,
                    "strategy": "all_must_pass",
                    "max_total_retries": 0,
                    "fallback_action": "fail",
                    "verifiers": [
                        {
                            "verifier_id": f"real_notion_mcp_task_score_{phase}_{suffix}",
                            "verifier_type": "rule_based",
                            "retry_on_failure": False,
                            "max_retries": 0,
                            "config": {
                                "rules": [
                                    {"type": "required_field", "field": "actual_outcome"},
                                    {"type": "required_field", "field": "external_execution"},
                                ]
                            },
                        }
                    ],
                },
            },
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["metadata"]["executor_type"] == "mcp"
    assert created["metadata"]["mcp_server_id"] == server_id
    assert created["metadata"]["mcp_tool_name"] == tool_name
    return str(created["task_id"])


def _run_one_worker_cycle_and_fetch_detail(
    *,
    app: FastAPI,
    base_url: str,
    task_id: str,
    trace_id: str,
) -> dict[str, Any]:
    stats = asyncio.run(app.state.task_service.run_worker_cycle())
    assert "error" not in stats, stats
    response = requests.get(f"{base_url}/api/web/tasks/{task_id}/detail", timeout=30)
    assert response.status_code == 200, response.text
    detail = response.json()
    task = detail["task"]
    if stats.get("tasks_succeeded") != 1:
        dao_ready = app.state.task_service._task_dao.list_tasks(status="todo", limit=20)
        raise AssertionError(
            json.dumps(
                {
                    "stats": stats,
                    "task_id": task_id,
                    "task_status": task.get("status"),
                    "attempt_count": task.get("attempt_count"),
                    "last_error": task.get("last_error"),
                    "dao_ready_task_ids": [item.get("task_id") for item in dao_ready],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    assert task["status"] == "done", task
    done_list = requests.get(
        f"{base_url}/api/web/tasks",
        params={"status_filter": "done", "metadata_filters": f"trace_id={trace_id}", "limit": 20},
        timeout=30,
    )
    assert done_list.status_code == 200, done_list.text
    assert any(item["task_id"] == task_id and item["status"] == "done" for item in done_list.json())
    execution = task["metadata"]["external_execution"]
    assert execution["executor_type"] == "mcp"
    assert execution["result"]["status"] == "completed", execution
    assert execution["result"]["error_code"] is None, execution
    outcome = app.state.task_service.get_task_outcome(task_id)
    assert outcome is not None, task
    assert outcome["task_id"] == task_id
    assert outcome["trace_id"] == trace_id
    assert outcome["overall_passed"] is True
    assert outcome["confidence_score"] == 1.0
    verification = outcome["verification_result"]
    assert verification["overall_passed"] is True
    assert verification["confidence_score"] == 1.0
    assert len(verification["verifier_results"]) == 1
    verifier = verification["verifier_results"][0]
    assert verifier["passed"] is True
    assert verifier["confidence"] == 1.0
    assert verifier["details"]["rule_results"]
    assert all(item["passed"] is True for item in verifier["details"]["rule_results"])

    memory_writeback = app.state.task_service.write_task_outcome_to_memory(
        app.state.memory_service,
        task_id,
    )
    assert memory_writeback["memory_id"]
    memory_response = requests.get(
        f"{base_url}/api/web/memory/records",
        params={"target_id": task_id, "trace_id": trace_id, "limit": 20},
        timeout=30,
    )
    assert memory_response.status_code == 200, memory_response.text
    memories = memory_response.json()["items"]
    assert any(item["memory_id"] == memory_writeback["memory_id"] for item in memories), memories
    memory_detail = requests.get(f"{base_url}/api/web/memory/{memory_writeback['memory_id']}", timeout=30)
    assert memory_detail.status_code == 200, memory_detail.text
    memory_payload = memory_detail.json()
    assert memory_payload["memory_id"] == memory_writeback["memory_id"]
    assert memory_payload["target_id"] == task_id
    assert memory_payload["payload"]["overall_passed"] is True
    assert memory_payload["payload"]["task_id"] == task_id
    assert memory_payload["payload"]["verification_result"]["overall_passed"] is True

    mcp_audits = _transcript_payloads(app, trace_id=trace_id)
    assert any(
        item.get("phase") == "completed"
        and item.get("status") == "completed"
        and item.get("server_id")
        and item.get("tool_name")
        and item.get("request")
        and item.get("response")
        for item in mcp_audits
    ), mcp_audits
    task_audits = _transcript_payloads(app, task_id=task_id)
    assert any(item.get("action") == "TASK_CREATED" for item in task_audits), task_audits
    assert any(item.get("action") == "TASK_STATUS_UPDATED" for item in task_audits), task_audits

    execution_history = requests.get(f"{base_url}/api/web/tasks/{task_id}/execution-history", timeout=30)
    assert execution_history.status_code == 200, execution_history.text
    history = execution_history.json()
    assert history["task"]["task_id"] == task_id
    assert history["task"]["status"] == "done"
    assert history["audit_trail"]["created_at"]
    assert history["audit_trail"]["completed_at"]

    _sync_transcript_entries_to_audit_service(app)
    audit_page = requests.get(f"{base_url}/api/web/audits", params={"page": 1, "page_size": 200}, timeout=30)
    assert audit_page.status_code == 200, audit_page.text
    audit_items = audit_page.json()["items"]
    assert any(item["trace_id"] == trace_id and item["source"] == "mcp.adapter.test_call" for item in audit_items)
    assert any(task_id in item["trace_id"] for item in audit_items)
    return execution["result"]


def _run_forced_notion_mcp_task(
    *,
    app: FastAPI,
    base_url: str,
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    phase: str,
    suffix: str,
    api_key: str,
) -> dict[str, Any]:
    trace_id = f"real-notion-task-crud-{phase}-{suffix}"
    task_id = _create_mcp_task_via_requests(
        base_url=base_url,
        server_id=server_id,
        tool_name=tool_name,
        arguments=arguments,
        phase=phase,
        suffix=suffix,
    )
    result = _run_one_worker_cycle_and_fetch_detail(
        app=app,
        base_url=base_url,
        task_id=task_id,
        trace_id=trace_id,
    )
    detail_response = requests.get(f"{base_url}/api/web/tasks/{task_id}/detail", timeout=30)
    assert api_key not in detail_response.text
    return _parse_mcp_json_text(result)


def test_real_task_module_forces_notion_mcp_page_crud_via_api_key_and_requests(
    request: pytest.FixtureRequest,
) -> None:
    case = _load_real_notion_case()
    api_key = str(case["api_key"])
    notion_version = str(case.get("notion_version", "2022-06-28"))
    parent = _discover_parent(case, api_key=api_key, notion_version=notion_version)

    acceptance_app: FastAPI = request.getfixturevalue("acceptance_app")
    auth_service = AgentAuthService(
        AgentCredentialVault(
            DatabaseConnection(f"{request.getfixturevalue('tmp_path')}/notion-task-crud-auth.sqlite3"),
            master_key="real-notion-task-crud-master-key",
        )
    )
    original_auth_service = acceptance_app.state.agent_coordination_service.auth_service
    original_mcp_service = acceptance_app.state.mcp_service
    original_task_service = acceptance_app.state.task_service
    acceptance_app.state.agent_coordination_service.auth_service = auth_service
    acceptance_app.state.task_service = TaskManagementService(
        registry=TaskRegistry(),
        transcript_store=acceptance_app.state.transcript_store,
        decomposer=TaskDecomposerPlugin(),
        db_path=f"{request.getfixturevalue('tmp_path')}/notion-task-crud-tasks.sqlite3",
    )
    _install_real_notion_mcp_service(acceptance_app, auth_service)
    acceptance_app.state.task_service.attach_dependencies(mcp_service=acceptance_app.state.mcp_service)

    suffix = uuid4().hex[:8]
    server_id = f"real-notion-task-crud-{suffix}"
    credential_id = f"real-notion-task-crud-cred-{suffix}"
    created_title = f"Zentex Real Notion MCP CRUD {suffix}"
    updated_title = f"Zentex Real Notion MCP CRUD updated {suffix}"
    command = str(case.get("command") or "npx")
    args = _render_placeholders(case.get("args", ["-y", "@notionhq/notion-mcp-server"]), {"suffix": suffix})
    auth_config: dict[str, Any] = {
        "type": "api_key",
        "credential_ref": credential_id,
        "inject": {
            "env": {
                "OPENAPI_MCP_HEADERS": (
                    '{"Authorization":"Bearer $auth.api_key",'
                    f'"Notion-Version":"{notion_version}"' + "}"
                )
            }
        },
    }

    try:
        with live_http_server(acceptance_app) as base_url:
            register_response = requests.post(
                f"{base_url}/api/web/mcp-servers/register",
                json={
                    "server_id": server_id,
                    "name": "Real Notion MCP Task CRUD",
                    "description": "Real Notion API-key MCP used by task-center CRUD test",
                    "protocol_version": str(case.get("protocol_version", "2024-11-05")),
                    "transport_type": str(case.get("transport", "stdio")),
                    "command": command,
                    "args": args,
                    "env": {},
                    "scope": ["read", "write"],
                    "auth_mode": "api_key",
                    "auth_config": auth_config,
                    "auth_credential": {
                        "credential_id": credential_id,
                        "credential_type": "api_key",
                        "secret_payload": {"api_key": api_key},
                        "metadata": {"provider": "notion", "purpose": "real task crud"},
                    },
                    "documentation_learning_required": False,
                },
                timeout=90,
            )
            assert register_response.status_code == 200, register_response.text
            assert api_key not in register_response.text
            registered = register_response.json()
            assert registered["status"] == "online"
            tool_names = {tool["tool_name"] for tool in registered["tools"]}
            assert {
                "API-post-page",
                "API-retrieve-a-page",
                "API-patch-page",
            }.issubset(tool_names)

            created = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-post-page",
                arguments={
                    "parent": {
                        "page_id" if parent["kind"] == "page" else "database_id": parent["id"],
                    },
                    "properties": {
                        parent["title_property"]: {"title": [{"text": {"content": created_title}}]},
                    },
                },
                phase="create",
                suffix=suffix,
                api_key=api_key,
            )
            page_id = str(created["id"])
            assert created["object"] == "page"
            assert created["parent"][f"{parent['kind']}_id"].replace("-", "") == parent["id"]
            assert _page_title(created, parent["title_property"]) == created_title
            assert created.get("archived") is False

            read_after_create = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-retrieve-a-page",
                arguments={"page_id": page_id},
                phase="read-after-create",
                suffix=suffix,
                api_key=api_key,
            )
            assert read_after_create["id"] == page_id
            assert _page_title(read_after_create, parent["title_property"]) == created_title
            rest_after_create = _notion_get_page(api_key, notion_version, page_id)
            assert rest_after_create["id"] == page_id
            assert _page_title(rest_after_create, parent["title_property"]) == created_title

            updated = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-patch-page",
                arguments={
                    "page_id": page_id,
                    "properties": {
                        parent["title_property"]: {"title": [{"text": {"content": updated_title}}]},
                    },
                },
                phase="update",
                suffix=suffix,
                api_key=api_key,
            )
            assert updated["id"] == page_id
            assert _page_title(updated, parent["title_property"]) == updated_title

            read_after_update = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-retrieve-a-page",
                arguments={"page_id": page_id},
                phase="read-after-update",
                suffix=suffix,
                api_key=api_key,
            )
            assert read_after_update["id"] == page_id
            assert _page_title(read_after_update, parent["title_property"]) == updated_title
            rest_after_update = _notion_get_page(api_key, notion_version, page_id)
            assert _page_title(rest_after_update, parent["title_property"]) == updated_title

            deleted = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-patch-page",
                arguments={"page_id": page_id, "archived": True, "in_trash": True},
                phase="delete",
                suffix=suffix,
                api_key=api_key,
            )
            assert deleted["id"] == page_id
            assert deleted.get("archived") is True

            read_after_delete = _run_forced_notion_mcp_task(
                app=acceptance_app,
                base_url=base_url,
                server_id=server_id,
                tool_name="API-retrieve-a-page",
                arguments={"page_id": page_id},
                phase="read-after-delete",
                suffix=suffix,
                api_key=api_key,
            )
            assert read_after_delete["id"] == page_id
            assert read_after_delete.get("archived") is True
            rest_after_delete = _notion_get_page(api_key, notion_version, page_id)
            assert rest_after_delete.get("archived") is True
            assert rest_after_delete.get("in_trash") is True
    finally:
        acceptance_app.state.task_service.close()
        acceptance_app.state.task_service = original_task_service
        acceptance_app.state.agent_coordination_service.auth_service = original_auth_service
        acceptance_app.state.mcp_service = original_mcp_service
