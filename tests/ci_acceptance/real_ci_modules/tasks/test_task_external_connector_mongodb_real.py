from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from zentex.external_connectors.service import ExternalConnectorService
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models import TaskStatus, TaskType
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.service import TaskManagementService


class _RealAuditTranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def write_entry(self, **entry: Any) -> None:
        self.entries.append(entry)

    def query_by_session(self, session_id: str, limit: int = 500) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry.get("session_id") == session_id][:limit]


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _real_mongodb_container() -> Iterator[str]:
    port = _free_tcp_port()
    name = f"zentex-task-mongo-{uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:27017",
            "mongo:7",
        ],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if run.returncode != 0:
        pytest.fail(f"real MongoDB docker container failed to start: {run.stderr or run.stdout}")

    deadline = time.time() + 45
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.5)
    else:
        subprocess.run(["docker", "stop", name], text=True, capture_output=True, timeout=20, check=False)
        pytest.fail("real MongoDB docker container did not open its TCP port in time")

    try:
        yield f"mongodb://127.0.0.1:{port}/"
    finally:
        subprocess.run(["docker", "stop", name], text=True, capture_output=True, timeout=30, check=False)


@pytest.fixture()
def task_service_with_external_connector(
    tmp_path: Path,
) -> Iterator[tuple[TaskManagementService, ExternalConnectorService, _RealAuditTranscriptStore]]:
    transcript_store = _RealAuditTranscriptStore()
    connector_service = ExternalConnectorService(transcript_store=transcript_store)
    task_service = TaskManagementService(
        registry=TaskRegistry(),
        transcript_store=transcript_store,
        decomposer=TaskDecomposerPlugin(),
        db_path=str(tmp_path / "tasks.sqlite3"),
    )
    task_service.attach_dependencies(
        transcript_store=transcript_store,
        external_connector_service=connector_service,
    )
    try:
        yield task_service, connector_service, transcript_store
    finally:
        task_service.close()


async def _run_worker_until_done(task_service: TaskManagementService, task_id: str) -> Any:
    last_stats: dict[str, Any] = {}
    for _ in range(6):
        last_stats = await task_service.run_worker_cycle()
        task = task_service.get_task(task_id)
        assert task is not None
        if task.status == TaskStatus.DONE:
            return task
        if task.status == TaskStatus.FAILED:
            pytest.fail(f"task {task_id} failed: stats={last_stats}, metadata={task.metadata}")
    raw = task_service._task_dao.get_task(task_id)
    pytest.fail(f"task {task_id} did not complete; stats={last_stats}, raw={raw}")


async def _create_connector_task(
    task_service: TaskManagementService,
    *,
    suffix: str,
    connector_id: str,
    capability: str,
    arguments: dict[str, Any],
) -> Any:
    return await task_service.create_task(
        {
            "idempotency_key": f"task-mongodb-{capability}-{suffix}",
            "title": f"Run {capability} through forced root external plugin",
            "task_type": TaskType.SYSTEM_ACTION,
            "originator_id": "ci-task-external-connector",
            "target_id": f"external_connector:{connector_id}",
            "metadata": {
                "executor_type": "external_connector",
                "external_connector_id": connector_id,
                "external_connector_capability": capability,
                "external_plugin_path": "mongodb_crud_connector/connector.py",
                "external_connector_arguments": arguments,
                "trace_id": f"task-mongodb-{capability}-{suffix}",
            },
        }
    )


