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
                        "target_id": f"cli:executor-{suffix}",
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
            assert all(item["execution_assignment"]["status"] == "assigned" for item in first_items)
            assert all(item["execution_assignment"]["label"] == f"cli:executor-{suffix}" for item in first_items)

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

            first_tab_page = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={"source_module": source_module, "group": "todo", "limit": 2, "offset": 0},
                timeout=10,
            )
            assert first_tab_page.status_code == 200
            first_tab_payload = first_tab_page.json()
            assert first_tab_payload["group"] == "todo"
            assert first_tab_payload["total"] == 3
            assert first_tab_payload["limit"] == 2
            assert first_tab_payload["offset"] == 0
            assert first_tab_payload["counts"]["todo"] == 3
            assert first_tab_payload["counts"]["pending"] == 3
            assert len(first_tab_payload["items"]) == 2
            assert all(item["metadata"]["source_module"] == source_module for item in first_tab_payload["items"])
            assert all(item["status"] == "todo" for item in first_tab_payload["items"])

            second_tab_page = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={"source_module": source_module, "group": "todo", "limit": 2, "offset": 2},
                timeout=10,
            )
            assert second_tab_page.status_code == 200
            second_tab_payload = second_tab_page.json()
            assert second_tab_payload["total"] == 3
            assert second_tab_payload["offset"] == 2
            assert len(second_tab_payload["items"]) == 1
            assert {item["task_id"] for item in first_tab_payload["items"] + second_tab_payload["items"]} == set(created_ids[:3])
            invalid_group = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={"group": "not_a_real_group", "limit": 2, "offset": 0},
                timeout=10,
            )
            assert invalid_group.status_code == 400

            grouped = requests.get(
                f"{base_url}/api/web/tasks/by-status",
                params={"source_module": source_module, "limit_per_group": 1, "offset": 0},
                timeout=10,
            )
            assert grouped.status_code == 200
            grouped_payload = grouped.json()
            assert set(grouped_payload) == {
                "in_progress",
                "todo",
                "blocked",
                "pending",
                "waiting_confirmation",
                "completed",
                "cancelled",
            }
            assert len(grouped_payload["pending"]) == 1
            assert grouped_payload["pending"][0]["metadata"]["source_module"] == source_module
            assert grouped_payload["pending"][0]["status"] == "todo"
            assert len(grouped_payload["todo"]) == 1
            assert grouped_payload["todo"][0]["task_id"] == grouped_payload["pending"][0]["task_id"]
            assert grouped_payload["todo"][0]["execution_assignment"]["label"] == f"cli:executor-{suffix}"

            detail = requests.get(
                f"{base_url}/api/web/tasks/{grouped_payload['todo'][0]['task_id']}/detail",
                timeout=10,
            )
            assert detail.status_code == 200
            detail_task = detail.json()["task"]
            assert detail_task["target_id"] == f"cli:executor-{suffix}"
            assert detail_task["execution_assignment"] == {
                "status": "assigned",
                "source": "target_id",
                "executor_id": f"cli:executor-{suffix}",
                "executor_type": "cli",
                "label": f"cli:executor-{suffix}",
            }

            invalid_limit = requests.get(f"{base_url}/api/web/tasks", params={"limit": 0}, timeout=10)
            assert invalid_limit.status_code == 422

            unfiltered_marker_page = requests.get(
                f"{base_url}/api/web/tasks",
                params={"metadata_filters": f"page_marker={suffix}", "limit": 10, "offset": 0},
                timeout=10,
            )
            assert unfiltered_marker_page.status_code == 200
            assert {item["task_id"] for item in unfiltered_marker_page.json()} == set(created_ids)

            worker_status = requests.get(f"{base_url}/api/web/tasks/worker/status", timeout=10)
            assert worker_status.status_code == 200
            worker_payload = worker_status.json()
            assert set(worker_payload) == {"scheduler", "task_statistics", "database"}
            assert "running" in worker_payload["scheduler"]
            assert worker_payload["database"]["available"] is True
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
        cli_usage_profile = requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/usage-profile", timeout=10)
        assert cli_usage_profile.status_code == 200
        cli_usage_payload = cli_usage_profile.json()
        assert cli_usage_payload["source_type"] == "cli"
        assert cli_usage_payload["learning_status"] == "learned"
        assert cli_usage_payload["argument_schema"] == {"type": "array", "items": {"type": "string"}}
        assert "Acceptance read-only CLI" in cli_usage_payload["task_routing_hints"]
        duplicate_cli_register = requests.post(f"{base_url}/api/web/cli-tools/register", json=cli_payload, timeout=10)
        assert duplicate_cli_register.status_code == 200
        duplicate_cli_payload = duplicate_cli_register.json()
        assert duplicate_cli_payload["command_name"] == cli_tool
        assert duplicate_cli_payload["description"] == "Acceptance read-only CLI"
        assert duplicate_cli_payload["read_only"] is True
        assert duplicate_cli_payload["status"] in {"active", "stopped"}
        cli_rows_after_duplicate = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert cli_rows_after_duplicate.status_code == 200
        assert [item["command_name"] for item in cli_rows_after_duplicate.json()].count(cli_tool) == 1
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
        assert requests.get(f"{base_url}/api/web/cli-tools/{cli_tool}/usage-profile", timeout=10).status_code == 404
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
        mcp_register_payload = mcp_register.json()
        assert mcp_register_payload["server_id"] == mcp_id
        assert mcp_register_payload["status"] == "online"
        assert mcp_register_payload["transport_type"] == "stdio"
        assert mcp_register_payload["tool_count"] == 1
        assert mcp_register_payload["tools"][0]["tool_name"] == "inspect"
        assert mcp_register_payload["tools"][0]["mcp_id"] == f"mcp:{mcp_id}:inspect"
        assert "plugin_id" not in mcp_register_payload["tools"][0]
        mcp_rows = requests.get(f"{base_url}/api/web/mcp-servers", timeout=10)
        assert mcp_rows.status_code == 200
        mcp_rows_by_id = {item["server_id"]: item for item in mcp_rows.json()}
        assert mcp_id in mcp_rows_by_id
        assert mcp_rows_by_id[mcp_id]["server_id"] == mcp_id
        assert mcp_rows_by_id[mcp_id]["status"] == "online"
        assert mcp_rows_by_id[mcp_id]["transport_type"] == "stdio"
        assert mcp_rows_by_id[mcp_id]["tool_count"] == 1
        assert mcp_rows_by_id[mcp_id]["tools"][0]["tool_name"] == "inspect"
        assert mcp_rows_by_id[mcp_id]["tools"][0]["mcp_id"] == f"mcp:{mcp_id}:inspect"
        assert "plugin_id" not in mcp_rows_by_id[mcp_id]["tools"][0]
        mcp_usage_profile = requests.get(
            f"{base_url}/api/web/mcp-servers/{mcp_id}/tools/inspect/usage-profile",
            timeout=10,
        )
        assert mcp_usage_profile.status_code == 200
        mcp_usage_payload = mcp_usage_profile.json()
        assert mcp_usage_payload["source_type"] == "mcp"
        assert mcp_usage_payload["learning_status"] == "learned"
        assert mcp_usage_payload["supported_tools"] == ["inspect"]
        assert mcp_usage_payload["argument_schema"]["properties"]["x"]["type"] == "integer"
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
        assert requests.get(
            f"{base_url}/api/web/mcp-servers/{mcp_id}/tools/inspect/usage-profile",
            timeout=10,
        ).status_code == 404
        assert requests.delete(f"{base_url}/api/web/mcp-servers/{mcp_id}", timeout=10).status_code == 404
