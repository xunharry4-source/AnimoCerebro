from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
import pytest
import requests

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-q8-separated-{suffix}",
            "summary": "Q8 separated task sync test",
            "context_updates": {
                "q8_q1_q7_snapshot": {
                    "q3": {
                        "available_cognitive_tools": ["reflection", "learning"],
                        "available_execution_tools": ["cli:gemini"],
                        "cli_tools": [{"tool_name": "gemini"}],
                    },
                    "q4": {"actionable_space": ["internal audit reflection"]},
                    "q5": {"allowed_action_space": ["registered cli"]},
                    "q6": {"absolute_red_lines": ["no secret leakage"]},
                    "q7": {"fallback_plans": ["internal follow-up"]},
                },
                "q8_objective_profile": {
                    "current_mission": f"separate internal and external Q8 tasks {suffix}",
                    "primary_objectives": ["prove physical Q8 task isolation"],
                    "secondary_objectives": ["preserve task center queryability"],
                    "completion_conditions": ["internal and external tasks are queryable separately"],
                    "pause_conditions": ["scope isolation fails"],
                    "escalation_conditions": ["external auth missing"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"internal-reflection-{suffix}",
                            "title": f"write internal reflection after Q8 run {suffix}",
                            "reason": "internal reflection uses Zentex audit and memory only",
                            "success_criteria": ["reflection task is stored as internal"],
                        },
                        {
                            "task_id": f"external-gemini-{suffix}",
                            "title": f"use Gemini CLI for external file operation {suffix}",
                            "reason": "external task requires registered CLI executor",
                            "task_scope": "external",
                            "executor_type": "cli",
                            "target_id": "cli:gemini",
                            "metadata": {
                                "executor_type": "cli",
                                "target_id": "cli:gemini",
                                "cli_tool_name": "gemini",
                            },
                            "success_criteria": ["CLI execution evidence is recorded"],
                        },
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


@pytest.mark.asyncio
async def test_q8_separated_internal_external_tasks_sync_and_query_via_real_api(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:10]
    session_id = f"q8-separated-{suffix}"
    task_service = acceptance_app.state.task_service
    created_ids: list[str] = []

    try:
        await sync_q8_tasks_to_task_service(
            task_service=task_service,
            session_id=session_id,
            snapshot_map=_snapshot(session_id, suffix),
        )

        persisted = task_service.list_tasks(metadata_filters={"session_id": session_id})
        created_ids = [task.task_id for task in persisted]
        assert len(persisted) == 2
        by_scope = {task.task_scope.value: task for task in persisted}
        assert set(by_scope) == {"internal", "external"}
        assert by_scope["internal"].metadata["source_chain"] == "internal_q8"
        assert by_scope["internal"].execution_assignment["executor_type"] == "internal"
        assert by_scope["external"].metadata["source_chain"] == "external_q8"
        assert by_scope["external"].metadata["executor_type"] == "cli"
        assert by_scope["external"].execution_assignment["executor_type"] == "cli"
        assert by_scope["external"].target_id == "cli:gemini"

        with live_http_server(acceptance_app) as base_url:
            internal_response = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "task_scope": "internal",
                    "metadata_filters": f"session_id={session_id},source_chain=internal_q8",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert internal_response.status_code == 200, internal_response.text
            internal_rows = internal_response.json()
            assert len(internal_rows) == 1
            assert internal_rows[0]["task_id"] == by_scope["internal"].task_id
            assert internal_rows[0]["task_scope"] == "internal"
            assert internal_rows[0]["metadata"]["source_chain"] == "internal_q8"

            external_response = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "task_scope": "external",
                    "metadata_filters": f"session_id={session_id},source_chain=external_q8",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert external_response.status_code == 200, external_response.text
            external_rows = external_response.json()
            assert len(external_rows) == 1
            assert external_rows[0]["task_id"] == by_scope["external"].task_id
            assert external_rows[0]["task_scope"] == "external"
            assert external_rows[0]["metadata"]["executor_type"] == "cli"
            assert external_rows[0]["target_id"] == "cli:gemini"

            external_page = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={
                    "group": "todo",
                    "task_scope": "external",
                    "metadata_filters": f"session_id={session_id},source_chain=external_q8",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert external_page.status_code == 200, external_page.text
            page_payload = external_page.json()
            assert page_payload["total"] == 1
            assert len(page_payload["items"]) == 1
            assert page_payload["items"][0]["task_id"] == by_scope["external"].task_id
            assert page_payload["items"][0]["task_scope"] == "external"

        delete_result = task_service.bulk_delete(created_ids, force=True)
        assert delete_result["failed"] == []
        assert {item["task_id"] for item in delete_result["success"]} == set(created_ids)
        assert task_service.list_tasks(metadata_filters={"session_id": session_id}) == []
        for task_id in created_ids:
            assert task_service.get_task(task_id) is None
            assert task_service._task_dao.get_task(task_id) is None
        created_ids.clear()
    finally:
        if created_ids:
            task_service.bulk_delete(created_ids, force=True)