@pytest.mark.asyncio()
async def test_task_module_forces_root_plugins_mongodb_crud_connector_real_flow(
    task_service_with_external_connector: tuple[
        TaskManagementService,
        ExternalConnectorService,
        _RealAuditTranscriptStore,
    ],
) -> None:
    suffix = uuid4().hex[:8]
    connector_id = f"task-mongodb-{suffix}"
    database = f"zentex_task_feature70_{suffix}"
    collection = "orders"
    task_service, connector_service, transcript_store = task_service_with_external_connector
    audit_start = len(transcript_store.entries)

    connector = connector_service.register_from_manifest(
        manifest_path="mongodb_crud_connector/manifest.json",
        connector_id_override=connector_id,
        display_name="Task MongoDB Root Plugin Connector",
        description="Task module forced connector for plugins/mongodb_crud_connector.",
        connection_config={"timeout_seconds": 20},
        permission_scope={"allowed_operations": ["mongodb_create", "mongodb_read", "mongodb_update", "mongodb_delete"]},
    )
    assert connector.profile_level.value == "verifiable"
    assert connector.manifest_path == "mongodb_crud_connector/manifest.json"

    from pymongo import MongoClient

    with _real_mongodb_container() as mongo_uri:
        common_args = {
            "mongo_uri": mongo_uri,
            "database": database,
            "collection": collection,
            "server_selection_timeout_ms": 5000,
        }
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            mongo_collection = client[database][collection]

            create_task = await _create_connector_task(
                task_service,
                suffix=suffix,
                connector_id=connector_id,
                capability="mongodb_create",
                arguments={
                    **common_args,
                    "document": {
                        "order_id": f"order-{suffix}",
                        "status": "new",
                        "amount": 42,
                    },
                },
            )
            create_done = await _run_worker_until_done(task_service, create_task.task_id)
            created = mongo_collection.find_one({"order_id": f"order-{suffix}"})
            assert created is not None
            assert created["status"] == "new"
            assert create_done.metadata["external_execution"]["executor_type"] == "external_connector"
            assert create_done.metadata["external_execution"]["connector_id"] == connector_id
            assert create_done.metadata["external_execution"]["external_plugin_path"] == "mongodb_crud_connector/connector.py"
            assert create_done.metadata["external_execution"]["profile_level"] == "verifiable"
            assert create_done.metadata["external_execution"]["risk_level"] == "mutates_remote"
            assert create_done.metadata["external_execution"]["verification_mode"] == "read_after_write"
            assert create_done.metadata["external_execution"]["result"]["evidence_validation_status"] == "present"
            assert create_done.metadata["external_execution"]["result"]["output_summary"]["post_query_count"] == 1

            read_task = await _create_connector_task(
                task_service,
                suffix=suffix,
                connector_id=connector_id,
                capability="mongodb_read",
                arguments={**common_args, "filter": {"order_id": f"order-{suffix}"}},
            )
            read_done = await _run_worker_until_done(task_service, read_task.task_id)
            read_summary = read_done.metadata["external_execution"]["result"]["output_summary"]
            assert read_summary["matched_total"] == 1
            assert read_summary["documents"][0]["amount"] == 42

            update_task = await _create_connector_task(
                task_service,
                suffix=suffix,
                connector_id=connector_id,
                capability="mongodb_update",
                arguments={
                    **common_args,
                    "filter": {"order_id": f"order-{suffix}"},
                    "update": {"status": "paid", "amount": 55},
                },
            )
            update_done = await _run_worker_until_done(task_service, update_task.task_id)
            updated = mongo_collection.find_one({"order_id": f"order-{suffix}"})
            assert updated is not None
            assert updated["status"] == "paid"
            assert updated["amount"] == 55
            update_summary = update_done.metadata["external_execution"]["result"]["output_summary"]
            assert update_summary["matched_count"] == 1
            assert update_summary["modified_count"] == 1
            assert update_summary["post_update_documents"][0]["status"] == "paid"

            delete_task = await _create_connector_task(
                task_service,
                suffix=suffix,
                connector_id=connector_id,
                capability="mongodb_delete",
                arguments={**common_args, "filter": {"order_id": f"order-{suffix}"}},
            )
            delete_done = await _run_worker_until_done(task_service, delete_task.task_id)
            assert mongo_collection.count_documents({"order_id": f"order-{suffix}"}) == 0
            delete_summary = delete_done.metadata["external_execution"]["result"]["output_summary"]
            assert delete_summary["matched_before_delete"] == 1
            assert delete_summary["deleted_count"] == 1
            assert delete_summary["post_query_count"] == 0

            history = connector_service.history(connector_id)
            assert [item.capability for item in history] == [
                "mongodb_create",
                "mongodb_read",
                "mongodb_update",
                "mongodb_delete",
            ]
            assert all(item.status == "success" for item in history)
            assert all(item.evidence_refs[0]["type"] == "mongodb_collection" for item in history)
            assert {task_service.get_task(task_id).status for task_id in [create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id]} == {TaskStatus.DONE}

            completed_task_ids = {
                item.task_id
                for item in task_service.list_tasks(
                    status=TaskStatus.DONE,
                    metadata_filters={"executor_type": "external_connector"},
                    limit=20,
                )
            }
            assert {create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id} <= completed_task_ids

            grouped = task_service.list_tasks_grouped(limit_per_group=50)
            task_center_completed_ids = {item.task_id for item in grouped["completed"]}
            assert {create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id} <= task_center_completed_ids
            for task_id in [create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id]:
                task_center_row = next(item for item in grouped["completed"] if item.task_id == task_id)
                assert task_center_row.status == TaskStatus.DONE
                assert task_center_row.metadata["execution_status"] == "completed"
                assert task_center_row.metadata["external_execution"]["executor_type"] == "external_connector"
                assert task_center_row.metadata["external_execution"]["external_plugin_path"] == "mongodb_crud_connector/connector.py"

            task_ids = [create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id]
            new_audit_entries = transcript_store.entries[audit_start:]

            connector_audit_payloads = [
                entry["payload"]
                for entry in new_audit_entries
                if entry.get("session_id") == "external-connectors"
                and entry.get("entry_type") == "connector_audit_event"
                and entry.get("payload", {}).get("connector_id") == connector_id
            ]
            assert [payload["capability"] for payload in connector_audit_payloads] == [
                "mongodb_create",
                "mongodb_read",
                "mongodb_update",
                "mongodb_delete",
            ]
            assert all(payload["status"] == "success" for payload in connector_audit_payloads)
            assert all(payload["profile_level"] == "verifiable" for payload in connector_audit_payloads)
            assert connector_audit_payloads[0]["evidence_validation_status"] == "present"
            assert connector_audit_payloads[1]["evidence_validation_status"] == "not_required"
            assert connector_audit_payloads[2]["evidence_validation_status"] == "present"
            assert connector_audit_payloads[3]["evidence_validation_status"] == "present"
            assert all(payload["evidence_refs"][0]["type"] == "mongodb_collection" for payload in connector_audit_payloads)
            assert connector_audit_payloads[0]["output_summary"]["post_query_count"] == 1
            assert connector_audit_payloads[2]["output_summary"]["modified_count"] == 1
            assert connector_audit_payloads[3]["output_summary"]["post_query_count"] == 0

            task_trace_ids = {
                task_service.get_task(task_id).metadata["external_execution"]["trace_id"]
                for task_id in task_ids
            }
            assert task_trace_ids == {payload["trace_id"] for payload in connector_audit_payloads}

            task_audit_payloads = [
                entry["payload"]
                for entry in new_audit_entries
                if entry.get("session_id") == "task-management-audit"
                and getattr(entry.get("entry_type"), "value", entry.get("entry_type")) == "plugin_audit_event"
                and entry.get("payload", {}).get("task_id") in task_ids
            ]
            created_task_ids = {
                payload["task_id"]
                for payload in task_audit_payloads
                if payload["action"] == "TASK_CREATED"
            }
            done_task_ids = {
                payload["task_id"]
                for payload in task_audit_payloads
                if payload["action"] == "TASK_STATUS_UPDATED"
                and payload["details"].get("new_status") == "done"
            }
            assert set(task_ids) == created_task_ids
            assert set(task_ids) == done_task_ids
            assert len(connector_service.history(connector_id)) == len(connector_audit_payloads) == 4
        finally:
            client.close()
            task_service.bulk_delete(
                [create_task.task_id, read_task.task_id, update_task.task_id, delete_task.task_id],
                force=True,
            )
