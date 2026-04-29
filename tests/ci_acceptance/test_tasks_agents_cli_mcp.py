from __future__ import annotations

import asyncio
import sys
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.tasks.service import TaskStatus


def test_tasks_api_filters_and_paginates_in_query_results(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:10]
    app = acceptance_app
    source_module = f"ci_tasks_api_page_{suffix}"
    created_ids: list[str] = []
    try:
        for idx in range(3):
            task = asyncio.run(
                app.state.task_service.create_task(
                    {
                        "title": f"api-page-{suffix}-{idx}",
                        "task_type": "system_action",
                        "originator_id": "ci_acceptance",
                        "idempotency_key": f"api-page-{suffix}-{idx}",
                        "metadata": {"source_module": source_module, "page_marker": suffix},
                    }
                )
            )
            created_ids.append(task.task_id)
        other = asyncio.run(
            app.state.task_service.create_task(
                {
                    "title": f"api-page-other-{suffix}",
                    "task_type": "system_action",
                    "originator_id": "ci_acceptance",
                    "idempotency_key": f"api-page-other-{suffix}",
                    "metadata": {"source_module": f"{source_module}_other", "page_marker": suffix},
                }
            )
        )
        created_ids.append(other.task_id)

        with live_http_server(app) as base_url:
            first_page = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "source_module": source_module,
                    "status_filter": "todo",
                    "limit": 2,
                    "offset": 0,
                },
                timeout=10,
            )
            assert first_page.status_code == 200
            first_items = first_page.json()
            assert len(first_items) == 2
            assert all(item["metadata"]["source_module"] == source_module for item in first_items)
            assert all(item["status"] == "todo" for item in first_items)

            second_page = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "source_module": source_module,
                    "status_filter": "todo",
                    "limit": 2,
                    "offset": 2,
                },
                timeout=10,
            )
            assert second_page.status_code == 200
            second_items = second_page.json()
            assert len(second_items) == 1
            assert second_items[0]["metadata"]["source_module"] == source_module
            assert {item["task_id"] for item in first_items + second_items} == set(created_ids[:3])

            grouped = requests.get(
                f"{base_url}/api/web/tasks/by-status",
                params={"source_module": source_module, "limit_per_group": 1, "offset": 0},
                timeout=10,
            )
            assert grouped.status_code == 200
            grouped_payload = grouped.json()
            assert set(grouped_payload) == {
                "in_progress",
                "pending",
                "waiting_confirmation",
                "completed",
                "cancelled",
            }
            assert len(grouped_payload["pending"]) == 1
            assert grouped_payload["pending"][0]["metadata"]["source_module"] == source_module
            assert grouped_payload["pending"][0]["status"] == "todo"

            invalid_limit = requests.get(f"{base_url}/api/web/tasks", params={"limit": 0}, timeout=10)
            assert invalid_limit.status_code == 422

            unfiltered_marker_page = requests.get(
                f"{base_url}/api/web/tasks",
                params={"metadata_filters": f"page_marker={suffix}", "limit": 10, "offset": 0},
                timeout=10,
            )
            assert unfiltered_marker_page.status_code == 200
            assert {item["task_id"] for item in unfiltered_marker_page.json()} == set(created_ids)
    finally:
        if created_ids:
            app.state.task_service.bulk_delete(created_ids, force=True)


