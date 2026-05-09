from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
import requests

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def test_task_scope_is_persisted_and_returned_by_real_tasks_api(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:10]
    internal_key = f"ci-task-scope-internal-{suffix}"
    external_key = f"ci-task-scope-external-{suffix}"
    created_ids: list[str] = []
    task_service = acceptance_app.state.task_service

    try:
        with task_service._db.get_connection() as conn:
            columns = {
                str(row[1]): {
                    "notnull": int(row[3]),
                    "default": row[4],
                }
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
        assert "task_scope" in columns
        assert columns["task_scope"]["notnull"] == 1
        assert str(columns["task_scope"]["default"]).strip("'\"") == "internal"

        with live_http_server(acceptance_app) as base_url:
            internal_response = requests.post(
                f"{base_url}/api/web/tasks",
                json={
                    "idempotency_key": internal_key,
                    "title": f"CI internal task scope {suffix}",
                    "task_type": "cognitive_step",
                    "originator_id": "ci-task-scope",
                    "remarks": "Verify default internal task_scope through real HTTP API.",
                    "metadata": {"source_module": "ci_task_scope", "run_id": suffix},
                },
                timeout=30,
            )
            assert internal_response.status_code == 200, internal_response.text
            internal_payload = internal_response.json()
            created_ids.append(internal_payload["task_id"])
            assert internal_payload["idempotency_key"] == internal_key
            assert internal_payload["metadata"]["source_module"] == "ci_task_scope"
            assert internal_payload["metadata"]["run_id"] == suffix
            assert internal_payload["task_scope"] == "internal"
            assert internal_payload["execution_assignment"]["executor_type"] == "internal"

            external_response = requests.post(
                f"{base_url}/api/web/tasks",
                json={
                    "idempotency_key": external_key,
                    "title": f"CI external CLI task scope {suffix}",
                    "task_type": "system_action",
                    "originator_id": "ci-task-scope",
                    "target_id": "cli:gemini",
                    "remarks": "Verify external task_scope through real HTTP API.",
                    "metadata": {
                        "source_module": "ci_task_scope",
                        "run_id": suffix,
                        "executor_type": "cli",
                        "cli_tool_name": "gemini",
                    },
                },
                timeout=30,
            )
            assert external_response.status_code == 200, external_response.text
            external_payload = external_response.json()
            created_ids.append(external_payload["task_id"])
            assert external_payload["idempotency_key"] == external_key
            assert external_payload["metadata"]["source_module"] == "ci_task_scope"
            assert external_payload["metadata"]["run_id"] == suffix
            assert external_payload["metadata"]["executor_type"] == "cli"
            assert external_payload["target_id"] == "cli:gemini"
            assert external_payload["task_scope"] == "external"
            assert external_payload["execution_assignment"]["executor_type"] == "cli"

            internal_list_response = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "task_scope": "internal",
                    "metadata_filters": f"source_module=ci_task_scope,run_id={suffix}",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert internal_list_response.status_code == 200, internal_list_response.text
            internal_rows = internal_list_response.json()
            assert any(row["task_id"] == internal_payload["task_id"] for row in internal_rows)
            assert all(row["task_scope"] == "internal" for row in internal_rows)
            assert all(row["metadata"]["source_module"] == "ci_task_scope" for row in internal_rows)
            assert all(row["metadata"]["run_id"] == suffix for row in internal_rows)

            external_list_response = requests.get(
                f"{base_url}/api/web/tasks",
                params={
                    "task_scope": "external",
                    "metadata_filters": f"source_module=ci_task_scope,run_id={suffix}",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert external_list_response.status_code == 200, external_list_response.text
            external_rows = external_list_response.json()
            assert any(row["task_id"] == external_payload["task_id"] for row in external_rows)
            assert all(row["task_scope"] == "external" for row in external_rows)
            assert all(row["metadata"]["source_module"] == "ci_task_scope" for row in external_rows)
            assert all(row["metadata"]["run_id"] == suffix for row in external_rows)

            external_page_response = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={
                    "group": "todo",
                    "task_scope": "external",
                    "source_module": "ci_task_scope",
                    "metadata_filters": f"source_module=ci_task_scope,run_id={suffix}",
                    "limit": 20,
                    "offset": 0,
                },
                timeout=30,
            )
            assert external_page_response.status_code == 200, external_page_response.text
            external_page = external_page_response.json()
            assert external_page["group"] == "todo"
            assert external_page["limit"] == 20
            assert external_page["offset"] == 0
            assert external_page["total"] >= 1
            assert any(row["task_id"] == external_payload["task_id"] for row in external_page["items"])
            assert all(row["task_scope"] == "external" for row in external_page["items"])
            assert all(row["metadata"]["source_module"] == "ci_task_scope" for row in external_page["items"])
            assert all(row["metadata"]["run_id"] == suffix for row in external_page["items"])

            invalid_scope_response = requests.get(
                f"{base_url}/api/web/tasks",
                params={"task_scope": "partner"},
                timeout=30,
            )
            assert invalid_scope_response.status_code == 400, invalid_scope_response.text
            assert "Invalid task_scope: partner" in invalid_scope_response.text

            invalid_page_scope_response = requests.get(
                f"{base_url}/api/web/tasks/page",
                params={"group": "todo", "task_scope": "partner"},
                timeout=30,
            )
            assert invalid_page_scope_response.status_code == 400, invalid_page_scope_response.text
            assert "Invalid task_scope: partner" in invalid_page_scope_response.text

        internal_db = task_service._task_dao.get_task(internal_payload["task_id"])
        external_db = task_service._task_dao.get_task(external_payload["task_id"])
        assert internal_db is not None
        assert external_db is not None
        assert internal_db["task_scope"] == "internal"
        assert external_db["task_scope"] == "external"

        internal_model = task_service.get_task(internal_payload["task_id"])
        external_model = task_service.get_task(external_payload["task_id"])
        assert internal_model is not None
        assert external_model is not None
        assert internal_model.task_scope.value == "internal"
        assert external_model.task_scope.value == "external"

        delete_result = task_service.bulk_delete(created_ids, force=True)
        assert delete_result["failed"] == []
        assert {item["task_id"] for item in delete_result["success"]} == set(created_ids)
        assert task_service.get_task(internal_payload["task_id"]) is None
        assert task_service.get_task(external_payload["task_id"]) is None
        assert task_service._task_dao.get_task(internal_payload["task_id"]) is None
        assert task_service._task_dao.get_task(external_payload["task_id"]) is None
        assert not task_service.list_tasks(
            source_module="ci_task_scope",
            metadata_filters={"source_module": "ci_task_scope", "run_id": suffix},
            limit=20,
            offset=0,
        )
        created_ids.clear()
    finally:
        if created_ids:
            task_service.bulk_delete(created_ids, force=True)
