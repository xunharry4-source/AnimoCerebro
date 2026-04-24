from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from zentex.tasks.service import TaskStatus


def test_tasks_agents_cli_and_mcp_acceptance(client: TestClient) -> None:
    suffix = uuid4().hex[:10]
    app = client.app

    task = app.state.task_service.create_task_sync(
        {
            "title": f"acceptance-task-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_acceptance",
            "idempotency_key": f"task-{suffix}",
            "metadata": {"source_module": "ci_acceptance"},
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
                    "metadata": {"source_module": "ci_acceptance"},
                }
            )
        )

    list_response = client.get("/api/web/tasks?source_module=ci_acceptance")
    assert list_response.status_code == 200
    assert any(item["task_id"] == task.task_id for item in list_response.json())

    intervention_response = client.post(
        f"/api/web/tasks/{task.task_id}/intervene",
        json={
            "action": "resume",
            "idempotency_key": f"intervene-{suffix}",
            "remarks": "acceptance transition",
            "operator_id": "ci_acceptance",
        },
    )
    assert intervention_response.status_code == 200
    asyncio.run(
        app.state.task_service.update_task_status(
            task.task_id,
            TaskStatus.DONE,
            remarks="acceptance done",
        )
    )
    detail_response = client.get(f"/api/web/tasks/{task.task_id}/detail")
    assert detail_response.status_code == 200
    assert detail_response.json()["task"]["status"] == "done"
    delete_result = app.state.task_service.bulk_delete([task.task_id], force=True)
    assert any(item["task_id"] == task.task_id for item in delete_result["success"])
    assert app.state.task_service.get_task(task.task_id) is None
    deleted_task_detail = client.get(f"/api/web/tasks/{task.task_id}/detail")
    assert deleted_task_detail.status_code == 404
    deleted_task_intervention = client.post(
        f"/api/web/tasks/{task.task_id}/intervene",
        json={
            "action": "resume",
            "idempotency_key": f"intervene-missing-{suffix}",
            "remarks": "should fail",
            "operator_id": "ci_acceptance",
        },
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
    register_agent = client.post("/api/web/agents/register", json=agent_payload)
    assert register_agent.status_code == 200
    agent_id = register_agent.json()["agent_id"]
    assert register_agent.json()["name"] == agent_payload["name"]
    policy_response = client.patch(
        f"/api/web/agents/{agent_id}/policy",
        json={"trust_level": "trusted", "scope": ["ci_acceptance"]},
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["trust_level"] == "trusted"
    health_response = client.get("/api/web/agents-health/status")
    assert health_response.status_code == 200
    assert any(item["agent_id"] == agent_id for item in health_response.json())
    delete_agent = client.delete(f"/api/web/agents/{agent_id}")
    assert delete_agent.status_code == 200
    assert delete_agent.json()["success"] is True
    health_after_delete = client.get("/api/web/agents-health/status")
    assert health_after_delete.status_code == 200
    assert all(item["agent_id"] != agent_id for item in health_after_delete.json())
    deleted_agent_policy = client.patch(
        f"/api/web/agents/{agent_id}/policy",
        json={"trust_level": "trusted", "scope": ["ci_acceptance"]},
    )
    assert deleted_agent_policy.status_code == 404

    cli_tool = f"acceptance-cli-{suffix}"
    cli_payload = {
        "tool_name": cli_tool,
        "command_executable": "python",
        "command_args": ["-c", "print('cli acceptance ok')"],
        "description": "Acceptance read-only CLI",
        "read_only_flag": True,
    }
    cli_register = client.post(
        "/api/web/cli-tools/register",
        json=cli_payload,
    )
    assert cli_register.status_code == 200
    assert cli_register.json()["command_name"] == cli_tool
    duplicate_cli_register = client.post("/api/web/cli-tools/register", json=cli_payload)
    assert duplicate_cli_register.status_code == 400
    activate_response = client.post(f"/api/web/cli-tools/{cli_tool}/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["status"] == "active"
    cli_health = client.get(f"/api/web/cli-tools/{cli_tool}/health")
    assert cli_health.status_code == 200
    assert cli_health.json()["healthy"] is True
    cli_call = client.post(f"/api/web/cli-tools/{cli_tool}/test-call", json={"timeout_seconds": 5})
    assert cli_call.status_code == 200
    assert "cli acceptance ok" in cli_call.json()["stdout"]
    cli_disable = client.post(f"/api/web/cli-tools/{cli_tool}/disable")
    assert cli_disable.status_code == 200
    assert cli_disable.json()["status"] == "stopped"
    cli_health_after_disable = client.get(f"/api/web/cli-tools/{cli_tool}/health")
    assert cli_health_after_disable.status_code == 200
    assert cli_health_after_disable.json()["healthy"] is False
    delete_cli = client.delete(f"/api/web/cli-tools/{cli_tool}")
    assert delete_cli.status_code == 200
    assert delete_cli.json()["success"] is True
    assert client.get(f"/api/web/cli-tools/{cli_tool}/detail").status_code == 404
    assert client.get(f"/api/web/cli-tools/{cli_tool}/health").status_code == 404
    assert client.delete(f"/api/web/cli-tools/{cli_tool}").status_code == 404

    mcp_id = f"acceptance-mcp-{suffix}"
    mcp_payload = {
        "server_id": mcp_id,
        "transport_type": "stdio",
        "command": "acceptance-mcp",
        "args": [],
        "env": {},
    }
    mcp_register = client.post(
        "/api/web/mcp-servers/register",
        json=mcp_payload,
    )
    assert mcp_register.status_code == 200
    assert mcp_register.json()["server_id"] == mcp_id
    assert mcp_register.json()["status"] == "online"
    duplicate_mcp_register = client.post("/api/web/mcp-servers/register", json=mcp_payload)
    assert duplicate_mcp_register.status_code == 400
    mcp_health = client.get(f"/api/web/mcp-servers/{mcp_id}/health")
    assert mcp_health.status_code == 200
    assert mcp_health.json()["status"] == "online"
    mcp_call = client.post(f"/api/web/mcp-servers/{mcp_id}/test-call", json={"tool_name": "inspect", "arguments": {"x": 1}})
    assert mcp_call.status_code == 200
    assert mcp_call.json()["payload"]["status"] == "completed"
    mcp_disable = client.post(f"/api/web/mcp-servers/{mcp_id}/disable")
    assert mcp_disable.status_code == 200
    assert mcp_disable.json()["status"] == "offline"
    mcp_health_after_disable = client.get(f"/api/web/mcp-servers/{mcp_id}/health")
    assert mcp_health_after_disable.status_code == 200
    assert mcp_health_after_disable.json()["healthy"] is False
    mcp_activate = client.post(f"/api/web/mcp-servers/{mcp_id}/activate")
    assert mcp_activate.status_code == 200
    assert mcp_activate.json()["status"] == "online"
    mcp_delete = client.delete(f"/api/web/mcp-servers/{mcp_id}")
    assert mcp_delete.status_code == 200
    assert mcp_delete.json()["success"] is True
    assert client.get(f"/api/web/mcp-servers/{mcp_id}").status_code == 404
    assert client.get(f"/api/web/mcp-servers/{mcp_id}/health").status_code == 404
    assert client.delete(f"/api/web/mcp-servers/{mcp_id}").status_code == 404
