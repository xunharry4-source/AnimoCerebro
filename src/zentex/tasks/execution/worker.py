from __future__ import annotations
"""
TaskExecutionWorker — the missing bridge between dispatch and plugin execution.

This module is the core of the task-plugin closed loop.  It:
  1. Polls for dispatchable TODO tasks (those whose dependencies are all DONE)
  2. Calls UnifiedTaskRouter to select the best executor (internal plugin first)
  3. Calls InternalPluginExecutor.execute_on_plugin() to actually run the task
  4. Writes the DispatchResult back to the task row (execution_output, status, etc.)
  5. Updates plugin credit scores via router.record_execution_result()
  6. Handles retry / fallback logic per task contract

CONTRACT (fail-closed):
  - Never silently swallow exceptions — all errors are surfaced to the task record.
  - Never return fake / hardcoded results.
  - If no dispatchable tasks exist the cycle is a no-op.
  - If the plugin_layer is None the worker logs a warning and skips execution.
"""


import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.common.startup_markers import log_once

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class WorkerConfig:
    """Tunable parameters for TaskExecutionWorker."""
    # How many TODO tasks to pull per cycle
    batch_size: int = 20
    # Seconds to wait between dispatch and execution attempts
    execution_timeout_seconds: float = 300.0
    # Maximum retry attempts before marking a task FAILED
    max_attempts: int = 3
    # Fallback: if internal plugin fails, try external executors
    enable_fallback: bool = True
    # Only dispatch tasks whose task_type is in this set (None = all types)
    allowed_task_types: Optional[List[str]] = None
    # Option A: If True, only execute tasks with metadata.operator_approval = True
    require_approval: bool = False
    # If True, throttle execution (batch size 1, longer timeouts)
    conservative_mode: bool = False


# ---------------------------------------------------------------------------
# Per-cycle stats (returned for logging / monitoring)
# ---------------------------------------------------------------------------