def test_tasks_agents_cli_and_mcp_acceptance(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:10]
    app = acceptance_app
    app.state.agent_coordination_service.transcript_store = app.state.transcript_store
    source_module = f"ci_acceptance_{suffix}"

    task = app.state.task_service.create_task_sync(
        {
            "title": f"acceptance-task-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_acceptance",
            "idempotency_key": f"task-{suffix}",
            "metadata": {"source_module": source_module},
        }
    ) if hasattr(app.state.task_service, "create_task_sync") else None
    if task is None:
        task = asyncio.run(
            app.state.task_service.create_task(
                {
                    "title": f"acceptance-task-{suffix}",
                    "task_type": "system_action",
                    "originator_id": "ci_acceptance",
                    "idempotency_key": f"task-{suffix}",
                    "metadata": {"source_module": source_module},
                }
            )
        )

    with live_http_server(app) as base_url:
        list_response = requests.get(
            f"{base_url}/api/web/tasks",
            params={
                "source_module": source_module,
                "status_filter": "todo",
                "limit": 1,
                "offset": 0,
            },
            timeout=10,
        )
        assert list_response.status_code == 200
        listed_items = list_response.json()
        assert [item["task_id"] for item in listed_items] == [task.task_id]
        assert listed_items[0]["metadata"]["source_module"] == source_module
        assert listed_items[0]["status"] == "todo"

        intervention_response = requests.post(
            f"{base_url}/api/web/tasks/{task.task_id}/intervene",
            json={
                "action": "resume",
                "idempotency_key": f"intervene-{suffix}",
                "remarks": "acceptance transition",
                "operator_id": "ci_acceptance",
            },
            timeout=10,
        )
        assert intervention_response.status_code == 200
        asyncio.run(
            app.state.task_service.update_task_status(
                task.task_id,
                TaskStatus.DONE,
                remarks="acceptance done",
            )
        )
        detail_response = requests.get(f"{base_url}/api/web/tasks/{task.task_id}/detail", timeout=10)
        assert detail_response.status_code == 200
        assert detail_response.json()["task"]["status"] == "done"
        delete_result = app.state.task_service.bulk_delete([task.task_id], force=True)
        assert [item["task_id"] for item in delete_result["success"]] == [task.task_id]
        assert app.state.task_service.get_task(task.task_id) is None
        deleted_task_detail = requests.get(f"{base_url}/api/web/tasks/{task.task_id}/detail", timeout=10)
        assert deleted_task_detail.status_code == 404
        deleted_task_intervention = requests.post(
            f"{base_url}/api/web/tasks/{task.task_id}/intervene",
            json={
                "action": "resume",
                "idempotency_key": f"intervene-missing-{suffix}",
                "remarks": "should fail",
                "operator_id": "ci_acceptance",
            },
            timeout=10,
        )
        assert deleted_task_intervention.status_code == 404

        agent_payload = {
            "name": f"agent-{suffix}",
            "agent_name": "Acceptance Agent",
            "version": "1.0.0",
            "function_description": "CI acceptance agent",
            "endpoint": "local://acceptance",
            "auth_token": f"token-{suffix}",
            "role_tag": "acceptance",
        }
        register_agent = requests.post(f"{base_url}/api/web/agents/register", json=agent_payload, timeout=10)
        assert register_agent.status_code == 200
        agent_id = register_agent.json()["agent_id"]
        assert register_agent.json()["name"] == agent_payload["name"]
        agents_after_register = requests.get(f"{base_url}/api/web/agents", timeout=10)
        assert agents_after_register.status_code == 200
        assert any(item["agent_id"] == agent_id and item["name"] == agent_payload["name"] for item in agents_after_register.json())
        policy_response = requests.patch(
            f"{base_url}/api/web/agents/{agent_id}/policy",
            json={"trust_level": "trusted", "scope": ["ci_acceptance"]},
            timeout=10,
        )
        assert policy_response.status_code == 200
        assert policy_response.json()["trust_level"] == "trusted"
        agent_detail = requests.get(f"{base_url}/api/web/agents/{agent_id}/detail", timeout=10)
        assert agent_detail.status_code == 200
        assert agent_detail.json()["scope"] == ["ci_acceptance"]
        assert agent_detail.json()["trust_level"] == "trusted"
        health_response = requests.get(f"{base_url}/api/web/agents-health/status", timeout=10)
        assert health_response.status_code == 200
        assert any(item["agent_id"] == agent_id for item in health_response.json())
        audit_actions = {
            entry["payload"]["action"]
            for entry in app.state.transcript_store.entries
            if entry.get("payload", {}).get("agent_id") == agent_id
        }
        assert {"REGISTER", "POLICY_UPDATED"}.issubset(audit_actions)
        delete_agent = requests.delete(f"{base_url}/api/web/agents/{agent_id}", timeout=10)
        assert delete_agent.status_code == 200
        assert delete_agent.json()["success"] is True
        health_after_delete = requests.get(f"{base_url}/api/web/agents-health/status", timeout=10)
        assert health_after_delete.status_code == 200
        assert all(item["agent_id"] != agent_id for item in health_after_delete.json())
        agents_after_delete = requests.get(f"{base_url}/api/web/agents", timeout=10)
        assert agents_after_delete.status_code == 200
        assert all(item["agent_id"] != agent_id for item in agents_after_delete.json())
        deleted_agent_policy = requests.patch(
            f"{base_url}/api/web/agents/{agent_id}/policy",
            json={"trust_level": "trusted", "scope": ["ci_acceptance"]},
            timeout=10,
        )
        assert deleted_agent_policy.status_code == 404

        cli_tool = f"acceptance-cli-{suffix}"
        cli_payload = {
            "tool_name": cli_tool,
            "command_executable": sys.executable,
            "command_args": ["-c", "print('cli acceptance ok')"],
            "description": "Acceptance read-only CLI",
            "read_only_flag": True,
        }
        cli_register = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json=cli_payload,
            timeout=10,
        )
        assert cli_register.status_code == 200
        assert cli_register.json()["command_name"] == cli_tool
        cli_rows = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert cli_rows.status_code == 200
        assert any(item["command_name"] == cli_tool for item in cli_rows.json())
        duplicate_cli_register = requests.post(f"{base_url}/api/web/cli-tools/register", json=cli_payload, timeout=10)
        assert duplicate_cli_register.status_code == 400
        activate_response = requests.post(f"{base_url}/api/web/cli-tools/{cli_tool}/activate", timeout=10)
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"
        cli_health = requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/health", timeout=10)
        assert cli_health.status_code == 200
        assert cli_health.json()["healthy"] is True
        cli_call = requests.post(f"{base_url}/api/web/cli-tools/{cli_tool}/test-call", json={"timeout_seconds": 5}, timeout=10)
        assert cli_call.status_code == 200
        cli_call_payload = cli_call.json()
        assert cli_call_payload["status"] == "success"
        assert cli_call_payload["exit_code"] == 0
        assert "cli acceptance ok" in cli_call_payload["stdout"]
        cli_history = requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/execution-history", params={"limit": 1}, timeout=10)
        assert cli_history.status_code == 200
        assert cli_history.json()[0]["tool_name"] == cli_tool
        cli_disable = requests.post(f"{base_url}/api/web/cli-tools/{cli_tool}/disable", timeout=10)
        assert cli_disable.status_code == 200
        assert cli_disable.json()["status"] == "stopped"
        cli_health_after_disable = requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/health", timeout=10)
        assert cli_health_after_disable.status_code == 200
        assert cli_health_after_disable.json()["healthy"] is False
        cli_detail_after_disable = requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/detail", timeout=10)
        assert cli_detail_after_disable.status_code == 200
        assert cli_detail_after_disable.json()["status"] == "stopped"
        delete_cli = requests.delete(f"{base_url}/api/web/cli-tools/{cli_tool}", timeout=10)
        assert delete_cli.status_code == 200
        assert delete_cli.json()["success"] is True
        cli_rows_after_delete = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert cli_rows_after_delete.status_code == 200
        assert all(item["command_name"] != cli_tool for item in cli_rows_after_delete.json())
        assert requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/detail", timeout=10).status_code == 404
        assert requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/health", timeout=10).status_code == 404
        assert requests.delete(f"{base_url}/api/web/cli-tools/{cli_tool}", timeout=10).status_code == 404

        mcp_id = f"acceptance-mcp-{suffix}"
        mcp_payload = {
            "server_id": mcp_id,
            "transport_type": "stdio",
            "command": "acceptance-mcp",
            "args": [],
            "env": {},
        }
        mcp_register = requests.post(
            f"{base_url}/api/web/mcp-servers/register",
            json=mcp_payload,
            timeout=10,
        )
        assert mcp_register.status_code == 200
        assert mcp_register.json()["server_id"] == mcp_id
        assert mcp_register.json()["status"] == "online"
        mcp_rows = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
        assert mcp_rows.status_code == 200
        assert any(item["server_id"] == mcp_id for item in mcp_rows.json())
        duplicate_mcp_register = requests.post(f"{base_url}/api/web/mcp-servers/register", json=mcp_payload, timeout=10)
        assert duplicate_mcp_register.status_code == 400
        mcp_health = requests.get(f"{base_url}/api/web/mcp-servers/{mcp_id}/health", timeout=10)
        assert mcp_health.status_code == 200
        assert mcp_health.json()["status"] == "online"
        mcp_call = requests.post(
            f"{base_url}/api/web/mcp-servers/{mcp_id}/test-call",
            json={"tool_name": "inspect", "arguments": {"x": 1}},
            timeout=10,
        )
        assert mcp_call.status_code == 200
        assert mcp_call.json()["payload"]["status"] == "completed"
        mcp_disable = requests.post(f"{base_url}/api/web/mcp-servers/{mcp_id}/disable", timeout=10)
        assert mcp_disable.status_code == 200
        assert mcp_disable.json()["status"] == "offline"
        mcp_health_after_disable = requests.get(f"{base_url}/api/web/mcp-servers/{mcp_id}/health", timeout=10)
        assert mcp_health_after_disable.status_code == 200
        assert mcp_health_after_disable.json()["healthy"] is False
        mcp_detail_after_disable = requests.get(f"{base_url}/api/web/mcp-servers/{mcp_id}", timeout=10)
        assert mcp_detail_after_disable.status_code == 200
        assert mcp_detail_after_disable.json()["status"] == "offline"
        mcp_activate = requests.post(f"{base_url}/api/web/mcp-servers/{mcp_id}/activate", timeout=10)
        assert mcp_activate.status_code == 200
        assert mcp_activate.json()["status"] == "online"
        mcp_delete = requests.delete(f"{base_url}/api/web/mcp-servers/{mcp_id}", timeout=10)
        assert mcp_delete.status_code == 200
        assert mcp_delete.json()["success"] is True
        mcp_rows_after_delete = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
        assert mcp_rows_after_delete.status_code == 200
        assert all(item["server_id"] != mcp_id for item in mcp_rows_after_delete.json())
        assert requests.get(f"{base_url}/api/web/mcp-servers/{mcp_id}", timeout=10).status_code == 404
        assert requests.get(f"{base_url}/api/web/mcp-servers/{mcp_id}/health", timeout=10).status_code == 404
        assert requests.delete(f"{base_url}/api/web/mcp-servers/{mcp_id}", timeout=10).status_code == 404
