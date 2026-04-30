from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from zentex.agents.auth import AgentAuthService, AgentCredentialVault
from zentex.cli.adapter import create_cli_adapter_plugin
from zentex.cli.models import CliToolRegistrationConfig
from zentex.cli.service import CliIntegrationService
from zentex.common.database import DatabaseConnection
from zentex.memory.service import MemoryService
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models import TaskStatus, TaskType
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.service import TaskManagementService
from zentex.tasks.verification.models import VerificationStrategy, VerificationType


class _TranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def write_entry(self, **payload: Any) -> None:
        self.entries.append(payload)

    def list_entries(
        self,
        *,
        session_id: str | None = None,
        entry_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        entries = self.entries
        if session_id is not None:
            entries = [entry for entry in entries if entry.get("session_id") == session_id]
        if entry_type is not None:
            entries = [entry for entry in entries if entry.get("entry_type") == entry_type]
        return list(entries[-limit:])


def _require_real_gemini_cli() -> str:
    executable = shutil.which("gemini")
    if not executable:
        pytest.fail("real gemini CLI is not installed on PATH")
    try:
        probe = subprocess.run(
            [executable, "--version"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("real gemini CLI did not answer --version within 20s; CLI is not usable non-interactively")
    if probe.returncode != 0:
        pytest.fail(f"real gemini CLI is not usable: {probe.stderr or probe.stdout}")
    return executable


def _require_cli_gemini_api_key_from_process_env() -> str:
    """Read only CLI-test process env. Do not load project .env/provider config."""
    for name in ("ZENTEX_CLI_GEMINI_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value
    pytest.fail(
        "real Gemini CLI CRUD test requires a CLI credential in process env "
        "ZENTEX_CLI_GEMINI_API_KEY or GEMINI_API_KEY. Project .env is provider config and is intentionally not loaded."
    )


def _auth_service(db_path: Path) -> AgentAuthService:
    return AgentAuthService(
        AgentCredentialVault(
            DatabaseConnection(str(db_path)),
            master_key="gemini-cli-crud-auth-master-key",
        )
    )


def _verification_contract() -> dict[str, Any]:
    return {
        "expected_outcome": {
            "target_file_deleted": True,
            "proof_file_created": True,
        },
        "success_criteria": [
            "External CLI executed through task-center CLI dispatch",
            "The task center records a completed task",
            "The verified task outcome can be written to memory",
            "The CLI scoring module calculates from real execution history",
        ],
        "verification": {
            "enabled": True,
            "strategy": VerificationStrategy.ALL_MUST_PASS.value,
            "fallback_action": "fail",
            "max_total_retries": 0,
            "verifiers": [
                {
                    "verifier_id": "cli_external_execution_receipt",
                    "verifier_type": VerificationType.RULE_BASED.value,
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
    }


def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload")
    return payload if isinstance(payload, dict) else {}


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _assert_audit_workflow_is_queryable(
    *,
    transcript_store: _TranscriptStore,
    task_id: str,
    trace_id: str,
    tool_name: str,
) -> None:
    task_audits = [
        _entry_payload(entry)
        for entry in transcript_store.entries
        if entry.get("session_id") == "task-management-audit"
        and _entry_payload(entry).get("task_id") == task_id
    ]
    actions = [payload.get("action") for payload in task_audits]
    assert "TASK_CREATED" in actions
    assert actions.count("TASK_METADATA_UPDATED") >= 2
    assert "TASK_VERIFICATION_COMPLETED" in actions
    assert "TASK_STATUS_UPDATED" in actions

    external_phases = [
        payload.get("details", {}).get("metadata_updates", {}).get("external_execution", {}).get("phase")
        for payload in task_audits
        if payload.get("action") == "TASK_METADATA_UPDATED"
    ]
    assert "started" in external_phases
    assert "completed" in external_phases

    status_updates = [
        _value(payload.get("details", {}).get("new_status"))
        for payload in task_audits
        if payload.get("action") == "TASK_STATUS_UPDATED"
    ]
    assert "waiting_confirmation" in status_updates
    assert "done" in status_updates

    verification_events = [
        payload
        for payload in task_audits
        if payload.get("action") == "TASK_VERIFICATION_COMPLETED"
    ]
    assert len(verification_events) == 1
    assert verification_events[0]["details"]["overall_passed"] is True
    assert verification_events[0]["details"]["confidence_score"] == 1.0

    cli_audits = [
        _entry_payload(entry)
        for entry in transcript_store.entries
        if entry.get("session_id") == "cli-management"
        and _entry_payload(entry).get("tool_name") == tool_name
        and _entry_payload(entry).get("trace_id") == trace_id
    ]
    assert len(cli_audits) == 1
    assert cli_audits[0]["mapped_domain"] == "execution"
    assert cli_audits[0]["status"] == "success"
    assert cli_audits[0]["exit_code"] == 0
    assert cli_audits[0]["working_directory"]

    workflow = [
        "task_created",
        *[
            f"external_execution_{phase}"
            for phase in external_phases
            if phase in {"started", "completed"}
        ],
        "cli_call_success",
        "verification_passed",
        *[f"task_status_{status}" for status in status_updates],
    ]
    assert workflow.index("task_created") < workflow.index("external_execution_started")
    assert workflow.index("external_execution_started") < workflow.index("external_execution_completed")
    assert workflow.index("external_execution_completed") < workflow.index("cli_call_success")
    assert workflow.index("cli_call_success") < workflow.index("verification_passed")
    assert workflow.index("verification_passed") < workflow.index("task_status_done")


@pytest.mark.asyncio()
async def test_task_module_forces_real_gemini_cli_to_crud_plain_file(tmp_path: Path) -> None:
    gemini_executable = _require_real_gemini_cli()
    gemini_api_key = _require_cli_gemini_api_key_from_process_env()
    suffix = uuid4().hex
    workspace = tmp_path / f"gemini-crud-{suffix}"
    workspace.mkdir()
    target_file = workspace / "ordinary-file.txt"
    proof_file = workspace / "crud-proof.json"

    created_content = f"created-by-task-{suffix}\n"
    updated_content = f"{created_content}updated-by-gemini-cli-{suffix}\n"
    expected_updated_sha256 = hashlib.sha256(updated_content.encode("utf-8")).hexdigest()

    transcript_store = _TranscriptStore()
    auth_service = _auth_service(tmp_path / "gemini-auth.sqlite3")
    credential_id = f"gemini-cli-credential-{suffix}"
    stored_credential = auth_service.store_credential(
        agent_id="cli:gemini",
        owner_type="cli",
        owner_id="gemini",
        credential_type="api_key",
        credential_id=credential_id,
        secret_payload={"api_key": gemini_api_key},
        metadata={"purpose": "real gemini cli task crud test"},
    )
    assert stored_credential.credential_id == credential_id
    assert stored_credential.owner_type == "cli"
    assert stored_credential.owner_id == "gemini"
    cli_adapter = create_cli_adapter_plugin(transcript_store=transcript_store)
    cli_service = CliIntegrationService(
        adapter=cli_adapter,
        transcript_store=transcript_store,
        documentation_learning_service=None,
        auth_service=auth_service,
    )
    register_response = cli_service.register_tool(
        CliToolRegistrationConfig(
            tool_name="gemini",
            command_executable=gemini_executable,
            command_args=[],
            description="Real Google Gemini CLI used by task-center external CLI dispatch.",
            read_only_flag=False,
            documentation_learning_required=False,
            health_probe_args=["--version"],
            auth_config={
                "type": "api_key",
                "credential_ref": credential_id,
                "env_name": "GEMINI_API_KEY",
            },
        )
    )
    assert register_response.is_ok, register_response.message

    preflight = cli_service.test_call(
        "gemini",
        arguments=["--prompt", "Reply with exactly: READY"],
        working_directory=str(workspace),
        timeout_seconds=60,
    )
    assert preflight.is_ok, preflight.message
    assert preflight.data.status == "success", preflight.data.model_dump(mode="json")
    assert preflight.data.exit_code == 0, preflight.data.model_dump(mode="json")
    assert "READY" in f"{preflight.data.stdout}\n{preflight.data.stderr}", preflight.data.model_dump(mode="json")
    assert gemini_api_key not in str(preflight.data.model_dump(mode="json"))

    task_service = TaskManagementService(
        registry=TaskRegistry(),
        transcript_store=transcript_store,
        decomposer=TaskDecomposerPlugin(),
        db_path=str(tmp_path / "tasks.sqlite3"),
    )
    memory_service = MemoryService(storage_root=tmp_path / "memory")
    task_service.attach_dependencies(cli_service=cli_service)
    try:
        prompt = "\n".join(
            [
                "You are running inside a temporary test directory.",
                "Carry out this exact file CRUD workflow using real filesystem operations.",
                f"Target file: {target_file.name}",
                f"Proof file: {proof_file.name}",
                "1. Verify the target file does not exist.",
                f"2. Create the target file with exactly this UTF-8 content: {created_content!r}.",
                "3. Read the target file back.",
                f"4. Update the target file so its full content is exactly: {updated_content!r}.",
                "5. Read the updated target file back and compute its SHA-256 hex digest from the bytes on disk.",
                "6. Delete the target file.",
                "7. Create the proof file as strict JSON with keys: created, read_after_create, updated, "
                "read_after_update, updated_sha256, deleted, target_exists_after_delete.",
                "The proof values must reflect the actual filesystem state after each operation.",
                "Do not ask for confirmation. Do not leave the target file behind.",
            ]
        )
        trace_id = f"trace-gemini-crud-{suffix}"
        task = await task_service.create_task(
            {
                "idempotency_key": f"task-gemini-cli-crud-{suffix}",
                "title": "Force Gemini CLI to CRUD a plain file",
                "task_type": TaskType.SYSTEM_ACTION,
                "originator_id": "ci_acceptance",
                "target_id": "cli:gemini",
                "metadata": {
                    "executor_type": "cli",
                    "cli_tool_name": "gemini",
                    "arguments": ["--approval-mode", "yolo", "--prompt", prompt],
                    "working_directory": str(workspace),
                    "timeout_seconds": 180,
                    "trace_id": trace_id,
                },
                "contract": _verification_contract(),
            }
        )

        stats = await task_service.run_worker_cycle()
        refreshed = task_service.get_task(task.task_id)

        assert stats["tasks_dispatched"] == 1
        assert refreshed is not None
        failure_context = {
            "stats": stats,
            "task_status": getattr(refreshed.status, "value", refreshed.status),
            "remarks": refreshed.remarks,
            "execution_status": refreshed.metadata.get("execution_status"),
            "external_execution": refreshed.metadata.get("external_execution"),
            "dispatch_failure": refreshed.metadata.get("dispatch_failure"),
        }
        assert stats["tasks_succeeded"] == 1, failure_context
        assert refreshed.status == TaskStatus.DONE
        assert refreshed.metadata["execution_status"] == "completed"
        assert refreshed.metadata["cli_tool_name"] == "gemini"
        assert refreshed.metadata["external_execution"]["executor_type"] == "cli"
        assert refreshed.metadata["external_execution"]["trace_id"] == trace_id
        result = refreshed.metadata["external_execution"]["result"]
        assert result["status"] == "success", result
        assert result["exit_code"] == 0, result
        assert result["tool_name"] == "gemini"
        assert result["working_directory"] == str(workspace)

        assert not target_file.exists(), "Gemini CLI did not delete the CRUD target file"
        assert proof_file.exists(), "Gemini CLI did not create the CRUD proof file"
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        assert proof["created"] is True
        assert proof["read_after_create"] == created_content
        assert proof["updated"] is True
        assert proof["read_after_update"] == updated_content
        assert proof["updated_sha256"] == expected_updated_sha256
        assert proof["deleted"] is True
        assert proof["target_exists_after_delete"] is False
        assert not target_file.exists()

        task_center_stats = task_service.get_task_statistics()
        assert task_center_stats["completed_tasks"] == 1
        assert task_center_stats["failed_tasks"] == 0
        assert task_center_stats["tasks_by_status"]["done"] == 1

        cli_task_stats = cli_service.get_task_statistics("gemini")
        assert cli_task_stats == {
            "in_progress": 0,
            "pending": 0,
            "failed": 0,
            "completed": 1,
            "total": 1,
        }

        outcome = task_service.get_task_outcome(task.task_id)
        assert outcome is not None
        assert outcome["task_id"] == task.task_id
        assert outcome["overall_passed"] is True
        assert outcome["actual_outcome"]["status"] == "success"
        assert outcome["actual_outcome"]["exit_code"] == 0
        assert outcome["verification_result"]["overall_passed"] is True

        memory_writeback = task_service.write_task_outcome_to_memory(memory_service, task.task_id)
        memory_id = memory_writeback["memory_id"]
        remembered = memory_service.get_record(memory_id)
        assert remembered is not None
        assert remembered.memory_id == memory_id
        assert remembered.target_id == task.task_id
        assert remembered.trace_id == trace_id
        assert remembered.source_kind == "task_outcome_writeback"
        assert "task_outcome" in remembered.tags
        assert "verified" in remembered.tags
        assert task.task_id in remembered.content
        queried_memory = memory_service.query_managed_records(trace_id=trace_id, limit=20)
        assert any(item.memory_id == memory_id for item in queried_memory)
        updated_outcome = task_service.get_task_outcome(task.task_id)
        assert updated_outcome is not None
        assert updated_outcome["written_back_to_memory"] is True
        assert updated_outcome["memory_id"] == memory_id

        history = cli_service.get_tool_execution_history("gemini", limit=10)
        assert len(history) == 1
        assert history[0]["trace_id"] == trace_id
        assert history[0]["status"] == "success"
        assert history[0]["exit_code"] == 0
        credit_score = cli_service.calculate_credit_score("gemini")
        assert credit_score["total_executions"] == 1
        assert credit_score["successful_executions"] == 1
        assert credit_score["failed_executions"] == 0
        assert credit_score["success_rate"] == 1.0
        assert credit_score["error_rate"] == 0.0
        assert credit_score["total_score"] > 0
        assert credit_score["credit_level"] in {"fair", "good", "excellent"}

        _assert_audit_workflow_is_queryable(
            transcript_store=transcript_store,
            task_id=task.task_id,
            trace_id=trace_id,
            tool_name="gemini",
        )
    finally:
        memory_service.close()
        task_service.close()


@pytest.mark.asyncio()
async def test_task_center_memory_and_cli_score_are_synchronized_after_real_cli_success(tmp_path: Path) -> None:
    suffix = uuid4().hex
    workspace = tmp_path / f"real-cli-sync-{suffix}"
    workspace.mkdir()
    cli_script = workspace / "crud_cli.py"
    target_file = workspace / "ordinary-file.txt"
    proof_file = workspace / "crud-proof.json"
    created_content = f"created-by-real-cli-{suffix}\n"
    updated_content = f"{created_content}updated-by-real-cli-{suffix}\n"
    expected_updated_sha256 = hashlib.sha256(updated_content.encode("utf-8")).hexdigest()
    cli_script.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import hashlib",
                "import json",
                "import sys",
                "from pathlib import Path",
                "if '--health' in sys.argv:",
                "    print('healthy')",
                "    raise SystemExit(0)",
                "workspace = Path.cwd()",
                "target = workspace / sys.argv[1]",
                "proof = workspace / sys.argv[2]",
                "created = sys.argv[3]",
                "updated = sys.argv[4]",
                "created_before = not target.exists()",
                "target.write_text(created, encoding='utf-8')",
                "read_after_create = target.read_text(encoding='utf-8')",
                "target.write_text(updated, encoding='utf-8')",
                "read_after_update = target.read_text(encoding='utf-8')",
                "updated_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()",
                "target.unlink()",
                "proof.write_text(json.dumps({",
                "    'created': created_before and read_after_create == created,",
                "    'read_after_create': read_after_create,",
                "    'updated': read_after_update == updated,",
                "    'read_after_update': read_after_update,",
                "    'updated_sha256': updated_sha256,",
                "    'deleted': not target.exists(),",
                "    'target_exists_after_delete': target.exists(),",
                "}, ensure_ascii=False), encoding='utf-8')",
                "print('crud complete')",
            ]
        ),
        encoding="utf-8",
    )

    transcript_store = _TranscriptStore()
    cli_adapter = create_cli_adapter_plugin(transcript_store=transcript_store)
    cli_service = CliIntegrationService(
        adapter=cli_adapter,
        transcript_store=transcript_store,
        documentation_learning_service=None,
    )
    register_response = cli_service.register_tool(
        CliToolRegistrationConfig(
            tool_name="real_file_crud_cli",
            command_executable=sys.executable,
            command_args=[str(cli_script)],
            description="Real local subprocess CLI that performs plain-file CRUD for task-center verification.",
            read_only_flag=False,
            documentation_learning_required=False,
            health_probe_args=["--health"],
        )
    )
    assert register_response.is_ok, register_response.message

    task_service = TaskManagementService(
        registry=TaskRegistry(),
        transcript_store=transcript_store,
        decomposer=TaskDecomposerPlugin(),
        db_path=str(tmp_path / "tasks.sqlite3"),
    )
    memory_service = MemoryService(storage_root=tmp_path / "memory")
    task_service.attach_dependencies(cli_service=cli_service)
    try:
        trace_id = f"trace-real-cli-sync-{suffix}"
        task = await task_service.create_task(
            {
                "idempotency_key": f"task-real-cli-sync-{suffix}",
                "title": "Verify task center, memory, and CLI scoring sync",
                "task_type": TaskType.SYSTEM_ACTION,
                "originator_id": "ci_acceptance",
                "target_id": "cli:real_file_crud_cli",
                "metadata": {
                    "executor_type": "cli",
                    "cli_tool_name": "real_file_crud_cli",
                    "arguments": [target_file.name, proof_file.name, created_content, updated_content],
                    "working_directory": str(workspace),
                    "timeout_seconds": 30,
                    "trace_id": trace_id,
                },
                "contract": _verification_contract(),
            }
        )

        stats = await task_service.run_worker_cycle()
        refreshed = task_service.get_task(task.task_id)
        assert stats["tasks_dispatched"] == 1
        assert stats["tasks_succeeded"] == 1
        assert refreshed is not None
        assert refreshed.status == TaskStatus.DONE
        assert refreshed.metadata["execution_status"] == "completed"
        assert refreshed.metadata["external_execution"]["trace_id"] == trace_id
        assert refreshed.metadata["external_execution"]["result"]["status"] == "success"
        assert refreshed.metadata["external_execution"]["result"]["exit_code"] == 0

        assert not target_file.exists()
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        assert proof["created"] is True
        assert proof["read_after_create"] == created_content
        assert proof["updated"] is True
        assert proof["read_after_update"] == updated_content
        assert proof["updated_sha256"] == expected_updated_sha256
        assert proof["deleted"] is True
        assert proof["target_exists_after_delete"] is False

        task_center_stats = task_service.get_task_statistics()
        assert task_center_stats["completed_tasks"] == 1
        assert task_center_stats["failed_tasks"] == 0
        assert task_center_stats["tasks_by_status"]["done"] == 1
        assert cli_service.get_task_statistics("real_file_crud_cli") == {
            "in_progress": 0,
            "pending": 0,
            "failed": 0,
            "completed": 1,
            "total": 1,
        }

        outcome = task_service.get_task_outcome(task.task_id)
        assert outcome is not None
        assert outcome["overall_passed"] is True
        assert outcome["actual_outcome"]["status"] == "success"
        assert outcome["actual_outcome"]["working_directory"] == str(workspace)
        assert outcome["verification_result"]["overall_passed"] is True

        memory_writeback = task_service.write_task_outcome_to_memory(memory_service, task.task_id)
        memory_id = memory_writeback["memory_id"]
        remembered = memory_service.get_record(memory_id)
        assert remembered is not None
        assert remembered.memory_id == memory_id
        assert remembered.target_id == task.task_id
        assert remembered.trace_id == trace_id
        assert remembered.source_kind == "task_outcome_writeback"
        assert "task_outcome" in remembered.tags
        assert "verified" in remembered.tags
        assert task.task_id in remembered.content
        assert any(item.memory_id == memory_id for item in memory_service.query_managed_records(trace_id=trace_id, limit=20))
        updated_outcome = task_service.get_task_outcome(task.task_id)
        assert updated_outcome is not None
        assert updated_outcome["written_back_to_memory"] is True
        assert updated_outcome["memory_id"] == memory_id

        history = cli_service.get_tool_execution_history("real_file_crud_cli", limit=10)
        assert len(history) == 1
        assert history[0]["trace_id"] == trace_id
        assert history[0]["status"] == "success"
        assert history[0]["exit_code"] == 0
        credit_score = cli_service.calculate_credit_score("real_file_crud_cli")
        assert credit_score["total_executions"] == 1
        assert credit_score["successful_executions"] == 1
        assert credit_score["failed_executions"] == 0
        assert credit_score["success_rate"] == 1.0
        assert credit_score["error_rate"] == 0.0
        assert credit_score["total_score"] > 0
        assert credit_score["credit_level"] in {"fair", "good", "excellent"}

        _assert_audit_workflow_is_queryable(
            transcript_store=transcript_store,
            task_id=task.task_id,
            trace_id=trace_id,
            tool_name="real_file_crud_cli",
        )
    finally:
        memory_service.close()
        task_service.close()