@dataclass
class WorkerCycleStats:
    """Outcome of a single execution cycle."""
    cycle_started_at: str = ""
    tasks_dispatched: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0          # no plugin matched
    tasks_blocked: int = 0          # router found no eligible executor
    tasks_retried: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    cycle_duration_ms: int = 0


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class TaskExecutionWorker:
    """
    Drives the task → plugin → result write-back cycle.

    Typical usage (inside TaskAutoLoopScheduler):
        worker = TaskExecutionWorker(
            task_dao=task_dao,
            router=unified_task_router,
            internal_executor=internal_plugin_executor,
            config=WorkerConfig(batch_size=10),
        )
        stats = await worker.run_cycle()

    The worker is *stateless between cycles*: it re-reads the DB on each call.
    This makes it safe to run from multiple threads / async contexts provided
    the underlying DAO uses thread-safe connections.
    """

    def __init__(
        self,
        *,
        task_dao: Any,
        router: Any,
        internal_executor: Any,
        task_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        config: Optional[WorkerConfig] = None,
    ) -> None:
        """
        Args:
            task_dao:          TaskDAO instance for DB reads/writes.
            router:            UnifiedTaskRouter for dispatch decisions.
            internal_executor: InternalPluginExecutor for plugin calls.
            config:            Tuning parameters (uses defaults if None).
        """
        self._dao = task_dao
        self._router = router
        self._executor = internal_executor
        self._task_service = task_service
        self._cli_service = cli_service
        self._mcp_service = mcp_service
        self._external_connector_service = external_connector_service
        self._cfg = config or WorkerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_cycle(self) -> WorkerCycleStats:
        """
        Execute one worker cycle:
          - Fetch a batch of dispatchable TODO tasks
          - For each task: dispatch → execute → write result

        Returns a WorkerCycleStats summary for logging.
        """
        started_at = datetime.now(timezone.utc)
        stats = WorkerCycleStats(cycle_started_at=started_at.isoformat())

        log_once(
            "tasks.worker.cycle.invoked",
            batch_size=self._cfg.batch_size,
            max_attempts=self._cfg.max_attempts,
            enable_fallback=self._cfg.enable_fallback,
        )

        dispatchable = self._fetch_dispatchable_tasks()
        logger.info(
            "TaskExecutionWorker cycle: %d dispatchable task(s) found",
            len(dispatchable),
        )

        for task in dispatchable:
            task_id = task.get("task_id", "?")
            try:
                outcome = await self._process_task(task)
                if outcome == "succeeded":
                    stats.tasks_succeeded += 1
                elif outcome == "failed":
                    stats.tasks_failed += 1
                elif outcome == "retried":
                    stats.tasks_retried += 1
                elif outcome == "skipped":
                    stats.tasks_skipped += 1
                elif outcome == "blocked":
                    stats.tasks_blocked += 1
                stats.tasks_dispatched += 1
            except Exception as exc:
                logger.exception(
                    "TaskExecutionWorker: unhandled error for task %s: %s", task_id, exc
                )
                stats.errors.append({"task_id": task_id, "error": str(exc)})
                # Mark task as failed so it doesn't loop forever
                self._mark_failed(task_id, f"Worker unhandled error: {exc}")

        elapsed_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        stats.cycle_duration_ms = elapsed_ms
        logger.info(
            "TaskExecutionWorker cycle done — dispatched=%d succeeded=%d failed=%d "
            "skipped=%d blocked=%d retried=%d duration_ms=%d",
            stats.tasks_dispatched,
            stats.tasks_succeeded,
            stats.tasks_failed,
            stats.tasks_skipped,
            stats.tasks_blocked,
            stats.tasks_retried,
            elapsed_ms,
        )
        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_dispatchable_tasks(self) -> List[Dict[str, Any]]:
        """
        Return TODO tasks that are ready to execute:
          - status == 'todo'
          - all depends_on tasks are 'done'
          - attempt_count < max_attempts
          - (optional) task_type is in allowed_task_types
        """
        candidates = self._dao.list_tasks(
            status="todo",
            limit=self._cfg.batch_size,
        )

        ready = []
        for task in candidates:
            # Filter by task_type if configured
            if self._cfg.allowed_task_types:
                if task.get("task_type") not in self._cfg.allowed_task_types:
                    continue

            # Check attempt budget
            attempt_count = task.get("attempt_count") or 0
            if attempt_count >= self._cfg.max_attempts:
                logger.debug(
                    "Task %s exhausted attempt budget (%d/%d), skipping",
                    task.get("task_id"),
                    attempt_count,
                    self._cfg.max_attempts,
                )
                continue

            # Check dependencies
            depends_on = task.get("depends_on") or []
            if isinstance(depends_on, str):
                try:
                    depends_on = json.loads(depends_on)
                except Exception:
                    logger.warning("Failed to parse depends_on JSON for task %s", task_id)
                    depends_on = []

            if depends_on:
                if not self._all_deps_done(depends_on):
                    continue

            # --- OPTION A: Safety Lock Check ---
            if self._cfg.require_approval:
                metadata = task.get("metadata") or {}
                if not metadata.get("operator_approval"):
                    logger.debug(
                        "Task %s skipped: Q9 rhythm requires manual operator_approval.",
                        task.get("task_id"),
                    )
                    continue

            ready.append(task)

        return ready

    def _all_deps_done(self, dep_ids: List[str]) -> bool:
        """Return True only if every dependency task finished in an accepted terminal state."""
        for dep_id in dep_ids:
            dep = self._dao.get_task(dep_id)
            if dep is None:
                return False
            if dep.get("status") != "done":
                return False
            metadata = dep.get("metadata") if isinstance(dep.get("metadata"), dict) else {}
            completion_status = str(metadata.get("completion_status") or "completed").strip().lower()
            if completion_status not in {"completed", "degraded"}:
                return False
        return True

    @staticmethod
    def _merge_metadata(task: Dict[str, Any], **updates: Any) -> Dict[str, Any]:
        metadata = task.get("metadata")
        merged = dict(metadata) if isinstance(metadata, dict) else {}
        merged.update(updates)
        return merged

    async def _process_task(self, task: Dict[str, Any]) -> str:
        """
        Full dispatch → execute → write-back flow for a single task.

        Returns one of: 'succeeded' | 'failed' | 'retried' | 'skipped'
        """
        task_id: str = task["task_id"]
        attempt_count: int = (task.get("attempt_count") or 0) + 1

        # Detect origin for clinical-grade auditing
        metadata = task.get("metadata") or {}
        source_module = metadata.get("source_module", "manual")
        session_id = metadata.get("session_id", "unknown")
        
        if source_module == "q8_what_should_i_do_now":
            logger.info(f"TaskWorker: Processing MISSION-DRIVEN task {task_id} (Session: {session_id}, Turn: {metadata.get('turn_id')})")
        else:
            logger.info(f"TaskWorker: Processing {source_module} task {task_id}")

        log_once(
            "tasks.worker.process_task.invoked",
            task_id=task_id,
            task_type=str(task.get("task_type") or ""),
            origin=source_module
        )

        # 1. Mark IN_PROGRESS and increment attempt count
        now_iso = datetime.now(timezone.utc).isoformat()
        lease_owner = f"TaskExecutionWorker:{task_id}"
        self._dao.update_task(task_id, {
            "status": "in_progress",
            "attempt_count": attempt_count,
            "execution_started_at": now_iso,
            "started_at": task.get("started_at") or now_iso,
            "metadata": self._merge_metadata(
                task,
                lease={
                    "status": "active",
                    "owner": lease_owner,
                    "acquired_at": now_iso,
                    "heartbeat_at": now_iso,
                    "attempt_count": attempt_count,
                },
            ),
        })

        # 2. Build SubtaskIntent for the router / executor
        subtask_intent = self._build_subtask_intent(task)

        # 3. Task-center selected external executor path.  CLI/MCP tasks are
        # dispatched serially and write their own result back through
        # TaskManagementService, so the generic plugin writeback is skipped.
        external_dispatch = self._external_dispatch_from_task(task)
        if external_dispatch is not None:
            exec_result = await self._execute_on_external_executor(external_dispatch, task_id)
            if exec_result.get("task_center_synchronized") is True:
                return "succeeded" if exec_result.get("succeeded") else "failed"
            self._mark_failed(task_id, exec_result.get("error", "External executor did not synchronize task result"))
            return "failed"

        # 4. Get dispatch decision from the router
        decision = None
        try:
            if self._router is not None:
                decision = await self._router.get_dispatch_decision(
                    subtask_intent,
                    task_id=task_id,
                    context={"task": task, "attempt_count": attempt_count},
                )
        except Exception as exc:
            from zentex.tasks.dispatch.errors import NoMatchingExecutorError

            if isinstance(exc, NoMatchingExecutorError):
                logger.warning(
                    "No matching executor for task %s; blocking task instead of falling back: %s",
                    task_id,
                    exc,
                )
                self._mark_dispatch_blocked(
                    task,
                    reason=str(exc),
                    required_capabilities=exc.required_capabilities,
                    lease_owner=lease_owner,
                    attempt_count=attempt_count,
                )
                return "blocked"
            logger.error("Router failed for task %s; failing task without fallback: %s", task_id, exc, exc_info=True)
            self._mark_failed(task_id, f"Dispatch routing failed: {exc}")
            return "failed"

        # 5. Execute on the selected plugin
        if decision is not None:
            plugin_id = decision.selected_executor.executor_id
        else:
            # Only used when no router is configured.
            plugin_id = await self._direct_plugin_match(subtask_intent)

        if not plugin_id:
            logger.warning("No plugin found for task %s — skipping", task_id)
            self._mark_dispatch_blocked(
                task,
                reason="No matching executor found for task capabilities",
                required_capabilities=list(subtask_intent.required_capabilities or []),
                lease_owner=lease_owner,
                attempt_count=attempt_count,
            )
            return "blocked"

        exec_result = await self._execute_on_plugin(plugin_id, subtask_intent, task_id)

        # 6. Write result back to DB
        if exec_result.get("succeeded"):
            self._write_success(task_id, plugin_id, exec_result)
            await self._update_router_credit(decision, plugin_id, succeeded=True,
                                             duration=exec_result.get("duration_seconds", 0))
            return "succeeded"
        else:
            error_msg = exec_result.get("error", "Unknown error")
            if attempt_count < self._cfg.max_attempts:
                # Put back to 'todo' for retry
                self._dao.update_task(task_id, {
                    "status": "todo",
                    "last_error": error_msg,
                    "execution_finished_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": self._merge_metadata(
                        task,
                        lease={
                            "status": "released",
                            "owner": lease_owner,
                            "released_at": datetime.now(timezone.utc).isoformat(),
                            "attempt_count": attempt_count,
                        },
                    ),
                })
                await self._update_router_credit(decision, plugin_id, succeeded=False,
                                                 duration=exec_result.get("duration_seconds", 0))
                logger.info(
                    "Task %s attempt %d failed, will retry (max=%d): %s",
                    task_id, attempt_count, self._cfg.max_attempts, error_msg,
                )
                return "retried"
            else:
                self._mark_failed(task_id, error_msg, plugin_id=plugin_id)
                await self._update_router_credit(decision, plugin_id, succeeded=False,
                                                 duration=exec_result.get("duration_seconds", 0))
                return "failed"

    async def _execute_on_plugin(
        self,
        plugin_id: str,
        subtask_intent: Any,
        task_id: str,
    ) -> Dict[str, Any]:
        """Call InternalPluginExecutor with a timeout guard."""
        if self._executor is None:
            return {
                "succeeded": False,
                "error": "No InternalPluginExecutor configured",
                "output": None,
                "duration_seconds": 0.0,
            }
        try:
            result = await asyncio.wait_for(
                self._executor.execute_on_plugin(plugin_id, subtask_intent, task_id),
                timeout=self._cfg.execution_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            return {
                "succeeded": False,
                "error": f"Execution timed out after {self._cfg.execution_timeout_seconds}s",
                "output": None,
                "duration_seconds": self._cfg.execution_timeout_seconds,
                "failure_classification": "timeout",
            }
        except Exception as exc:
            return {
                "succeeded": False,
                "error": f"Plugin call raised: {exc}",
                "output": None,
                "duration_seconds": 0.0,
                "failure_classification": "execution_error",
            }

    async def _execute_on_external_executor(self, dispatch: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        executor_type = dispatch["executor_type"]
        if self._task_service is None:
            return {
                "succeeded": False,
                "error": "TaskManagementService is not attached to TaskExecutionWorker",
                "task_center_synchronized": False,
            }

        try:
            if executor_type == "cli":
                if self._cli_service is None:
                    raise RuntimeError("CliIntegrationService is not attached to TaskExecutionWorker")
                try:
                    profile = getattr(self._cli_service, "get_usage_profile", lambda _: None)(dispatch["tool_name"])
                except KeyError:
                    profile = None
                if profile is not None and (
                    getattr(profile, "learning_status", None) != "learned" or getattr(profile, "degraded", False)
                ):
                    raise RuntimeError(f"CLI tool '{dispatch['tool_name']}' is degraded and cannot be auto-dispatched")
                if profile is not None:
                    self._validate_profile_arguments(profile, dispatch.get("arguments") or [], executor_type="cli")
                return await self._cli_service.execute_task(
                    task_service=self._task_service,
                    task_id=task_id,
                    trace_id=dispatch["trace_id"],
                    tool_name=dispatch["tool_name"],
                    arguments=dispatch.get("arguments") or [],
                    stdin_input=dispatch.get("stdin_input"),
                    working_directory=dispatch.get("working_directory"),
                    timeout_seconds=float(dispatch.get("timeout_seconds") or self._cfg.execution_timeout_seconds),
                )
            if executor_type == "mcp":
                if self._mcp_service is None:
                    raise RuntimeError("McpIntegrationService is not attached to TaskExecutionWorker")
                try:
                    profile = getattr(self._mcp_service, "get_tool_usage_profile", lambda *_: None)(
                        dispatch["server_id"],
                        dispatch["tool_name"],
                    )
                except KeyError:
                    profile = None
                if profile is not None and (
                    getattr(profile, "learning_status", None) != "learned" or getattr(profile, "degraded", False)
                ):
                    raise RuntimeError(
                        f"MCP tool '{dispatch['server_id']}/{dispatch['tool_name']}' is degraded and cannot be auto-dispatched"
                    )
                if profile is not None:
                    self._validate_profile_arguments(profile, dispatch.get("arguments") or {}, executor_type="mcp")
                return await self._mcp_service.execute_task(
                    task_service=self._task_service,
                    task_id=task_id,
                    trace_id=dispatch["trace_id"],
                    server_id=dispatch["server_id"],
                    tool_name=dispatch["tool_name"],
                    arguments=dispatch.get("arguments") or {},
                )
            if executor_type == "external_connector":
                return await self._execute_external_connector_task(dispatch, task_id)
            raise RuntimeError(f"Unsupported external executor type: {executor_type}")
        except Exception as exc:
            logger.exception("External executor dispatch failed for task %s", task_id)
            raise

    async def _execute_external_connector_task(self, dispatch: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        if self._external_connector_service is None:
            raise RuntimeError("ExternalConnectorService is not attached to TaskExecutionWorker")

        from zentex.external_connectors.models import ConnectorTestCallRequest
        from zentex.tasks.execution.external_result_bridge import (
            mark_external_execution_started,
            write_external_execution_result,
        )

        connector_id = dispatch["connector_id"]
        capability = dispatch["capability"]
        expected_plugin_path = str(dispatch.get("external_plugin_path") or "").strip()
        connector = self._external_connector_service.get_connector(connector_id)
        actual_plugin_path = str(connector.connection_config.get("plugin_path") or "").strip()
        if expected_plugin_path and actual_plugin_path != expected_plugin_path:
            raise RuntimeError(
                f"External connector plugin path mismatch for {connector_id}: "
                f"expected {expected_plugin_path}, got {actual_plugin_path}"
            )
        capability_record = None
        for item in connector.capabilities:
            if item.name == capability:
                capability_record = item
                break
        risk_level = getattr(getattr(capability_record, "risk_level", None), "value", None) or "read_only"
        profile_level = getattr(getattr(connector, "profile_level", None), "value", None) or "minimal"
        if capability_record is not None:
            cap_profile = getattr(getattr(capability_record, "profile_level", None), "value", None)
            if cap_profile in {"described", "verifiable", "governed"}:
                profile_level = cap_profile
        verification_mode = getattr(getattr(capability_record, "verification_mode", None), "value", None) or "none"

        executor_metadata = {
            "connector_id": connector_id,
            "capability": capability,
            "target_app": connector.target_app,
            "external_plugin_path": actual_plugin_path,
            "profile_level": profile_level,
            "risk_level": risk_level,
            "verification_mode": verification_mode,
            "manifest_path": connector.manifest_path,
            "manifest_hash": connector.manifest_hash,
        }
        await mark_external_execution_started(
            task_service=self._task_service,
            task_id=task_id,
            trace_id=dispatch["trace_id"],
            executor_type="external_connector",
            executor_metadata=executor_metadata,
        )
        invocation = self._external_connector_service.test_call(
            connector_id,
            ConnectorTestCallRequest(
                capability=capability,
                arguments=dispatch.get("arguments") or {},
                trace_id=dispatch["trace_id"],
            ),
        )
        result_payload = invocation.model_dump(mode="json")
        completion = await write_external_execution_result(
            task_service=self._task_service,
            task_id=task_id,
            trace_id=dispatch["trace_id"],
            executor_type="external_connector",
            executor_metadata=executor_metadata,
            result_payload=result_payload,
            succeeded=invocation.status == "success",
            error_message=invocation.operator_message,
        )
        return {
            "succeeded": invocation.status == "success",
            "task_center_synchronized": True,
            "result": result_payload,
            "completion": completion,
        }

    @staticmethod
    def _validate_profile_arguments(profile: Any, arguments: Any, *, executor_type: str) -> None:
        schema = getattr(profile, "argument_schema", {}) or {}
        schema_type = schema.get("type") if isinstance(schema, dict) else None
        if executor_type == "cli":
            if schema_type == "array" and not isinstance(arguments, list):
                raise RuntimeError("CLI usage profile expects array arguments")
            return
        if executor_type == "mcp" and schema_type == "object" and not isinstance(arguments, dict):
            raise RuntimeError("MCP usage profile expects object arguments")

    @staticmethod
    def _external_dispatch_from_task(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        target_id = str(task.get("target_id") or metadata.get("target_id") or "")
        raw_type = (
            metadata.get("executor_type")
            or metadata.get("external_executor_type")
            or metadata.get("executor_kind")
            or ""
        )
        executor_type = str(raw_type).strip().lower()

        if not executor_type:
            if target_id.startswith("cli:") or metadata.get("cli_tool_name"):
                executor_type = "cli"
            elif target_id.startswith("mcp:") or metadata.get("mcp_server_id"):
                executor_type = "mcp"
            elif target_id.startswith("external_connector:") or metadata.get("external_connector_id"):
                executor_type = "external_connector"

        if executor_type == "cli":
            tool_name = (
                metadata.get("cli_tool_name")
                or metadata.get("tool_name")
                or metadata.get("command_name")
                or (target_id.removeprefix("cli:") if target_id.startswith("cli:") else "")
            )
            tool_name = str(tool_name or "").strip()
            if not tool_name:
                return None
            return {
                "executor_type": "cli",
                "trace_id": str(metadata.get("trace_id") or f"cli-task:{task.get('task_id')}"),
                "tool_name": tool_name,
                "arguments": TaskExecutionWorker._list_metadata(metadata, "cli_arguments", "arguments"),
                "stdin_input": metadata.get("stdin_input") or metadata.get("cli_stdin_input"),
                "working_directory": metadata.get("working_directory") or metadata.get("cli_working_directory"),
                "timeout_seconds": metadata.get("timeout_seconds") or metadata.get("cli_timeout_seconds"),
            }

        if executor_type == "mcp":
            target_server = ""
            target_tool = ""
            if target_id.startswith("mcp:"):
                parts = target_id.split(":", 2)
                if len(parts) >= 2:
                    target_server = parts[1]
                if len(parts) == 3:
                    target_tool = parts[2]
            server_id = str(metadata.get("mcp_server_id") or metadata.get("server_id") or target_server or "").strip()
            tool_name = str(metadata.get("mcp_tool_name") or metadata.get("tool_name") or target_tool or "").strip()
            if not server_id or not tool_name:
                return None
            arguments = metadata.get("mcp_arguments")
            if arguments is None:
                arguments = metadata.get("arguments")
            return {
                "executor_type": "mcp",
                "trace_id": str(metadata.get("trace_id") or f"mcp-task:{task.get('task_id')}"),
                "server_id": server_id,
                "tool_name": tool_name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            }

        if executor_type in {"external_connector", "connector"}:
            connector_id = str(
                metadata.get("external_connector_id")
                or metadata.get("connector_id")
                or (target_id.removeprefix("external_connector:") if target_id.startswith("external_connector:") else "")
                or ""
            ).strip()
            capability = str(
                metadata.get("external_connector_capability")
                or metadata.get("connector_capability")
                or metadata.get("capability")
                or ""
            ).strip()
            if not connector_id or not capability:
                return None
            arguments = metadata.get("external_connector_arguments")
            if arguments is None:
                arguments = metadata.get("connector_arguments")
            if arguments is None:
                arguments = metadata.get("arguments")
            return {
                "executor_type": "external_connector",
                "trace_id": str(metadata.get("trace_id") or f"external-connector-task:{task.get('task_id')}"),
                "connector_id": connector_id,
                "capability": capability,
                "external_plugin_path": metadata.get("external_plugin_path") or metadata.get("plugin_path"),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }

        return None

    @staticmethod
    def _list_metadata(metadata: Dict[str, Any], *keys: str) -> List[Any]:
        for key in keys:
            value = metadata.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                return value
            return [value]
        return []

    async def _direct_plugin_match(self, subtask_intent: Any) -> Optional[str]:
        """Try to find a matching plugin without going through the full router."""
        if self._executor is None:
            return None
        try:
            candidates = await self._executor.get_matching_plugins_for_subtask(subtask_intent)
            if candidates:
                return candidates[0].executor_id
        except Exception as exc:
            logger.warning("Direct plugin match failed: %s", exc)
        return None

    def _write_success(
        self,
        task_id: str,
        plugin_id: str,
        exec_result: Dict[str, Any],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        output = exec_result.get("output")
        output_json: Optional[str] = None
        if output is not None:
            try:
                output_json = json.dumps(output, ensure_ascii=False, default=str)
            except Exception:
                logger.warning("Failed to serialize task output for %s, falling back to raw string", task_id)
                output_json = json.dumps({"raw": str(output)})

        self._dao.update_task(task_id, {
            "status": "done",
            "progress": 1.0,
            "completed_at": now_iso,
            "execution_finished_at": now_iso,
            "dispatch_plugin_id": plugin_id,
            "execution_output": output_json,
            "last_error": None,
            "metadata": {
                "completion_status": "completed",
                "lease": {
                    "status": "released",
                    "released_at": now_iso,
                },
            },
        })
        logger.info("Task %s completed successfully via plugin %s", task_id, plugin_id)

    def _mark_failed(
        self,
        task_id: str,
        error_msg: str,
        *,
        plugin_id: Optional[str] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        updates: Dict[str, Any] = {
            "status": "failed",
            "completed_at": now_iso,
            "execution_finished_at": now_iso,
            "last_error": error_msg[:2000],    # cap to 2000 chars
            "metadata": {
                "completion_status": "failed",
                "lease": {
                    "status": "released",
                    "released_at": now_iso,
                },
            },
        }
        if plugin_id:
            updates["dispatch_plugin_id"] = plugin_id
        try:
            self._dao.update_task(task_id, updates)
        except Exception as exc:
            logger.error("Failed to mark task %s as failed: %s", task_id, exc)
        logger.error("Task %s permanently failed: %s", task_id, error_msg)

    def _mark_dispatch_blocked(
        self,
        task: Dict[str, Any],
        *,
        reason: str,
        required_capabilities: List[str],
        lease_owner: str,
        attempt_count: int,
    ) -> None:
        task_id = task["task_id"]
        now_iso = datetime.now(timezone.utc).isoformat()
        self._dao.update_task(task_id, {
            "status": "blocked",
            "execution_finished_at": now_iso,
            "last_error": reason[:2000],
            "metadata": self._merge_metadata(
                task,
                dispatch_failure={
                    "reason": "no_matching_executor",
                    "required_capabilities": list(required_capabilities),
                    "message": reason,
                },
                lease={
                    "status": "released",
                    "owner": lease_owner,
                    "released_at": now_iso,
                    "attempt_count": attempt_count,
                },
            ),
        })

    async def _update_router_credit(
        self,
        decision: Any,
        plugin_id: str,
        *,
        succeeded: bool,
        duration: float,
    ) -> None:
        """Feed execution outcome back into the router's credit scoring."""
        if self._router is None or decision is None:
            return
        try:
            record_fn = getattr(self._router, "record_execution_result", None)
            if callable(record_fn):
                from zentex.tasks.dispatch.models import DispatchResult
                result = DispatchResult(
                    task_id=decision.task_id,
                    executor_id=plugin_id,
                    execution_duration_seconds=duration,
                    succeeded=succeeded,
                    failure_action="retry" if not succeeded else "none",
                )
                maybe_result = record_fn(result)
                if asyncio.iscoroutine(maybe_result) or hasattr(maybe_result, "__await__"):
                    await maybe_result
        except Exception as exc:
            logger.warning("Could not update router credit score: %s", exc)

    @staticmethod
    def _build_subtask_intent(task: Dict[str, Any]) -> Any:
        """
        Convert a raw task DB row into a SubtaskIntent for the executor/router.
        Avoids hard import at module load time so the worker can be imported
        even when tasks.models is not yet fully initialized.
        """
        from zentex.tasks.models import SubtaskIntent

        # depends_on / tags may be stored as JSON strings
        def _parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    logger.warning("Failed to parse tags/capabilities JSON for task %s", task.get("task_id"))
                    return []
            return []

        return SubtaskIntent(
            local_id=task.get("task_id", ""),
            title=task.get("title", ""),
            task_type=task.get("task_type", "cognitive_step"),
            content=task.get("remarks") or task.get("title", ""),
            objective=task.get("remarks") or "",
            required_capabilities=_parse_list(task.get("tags")),
            execution_timeout_seconds=int(task.get("estimated_duration") or 300),
        )
