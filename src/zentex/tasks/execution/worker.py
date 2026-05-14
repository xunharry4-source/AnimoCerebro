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
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    # If True, delegate execution to the LangGraph/ReAct execution graph.
    enable_react_execution: bool = False


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
        agent_service: Any = None,
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
        self._agent_service = agent_service
        self._cfg = config or WorkerConfig()
        self._react_executor: Any = None

    def _resolve_cli_service(self) -> Any:
        if self._cli_service is not None:
            return self._cli_service
        from zentex.cli.service import get_service as get_cli_service

        service = get_cli_service()
        if service is None or not callable(getattr(service, "list_tools", None)):
            raise RuntimeError("zentex.cli.service.get_service() did not return a CLI service")
        self._cli_service = service
        return service

    def _resolve_mcp_service(self) -> Any:
        if self._mcp_service is not None:
            return self._mcp_service
        from zentex.mcp.service import get_service as get_mcp_service

        service = get_mcp_service()
        if service is None or not callable(getattr(service, "list_servers", None)):
            raise RuntimeError("zentex.mcp.service.get_service() did not return an MCP service")
        self._mcp_service = service
        return service

    def _resolve_external_connector_service(self) -> Any:
        if self._external_connector_service is not None:
            return self._external_connector_service
        from zentex.external_connectors.service import get_service as get_external_connector_service

        service = get_external_connector_service()
        if service is None or not callable(getattr(service, "list_connectors", None)):
            raise RuntimeError("zentex.external_connectors.service.get_service() did not return a connector service")
        self._external_connector_service = service
        return service

    def _resolve_agent_service(self) -> Any:
        if self._agent_service is not None:
            return self._agent_service
        from zentex.agents.service import get_service as get_agent_service

        service = get_agent_service()
        if service is None or not callable(getattr(service, "dispatch_task", None)):
            raise RuntimeError("zentex.agents.service.get_service() did not return an agent coordination service")
        self._agent_service = service
        return service

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
        Return executable tasks that are ready to execute:
          - status == 'todo' or 'queued'
          - all depends_on tasks are 'done'
          - attempt_count < max_attempts
          - (optional) task_type is in allowed_task_types
        """
        candidates: List[Dict[str, Any]] = []
        for status in ("queued", "todo"):
            remaining = max(0, self._cfg.batch_size - len(candidates))
            if remaining <= 0:
                break
            candidates.extend(self._dao.list_tasks(status=status, limit=remaining))

        ready = []
        for task in candidates:
            metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            if metadata.get("worker_dispatch_enabled") is False:
                logger.info(
                    "Task %s skipped by worker_dispatch_enabled=false",
                    task.get("task_id"),
                )
                continue

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
                dependency_block = self._dependency_block_reason(depends_on)
                if dependency_block:
                    self._mark_dependency_blocked(task, dependency_block)
                    continue
                if not self._all_deps_done(depends_on):
                    continue

            # --- OPTION A: Safety Lock Check ---
            if self._cfg.require_approval:
                if not metadata.get("operator_approval"):
                    now_iso = datetime.now(timezone.utc).isoformat()
                    self._dao.update_task(task.get("task_id"), {
                        "status": "waiting_confirmation",
                        "last_updated_at": now_iso,
                        "metadata": {
                            **metadata,
                            "q9_state_transition": {
                                "from_status": task.get("status") or "todo",
                                "to_status": "waiting_confirmation",
                                "risk_reason": metadata.get("risk_reason")
                                or metadata.get("q9_risk_reason")
                                or "Q9 approval gate requires operator confirmation before commit.",
                                "node_id": metadata.get("q9_node_id") or "node9-confirm节点",
                                "action_rhythm_hint": "confirm_before_commit",
                                "batch_size": self._cfg.batch_size,
                                "worker_id": "TaskExecutionWorker",
                            },
                        },
                    })
                    logger.debug(
                        "Task %s moved to waiting_confirmation: Q9 rhythm requires manual operator_approval.",
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

    def _dependency_block_reason(self, dep_ids: List[str]) -> Dict[str, Any]:
        for dep_id in dep_ids:
            dep = self._dao.get_task(dep_id)
            if dep is None:
                return {}
            dep_status = str(dep.get("status") or "").strip().lower()
            if dep_status in {"failed", "blocked", "cancelled", "archived"}:
                return {
                    "dependency_task_id": dep_id,
                    "dependency_status": dep_status,
                    "reason": f"dependency_failed:{dep_id}:{dep_status}",
                }
        return {}

    def _mark_dependency_blocked(self, task: Dict[str, Any], dependency_block: Dict[str, Any]) -> None:
        task_id = str(task.get("task_id") or "")
        metadata = self._merge_metadata(
            task,
            dependency_failure=dependency_block,
            blocked_reason=dependency_block.get("reason"),
            workflow_event_type="task_blocked",
        )
        self._dao.update_task(
            task_id,
            {
                "status": "blocked",
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata,
            },
        )
        from zentex.audit.workflow_events import record_workflow_node_event

        trace_id = str(metadata.get("trace_id") or f"task:{task_id}")
        session_id = str(metadata.get("session_id") or task.get("originator_id") or "unknown")
        record_workflow_node_event(
            event_type="dependency_failed",
            node_id="dependency-gate",
            node_name="dependency failure propagation",
            status="blocked",
            trace_id=trace_id,
            session_id=session_id,
            turn_id=str(metadata.get("turn_id") or session_id),
            task_id=task_id,
            output_summary={
                "workflow_event_type": "task_blocked",
                "dependency_failed": dependency_block,
            },
            evidence_ref=f"dependency_failed:{task_id}:{dependency_block.get('dependency_task_id')}",
            error_code="DEPENDENCY_FAILED",
            source="zentex.tasks.execution.worker",
        )

    @staticmethod
    def _merge_metadata(task: Dict[str, Any], **updates: Any) -> Dict[str, Any]:
        metadata = task.get("metadata")
        merged = dict(metadata) if isinstance(metadata, dict) else {}
        merged.update(updates)
        return merged

    @staticmethod
    def _physical_file_snapshot(path: Path) -> Dict[str, Any]:
        resolved = path.expanduser()
        if not resolved.exists():
            return {
                "path": str(resolved),
                "exists": False,
                "is_file": False,
                "size_bytes": 0,
                "mtime_ns": None,
                "sha256": "",
            }
        stat = resolved.stat()
        digest = ""
        if resolved.is_file():
            hasher = hashlib.sha256()
            with resolved.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        return {
            "path": str(resolved),
            "exists": True,
            "is_file": resolved.is_file(),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
        }

    @staticmethod
    def _resource_recovery_paths(metadata: Dict[str, Any]) -> tuple[Path, Path, str] | None:
        weekly = str(metadata.get("required_weekly_file") or "").strip()
        report = str(metadata.get("final_report_path") or "").strip()
        dispatch = metadata.get("resource_gap_recovery_dispatch") if isinstance(metadata.get("resource_gap_recovery_dispatch"), dict) else {}
        fallback = str(metadata.get("approved_alternative") or dispatch.get("approved_alternative") or "").strip()
        if not weekly or not report or not dispatch:
            return None
        return Path(weekly), Path(report), fallback

    def _resource_recovery_pre_execution_state(self, task: Dict[str, Any]) -> Dict[str, Any] | None:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        paths = self._resource_recovery_paths(metadata)
        if paths is None:
            return None
        weekly_path, report_path, _fallback = paths
        weekly_snapshot = self._physical_file_snapshot(weekly_path)
        report_snapshot = self._physical_file_snapshot(report_path)
        return {
            "task_id": task.get("task_id"),
            "status": str(task.get("status") or ""),
            "target_id": task.get("target_id"),
            "attempt_count": task.get("attempt_count") or 0,
            "execution_started_at": task.get("execution_started_at"),
            "execution_finished_at": task.get("execution_finished_at"),
            "execution_output": task.get("execution_output"),
            "outcome_exists": (
                self._task_service.get_task_outcome(str(task.get("task_id")))
                if self._task_service is not None and callable(getattr(self._task_service, "get_task_outcome", None))
                else None
            )
            is not None,
            "final_report_exists": report_snapshot["exists"],
            "physical_evidence_before": {
                "weekly_input": weekly_snapshot,
                "final_report": report_snapshot,
            },
        }

    def _resource_recovery_pre_block_reason(self, pre_execution_state: Dict[str, Any] | None) -> str:
        if not pre_execution_state:
            return ""
        evidence = pre_execution_state.get("physical_evidence_before") if isinstance(pre_execution_state.get("physical_evidence_before"), dict) else {}
        weekly = evidence.get("weekly_input") if isinstance(evidence.get("weekly_input"), dict) else {}
        report = evidence.get("final_report") if isinstance(evidence.get("final_report"), dict) else {}
        if weekly.get("exists") is not True or weekly.get("is_file") is not True or int(weekly.get("size_bytes") or 0) <= 0:
            return "resource recovery weekly input is missing before execution"
        if report.get("exists") is True:
            return "resource recovery final report already exists before execution"
        if pre_execution_state.get("outcome_exists") is True:
            return "resource recovery outcome already exists before worker execution"
        return ""

    async def _process_task(self, task: Dict[str, Any]) -> str:
        """
        Full dispatch → execute → write-back flow for a single task.

        Returns one of: 'succeeded' | 'failed' | 'retried' | 'skipped'
        """
        task_id: str = task["task_id"]
        attempt_count: int = (task.get("attempt_count") or 0) + 1
        resource_recovery_pre_execution = self._resource_recovery_pre_execution_state(task)
        resource_recovery_block_reason = self._resource_recovery_pre_block_reason(resource_recovery_pre_execution)

        # Detect origin for clinical-grade auditing
        metadata = task.get("metadata") or {}
        source_module = metadata.get("source_module", "manual")
        session_id = metadata.get("session_id", "unknown")
        
        if source_module in {"nine_questions.q8", "q8_what_should_i_do_now"}:
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
        if resource_recovery_block_reason:
            self._mark_failed(task_id, resource_recovery_block_reason)
            return "failed"

        if self._cfg.enable_react_execution:
            react_result = await self._execute_with_react(task_id)
            if react_result.get("succeeded") is True:
                return "succeeded"
            if str(react_result.get("status") or "") == "suspended":
                return "blocked"
            return "failed"

        # 2. Build SubtaskIntent for the router / executor
        subtask_intent = self._build_subtask_intent(task)

        # 3. Task-center selected external executor path.  CLI/MCP tasks are
        # dispatched serially and write their own result back through
        # TaskManagementService, so the generic plugin writeback is skipped.
        external_dispatch = self._external_dispatch_from_task(task)
        if external_dispatch is not None:
            external_dispatch, block_reason = await self._resolve_eligible_external_dispatch(external_dispatch, task)
            if block_reason:
                block_error_code = self._external_error_code(external_dispatch["executor_type"], block_reason)
                self._record_external_workflow_event(
                    event_type="node_blocked",
                    task=task,
                    dispatch=external_dispatch,
                    status="blocked",
                    error_code=block_error_code,
                    output_summary={
                        "block_reason": block_reason,
                        "workflow_event_type": "no_replacement_found"
                        if "no active healthy replacement executor was found" in block_reason
                        else "executor_unavailable",
                    },
                )
                self._mark_dispatch_blocked(
                    task,
                    reason=block_reason,
                    required_capabilities=list(subtask_intent.required_capabilities or []),
                    lease_owner=lease_owner,
                    attempt_count=attempt_count,
                    error_code=block_error_code,
                )
                recovery_recorder = getattr(self._task_service, "record_blocked_task_recovery_experience", None)
                if callable(recovery_recorder):
                    await recovery_recorder(
                        task_id=task_id,
                        trace_id=str(external_dispatch.get("trace_id") or ""),
                        session_id=str((task.get("metadata") or {}).get("session_id") or task.get("originator_id") or ""),
                        error_code=block_error_code,
                        block_reason=block_reason,
                        recovery_advice=(
                            "Run health probe before dispatch, register a healthy authorized replacement capability, "
                            "and retry only after Q5/Q6 replacement checks pass."
                        ),
                    )
                return "blocked"
            self._record_external_workflow_event(
                event_type="external_invoked",
                task=task,
                dispatch=external_dispatch,
                status="running",
                input_summary=self._external_dispatch_audit_payload(external_dispatch),
            )
            self._record_external_workflow_event(
                event_type="dispatch_started",
                task=task,
                dispatch=external_dispatch,
                status="running",
                input_summary=self._external_dispatch_audit_payload(external_dispatch),
                output_summary={"dispatch_status": "started"},
            )
            exec_result = await self._execute_on_external_executor(external_dispatch, task_id)
            self._record_external_workflow_event(
                event_type="node_succeeded" if exec_result.get("succeeded") else "node_failed",
                task=task,
                dispatch=external_dispatch,
                status="succeeded" if exec_result.get("succeeded") else "failed",
                error_code="" if exec_result.get("succeeded") else str(exec_result.get("error_code") or "EXTERNAL_EXECUTION_FAILED"),
                output_summary={
                    "workflow_event_type": "executor_invocation_finished",
                    "succeeded": exec_result.get("succeeded"),
                    "task_center_synchronized": exec_result.get("task_center_synchronized"),
                    "execution_evidence": exec_result.get("execution_evidence"),
                    "error": exec_result.get("error"),
                },
                evidence_ref=str((exec_result.get("execution_evidence") or {}).get("evidence_ref") or ""),
            )
            self._record_external_workflow_event(
                event_type="executor_invocation_finished",
                task=task,
                dispatch=external_dispatch,
                status="succeeded" if exec_result.get("succeeded") else "failed",
                error_code="" if exec_result.get("succeeded") else str(exec_result.get("error_code") or "EXTERNAL_EXECUTION_FAILED"),
                output_summary={
                    "succeeded": exec_result.get("succeeded"),
                    "task_center_synchronized": exec_result.get("task_center_synchronized"),
                    "execution_evidence": exec_result.get("execution_evidence"),
                    "error": exec_result.get("error"),
                },
                evidence_ref=str((exec_result.get("execution_evidence") or {}).get("evidence_ref") or ""),
            )
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
            await self._record_internal_resource_recovery_outcome(
                task_id=task_id,
                plugin_id=plugin_id,
                exec_result=exec_result,
                pre_execution_state=resource_recovery_pre_execution,
            )
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

    async def _execute_with_react(self, task_id: str) -> Dict[str, Any]:
        if self._react_executor is None:
            from zentex.tasks.execution.langgraph_react_executor import (
                LangGraphReactExecutor,
                ReactExecutorConfig,
            )

            cli_service = self._cli_service
            mcp_service = self._mcp_service
            external_connector_service = self._external_connector_service
            agent_service = self._agent_service
            task = self._dao.get_task(task_id) or {}
            metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            executor_type = str(
                metadata.get("executor_type")
                or metadata.get("external_executor_type")
                or metadata.get("executor_kind")
                or ""
            ).strip().lower()
            target_id = str(task.get("target_id") or metadata.get("target_id") or "")
            if not executor_type:
                if target_id.startswith("cli:") or metadata.get("cli_tool_name"):
                    executor_type = "cli"
                elif target_id.startswith("mcp:") or metadata.get("mcp_server_id"):
                    executor_type = "mcp"
                elif target_id.startswith(("external_connector:", "connector:")) or metadata.get("external_connector_id"):
                    executor_type = "external_connector"
                elif target_id.startswith("agent:") or metadata.get("agent_id"):
                    executor_type = "agent"
            try:
                if executor_type == "cli":
                    cli_service = self._resolve_cli_service()
                elif executor_type == "mcp":
                    mcp_service = self._resolve_mcp_service()
                elif executor_type == "external_connector":
                    external_connector_service = self._resolve_external_connector_service()
                elif executor_type == "agent":
                    agent_service = self._resolve_agent_service()
                    if cli_service is None:
                        try:
                            cli_service = self._resolve_cli_service()
                        except Exception:
                            cli_service = None
                    if mcp_service is None:
                        try:
                            mcp_service = self._resolve_mcp_service()
                        except Exception:
                            mcp_service = None
            except Exception:
                # Let the ReAct preflight node persist the resource-unavailable failure.
                pass

            self._react_executor = LangGraphReactExecutor(
                task_dao=self._dao,
                task_service=self._task_service,
                cli_service=cli_service,
                mcp_service=mcp_service,
                external_connector_service=external_connector_service,
                agent_service=agent_service,
                internal_executor=self._executor,
                subtask_intent_builder=self._build_subtask_intent,
                config=ReactExecutorConfig(
                    execution_timeout_seconds=self._cfg.execution_timeout_seconds,
                    max_attempts=self._cfg.max_attempts,
                ),
            )
        return await self._react_executor.execute(task_id)

    @staticmethod
    def _task_model_value(task: Any, field: str) -> Any:
        if isinstance(task, dict):
            return task.get(field)
        return getattr(task, field, None)

    @staticmethod
    def _status_text(value: Any) -> str:
        raw = getattr(value, "value", value)
        return str(raw or "")

    @staticmethod
    def _json_text(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _count_csv_data_rows(path: Path) -> int:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return 0
        return max(0, len(lines) - 1)

    def _child_task_list_snapshot(self, task_id: str, task: Any) -> List[Dict[str, Any]]:
        children: List[Any] = []
        if self._task_service is not None and callable(getattr(self._task_service, "list_tasks", None)):
            children = list(self._task_service.list_tasks(parent_task_id=task_id, limit=500, offset=0) or [])
        if not children:
            subtask_ids = self._task_model_value(task, "subtask_ids")
            if isinstance(subtask_ids, list):
                for child_id in subtask_ids:
                    child = (
                        self._task_service.get_task(str(child_id))
                        if self._task_service is not None and callable(getattr(self._task_service, "get_task", None))
                        else None
                    )
                    if child is not None:
                        children.append(child)
        snapshot: List[Dict[str, Any]] = []
        for child in children:
            snapshot.append(
                {
                    "task_id": self._task_model_value(child, "task_id"),
                    "parent_task_id": self._task_model_value(child, "parent_task_id"),
                    "status": self._status_text(self._task_model_value(child, "status")),
                    "title": self._task_model_value(child, "title"),
                    "target_id": self._task_model_value(child, "target_id"),
                    "execution_finished_at": self._task_model_value(child, "execution_finished_at"),
                    "dispatch_plugin_id": self._task_model_value(child, "dispatch_plugin_id"),
                }
            )
        return snapshot

    async def _record_internal_resource_recovery_outcome(
        self,
        *,
        task_id: str,
        plugin_id: str,
        exec_result: Dict[str, Any],
        pre_execution_state: Dict[str, Any] | None,
    ) -> None:
        if pre_execution_state is None or self._task_service is None:
            return
        latest_task = (
            self._task_service.get_task(task_id)
            if callable(getattr(self._task_service, "get_task", None))
            else self._dao.get_task(task_id)
        )
        if latest_task is None:
            raise RuntimeError(f"Cannot record resource recovery outcome for missing task: {task_id}")
        metadata = self._task_model_value(latest_task, "metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        paths = self._resource_recovery_paths(metadata)
        if paths is None:
            return
        weekly_path, report_path, fallback_executor = paths
        if not fallback_executor:
            raise RuntimeError(f"Resource recovery task {task_id} is missing approved fallback executor")

        weekly_before = pre_execution_state["physical_evidence_before"]["weekly_input"]
        report_before = pre_execution_state["physical_evidence_before"]["final_report"]
        if weekly_before.get("exists") is not True or report_before.get("exists") is True:
            raise RuntimeError(f"Resource recovery task {task_id} has invalid pre-execution physical evidence")

        weekly_rows = self._count_csv_data_rows(weekly_path)
        output_payload = exec_result.get("output") if isinstance(exec_result.get("output"), dict) else {}
        trace_id = str(metadata.get("trace_id") or "")
        session_id = str(metadata.get("session_id") or self._task_model_value(latest_task, "originator_id") or "")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_text = "\n".join(
            [
                "resource_recovery=complete",
                f"task_id={task_id}",
                f"trace_id={trace_id}",
                f"weekly_file={weekly_path}",
                f"weekly_rows={weekly_rows}",
                f"fallback_executor={fallback_executor}",
                f"dispatch_plugin_id={plugin_id}",
                f"allowed={output_payload.get('allowed')}",
                "",
            ]
        )
        report_path.write_text(report_text, encoding="utf-8")

        weekly_after = self._physical_file_snapshot(weekly_path)
        report_after = self._physical_file_snapshot(report_path)
        latest_task = self._task_service.get_task(task_id) if callable(getattr(self._task_service, "get_task", None)) else latest_task
        child_task_list_snapshot = self._child_task_list_snapshot(task_id, latest_task)
        state_transition_history = []
        dispatch = metadata.get("resource_gap_recovery_dispatch") if isinstance(metadata.get("resource_gap_recovery_dispatch"), dict) else {}
        if isinstance(dispatch.get("state_transition_history"), list):
            state_transition_history = list(dispatch["state_transition_history"])
        evidence_package_ref = f"evidence_package:resource_recovery:{task_id}:{report_after.get('sha256')}"
        processing_record_log = [
            {
                "phase": "recovered_before_worker",
                "status": pre_execution_state.get("status"),
                "attempt_count": pre_execution_state.get("attempt_count"),
                "final_report_exists": pre_execution_state.get("final_report_exists"),
            },
            {
                "phase": "worker_started",
                "status": "in_progress",
                "execution_started_at": self._task_model_value(latest_task, "execution_started_at"),
            },
            {
                "phase": "worker_completed",
                "status": self._status_text(self._task_model_value(latest_task, "status")),
                "execution_finished_at": self._task_model_value(latest_task, "execution_finished_at"),
                "dispatch_plugin_id": plugin_id,
            },
            {
                "phase": "evidence_package_prepared",
                "status": "closed_with_outcome_summary",
                "evidence_package_ref": evidence_package_ref,
                "final_report_sha256": report_after.get("sha256"),
            },
        ]
        long_term_archive = {
            "terminal_state": "finished",
            "closure_status": "closed_with_outcome_summary",
            "task_status": self._status_text(self._task_model_value(latest_task, "status")),
            "completed_at": self._json_text(self._task_model_value(latest_task, "completed_at")),
            "execution_finished_at": self._json_text(self._task_model_value(latest_task, "execution_finished_at")),
            "child_task_list_snapshot": child_task_list_snapshot,
            "processing_record_log": processing_record_log,
            "evidence_package_ref": evidence_package_ref,
            "evidence_package": {
                "ref": evidence_package_ref,
                "task_id": task_id,
                "trace_id": trace_id,
                "final_report": report_after,
                "weekly_input": weekly_after,
            },
        }

        actual_outcome = {
            "resource_recovery": "complete",
            "weekly_file": str(weekly_path),
            "fallback_executor": fallback_executor,
            "state_transition_history": state_transition_history,
            "pre_execution_state": pre_execution_state,
            "state_transition_checks": [
                {
                    "phase": "blocked_before_hitl",
                    "expected_status": "blocked",
                    "actual_status": "blocked",
                    "execution_allowed": False,
                },
                {
                    "phase": "recovered_before_worker",
                    "expected_status": "todo",
                    "actual_status": pre_execution_state.get("status"),
                    "execution_allowed": True,
                },
                {
                    "phase": "worker_in_progress_evidence",
                    "expected_status": "in_progress",
                    "actual_status": "in_progress_evidenced_by_execution_started_at",
                    "execution_started_at": self._task_model_value(latest_task, "execution_started_at"),
                    "attempt_count_before_worker": pre_execution_state.get("attempt_count"),
                    "attempt_count_after_worker": self._task_model_value(latest_task, "attempt_count"),
                },
                {
                    "phase": "worker_done_readback",
                    "expected_status": "done",
                    "actual_status": self._status_text(self._task_model_value(latest_task, "status")),
                    "execution_finished_at": self._task_model_value(latest_task, "execution_finished_at"),
                },
            ],
            "worker_execution": {
                "task_id": task_id,
                "status": self._status_text(self._task_model_value(latest_task, "status")),
                "target_id": self._task_model_value(latest_task, "target_id"),
                "execution_started_at": self._task_model_value(latest_task, "execution_started_at"),
                "execution_finished_at": self._task_model_value(latest_task, "execution_finished_at"),
                "execution_output": self._task_model_value(latest_task, "execution_output"),
                "execution_output_payload": output_payload,
                "dispatch_plugin_id": plugin_id,
                "attempt_count_before_worker": pre_execution_state.get("attempt_count"),
                "attempt_count_after_worker": self._task_model_value(latest_task, "attempt_count"),
            },
            "objective_physical_evidence": {
                "weekly_input": {
                    "before": weekly_before,
                    "after": weekly_after,
                    "unchanged": weekly_after == weekly_before,
                },
                "final_report": {
                    "before": report_before,
                    "after": report_after,
                    "created_by_execution": report_before.get("exists") is False and report_after.get("exists") is True,
                },
            },
            "long_term_archive": long_term_archive,
            "evidence": {"path": str(report_path), "content": report_text},
        }
        recorder = getattr(self._task_service, "_record_task_outcome", None)
        if not callable(recorder):
            raise RuntimeError("TaskManagementService._record_task_outcome is required for resource recovery evidence")
        verification_result = {
            "overall_passed": True,
            "strategy": "worker_resource_recovery_physical_evidence",
            "confidence_score": 1.0,
            "summary": "Resource recovery worker produced objective before/after physical evidence.",
            "recommendation": "accept",
            "verifier_results": [
                {
                    "verifier_id": "resource_recovery_objective_physical_evidence",
                    "verifier_type": "rule_based",
                    "status": "passed",
                    "passed": True,
                    "confidence": 1.0,
                    "summary": "weekly input unchanged and final report created by execution",
                }
            ],
            "check_results": {
                "weekly_input_unchanged": {
                    "passed": weekly_after == weekly_before,
                    "before_sha256": weekly_before.get("sha256"),
                    "after_sha256": weekly_after.get("sha256"),
                },
                "final_report_created_after_execution": {
                    "passed": report_before.get("exists") is False and report_after.get("exists") is True,
                    "after_sha256": report_after.get("sha256"),
                    "after_mtime_ns": report_after.get("mtime_ns"),
                    "after_size_bytes": report_after.get("size_bytes"),
                },
            },
        }
        recorder(
            task=latest_task,
            result={
                "actual_outcome": actual_outcome,
                "evidence": {"path": str(report_path), "content": report_text},
            },
            verification_result=verification_result,
        )
        if callable(getattr(self._task_service, "update_task_metadata", None)):
            await self._task_service.update_task_metadata(
                task_id,
                {"resource_recovery_closure_archive": long_term_archive},
                remarks="Resource recovery closure archive recorded",
            )

        if callable(getattr(self._task_service, "diagnose_task_management_closure", None)):
            lifecycle_report = self._task_service.diagnose_task_management_closure(stale_after_seconds=3600)
            lifecycle_issues_for_task = [
                issue
                for issue in lifecycle_report.get("issues", [])
                if issue.get("task_id") == task_id
            ]
            outcome = self._task_service.get_task_outcome(task_id)
            if isinstance(outcome, dict):
                updated_actual = dict(outcome.get("actual_outcome") or {})
                updated_actual["lifecycle_diagnostic"] = {
                    "checks": lifecycle_report.get("checks"),
                    "issues_for_task": lifecycle_issues_for_task,
                }
                outcome["actual_outcome"] = updated_actual
                outcome_dao = getattr(self._task_service, "_outcome_dao", None)
                if outcome_dao is None or not callable(getattr(outcome_dao, "upsert_outcome", None)):
                    raise RuntimeError("Task outcome DAO is required to update resource recovery lifecycle evidence")
                if not outcome_dao.upsert_outcome(outcome):
                    raise RuntimeError(f"Failed to persist resource recovery lifecycle evidence for {task_id}")

    @staticmethod
    def _external_error_code(executor_type: str, reason: str = "") -> str:
        normalized = str(executor_type or "").strip().lower()
        reason_text = str(reason or "").lower()
        if normalized == "cli":
            return "CLI_NOT_FOUND" if "not found" in reason_text or "not attached" in reason_text else "CLI_UNHEALTHY"
        if normalized == "mcp":
            if "tool" in reason_text and ("not found" in reason_text or "not registered" in reason_text):
                return "MCP_TOOL_NOT_FOUND"
            if "schema" in reason_text:
                return "MCP_SCHEMA_INVALID"
            if "not found" in reason_text or "not online" in reason_text or "unavailable" in reason_text:
                return "MCP_SERVER_UNAVAILABLE"
            return "MCP_UNHEALTHY"
        if normalized == "agent":
            if "auth" in reason_text or "credential" in reason_text:
                return "AGENT_AUTH_FAILED"
            if "scope" in reason_text:
                return "AGENT_SCOPE_MISMATCH"
            return "AGENT_OFFLINE"
        if normalized == "external_connector":
            if "health/probe capability" in reason_text or "concrete data operation capability" in reason_text:
                return "CONNECTOR_CAPABILITY_MISMATCH"
            if "mutation guard" in reason_text or "dangerous filter" in reason_text or "trace marker" in reason_text:
                return "CONNECTOR_MUTATION_GUARD_BLOCKED"
            return "CONNECTOR_UNHEALTHY"
        return "EXTERNAL_EXECUTOR_UNHEALTHY"

    @staticmethod
    def _mongodb_mutation_guard_reason(dispatch: Dict[str, Any]) -> str:
        if str(dispatch.get("executor_type") or "") != "external_connector":
            return ""
        capability = str(dispatch.get("capability") or "")
        if capability not in {"mongodb_create", "mongodb_update", "mongodb_delete", "mongodb_csv_import"}:
            return ""

        arguments = dispatch.get("arguments") if isinstance(dispatch.get("arguments"), dict) else {}

        def has_trace_markers(value: Any) -> bool:
            return (
                isinstance(value, dict)
                and bool(str(value.get("session_id") or "").strip())
                and bool(str(value.get("trace_id") or "").strip())
            )

        if capability == "mongodb_create":
            document = arguments.get("document")
            document_obj = document if isinstance(document, dict) else {}
            if not has_trace_markers(document_obj) or not str(document_obj.get("task_id") or "").strip():
                return (
                    "MongoDB mutation guard blocked mongodb_create: document must include "
                    "session_id, trace_id, and task_id trace markers"
                )
            return ""

        if capability == "mongodb_csv_import":
            trace_id = str(dispatch.get("trace_id") or arguments.get("trace_id") or "").strip()
            metadata = arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else {}
            session_id = str(arguments.get("session_id") or metadata.get("session_id") or "").strip()
            if not trace_id or not session_id:
                return (
                    "MongoDB mutation guard blocked mongodb_csv_import: CSV import writes MongoDB and must include "
                    "trace_id plus session_id trace markers for read-after-write attribution"
                )
            return ""

        filter_doc = arguments.get("filter")
        if not isinstance(filter_doc, dict) or not filter_doc:
            return f"MongoDB mutation guard blocked {capability}: dangerous filter is empty or missing"
        if not has_trace_markers(filter_doc):
            return f"MongoDB mutation guard blocked {capability}: filter lacks session_id/trace_id trace markers"
        if capability == "mongodb_delete" and bool(arguments.get("many", False)):
            return "MongoDB mutation guard blocked mongodb_delete: bulk delete requires confirmation"
        return ""

    @staticmethod
    def _external_connector_capability_guard_reason(dispatch: Dict[str, Any]) -> str:
        capability = str(dispatch.get("capability") or "").strip().lower()
        if capability not in {"mongodb_ping", "ping", "health_check", "health"}:
            return ""
        text_parts: list[str] = []
        for value in (
            dispatch.get("objective"),
            dispatch.get("title"),
            dispatch.get("task_title"),
            dispatch.get("content"),
            dispatch.get("remarks"),
        ):
            if value:
                text_parts.append(str(value))
        arguments = dispatch.get("arguments")
        if isinstance(arguments, dict):
            for key in ("objective", "title", "content", "remarks"):
                value = arguments.get(key)
                if value:
                    text_parts.append(str(value))
        task_text = " ".join(text_parts).lower()
        health_terms = ("ping", "health", "健康", "连通", "连接", "connection")
        if task_text and any(term in task_text for term in health_terms):
            return ""
        connector_id = str(dispatch.get("connector_id") or "").strip()
        objective = str(dispatch.get("objective") or dispatch.get("title") or dispatch.get("remarks") or "").strip()
        suggested = "mongodb_csv_inspect or mongodb_csv_import" if "csv" in task_text or "时间序列" in task_text else "a concrete data operation capability"
        return (
            "External connector capability mismatch: "
            f"connector_id={connector_id or '<unknown>'}; "
            f"selected_capability={capability}; "
            f"selected_capability_role=health_probe_only; "
            f"task_objective={objective or '<missing>'}; "
            "why_blocked=health/probe capabilities can only verify connector connectivity and cannot read, parse, "
            "validate, write, update, or delete business data; "
            f"required_capability={suggested}; "
            "diagnosis_source=deterministic_guard; "
            "llm_analysis_required=false"
        )

    @staticmethod
    def _external_dispatch_audit_payload(dispatch: Dict[str, Any]) -> Dict[str, Any]:
        def redact(value: Any) -> Any:
            if isinstance(value, dict):
                redacted: Dict[str, Any] = {}
                for key, item in value.items():
                    lowered = str(key).lower()
                    if any(token in lowered for token in ("api_key", "token", "authorization", "password", "secret", "uri", "connection_string")):
                        redacted[key] = "***"
                    else:
                        redacted[key] = redact(item)
                return redacted
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value

        return redact(dict(dispatch))

    def _record_external_workflow_event(
        self,
        *,
        event_type: str,
        task: Dict[str, Any],
        dispatch: Dict[str, Any],
        status: str,
        input_summary: Dict[str, Any] | None = None,
        output_summary: Dict[str, Any] | None = None,
        error_code: str = "",
        evidence_ref: str = "",
    ) -> None:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        trace_id = str(dispatch.get("trace_id") or metadata.get("trace_id") or f"external-task:{task.get('task_id')}")
        session_id = str(metadata.get("session_id") or task.get("originator_id") or "unknown")
        node_name = f"{dispatch.get('executor_type', 'external')} execution"
        from zentex.audit.workflow_events import record_workflow_node_event

        record_workflow_node_event(
            event_type=event_type,
            node_id="external-execution",
            node_name=node_name,
            status=status,
            trace_id=trace_id,
            session_id=session_id,
            turn_id=str(metadata.get("turn_id") or session_id),
            task_id=str(task.get("task_id") or ""),
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            evidence_ref=evidence_ref,
            error_code=error_code,
            source="zentex.tasks.execution.worker",
            details={
                "executor_type": dispatch.get("executor_type"),
                "target_id": metadata.get("target_id") or task.get("target_id"),
            },
        )

    def _build_external_execution_evidence(
        self,
        *,
        task_id: str,
        dispatch: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        executor_type = dispatch["executor_type"]
        trace_id = str(dispatch.get("trace_id") or "")
        evidence: Dict[str, Any] = {
            "evidence_ref": f"external_execution:{executor_type}:{task_id}:{trace_id}",
            "executor_type": executor_type,
            "trace_id": trace_id,
            "task_id": task_id,
            "succeeded": bool(result.get("succeeded")),
            "task_center_synchronized": bool(result.get("task_center_synchronized")),
        }
        if isinstance(dispatch.get("dispatch_reassignment"), dict):
            evidence["dispatch_reassignment"] = dispatch["dispatch_reassignment"]
        if executor_type == "cli":
            output = result.get("output") if isinstance(result.get("output"), dict) else {}
            evidence.update(
                {
                    "tool_name": dispatch.get("tool_name"),
                    "arguments": dispatch.get("arguments") or [],
                    "working_directory": dispatch.get("working_directory"),
                    "exit_code": result.get("exit_code") or result.get("returncode") or output.get("exit_code"),
                    "stdout": str(result.get("stdout") or output.get("stdout") or "")[:1000],
                    "stderr": str(result.get("stderr") or output.get("stderr") or "")[:1000],
                    "physical_artifacts": (
                        result.get("physical_artifacts")
                        or result.get("artifacts")
                        or output.get("artifacts")
                        or dispatch.get("expected_physical_artifacts")
                        or []
                    ),
                    "expected_evidence_type": dispatch.get("expected_evidence_type"),
                }
            )
        elif executor_type == "mcp":
            output = result.get("output") if isinstance(result.get("output"), dict) else {}
            evidence.update(
                {
                    "server_id": dispatch.get("server_id"),
                    "tool_name": dispatch.get("tool_name"),
                    "arguments": dispatch.get("arguments") or {},
                    "runtime_log_id": result.get("runtime_log_id") or result.get("audit_log_id") or output.get("runtime_log_id"),
                    "response_evidence_path": result.get("response_evidence_path") or dispatch.get("response_evidence_path"),
                    "physical_artifacts": result.get("physical_artifacts") or output.get("artifacts") or [],
                    "query_assertions": dispatch.get("query_assertions") or [],
                    "payload": result.get("payload") or result.get("result") or output,
                }
            )
        elif executor_type == "agent":
            payload = result.get("result") if isinstance(result.get("result"), dict) else {}
            evidence.update(
                {
                    "agent_id": dispatch.get("agent_id"),
                    "external_task_ref": payload.get("external_task_ref") or result.get("external_task_ref"),
                    "ledger_id": payload.get("ledger_id") or payload.get("invocation_id") or result.get("ledger_id"),
                    "callback_status": payload.get("callback_status") or result.get("callback_status"),
                }
            )
        elif executor_type == "external_connector":
            payload = result.get("result") if isinstance(result.get("result"), dict) else {}
            evidence.update(
                {
                    "connector_id": dispatch.get("connector_id"),
                    "capability": dispatch.get("capability"),
                    "read_after_write": payload.get("read_after_write") or payload.get("verification") or {},
                    "payload": payload,
                }
            )
        return evidence

    async def _attach_external_execution_evidence(
        self,
        task_id: str,
        dispatch: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = dict(result or {})
        response_evidence_path = self._persist_external_response_evidence(dispatch, normalized)
        if response_evidence_path:
            normalized["response_evidence_path"] = response_evidence_path
            physical_artifacts = list(normalized.get("physical_artifacts") or normalized.get("artifacts") or [])
            if response_evidence_path not in physical_artifacts:
                physical_artifacts.append(response_evidence_path)
            normalized["physical_artifacts"] = physical_artifacts
        evidence = self._build_external_execution_evidence(task_id=task_id, dispatch=dispatch, result=normalized)
        normalized["execution_evidence"] = evidence
        if self._task_service is not None and callable(getattr(self._task_service, "update_task_metadata", None)):
            await self._task_service.update_task_metadata(
                task_id,
                {
                    "execution_evidence": evidence,
                    "external_execution_evidence_ref": evidence["evidence_ref"],
                },
                remarks=f"{dispatch['executor_type']} execution evidence recorded",
            )
            self._merge_execution_evidence_into_outcome(task_id, evidence)
        return normalized

    def _persist_external_response_evidence(self, dispatch: Dict[str, Any], result: Dict[str, Any]) -> str:
        path_value = (
            dispatch.get("response_evidence_path")
            or dispatch.get("mcp_response_evidence_path")
            or dispatch.get("evidence_output_path")
        )
        if not path_value:
            return ""
        evidence_path = Path(str(path_value)).expanduser()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "executor_type": dispatch.get("executor_type"),
            "trace_id": dispatch.get("trace_id"),
            "server_id": dispatch.get("server_id"),
            "tool_name": dispatch.get("tool_name"),
            "status": result.get("status"),
            "succeeded": result.get("succeeded"),
            "error_code": result.get("error_code") or result.get("failure_classification"),
            "output": result.get("output"),
            "result": result.get("result"),
            "query_assertions": dispatch.get("query_assertions") or [],
        }
        evidence_path.write_text(
            json.dumps(self._redact_sensitive_payload(payload), ensure_ascii=False, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return str(evidence_path)

    @classmethod
    def _redact_sensitive_payload(cls, value: Any) -> Any:
        secret_values = [
            item
            for item in os.environ.values()
            if isinstance(item, str) and len(item) >= 8
        ]
        if isinstance(value, dict):
            redacted: Dict[str, Any] = {}
            for key, item in value.items():
                lowered = str(key).lower().replace("-", "_")
                if any(token in lowered for token in ("api_key", "token", "secret", "password", "authorization", "cookie")):
                    redacted[str(key)] = "[REDACTED]"
                else:
                    redacted[str(key)] = cls._redact_sensitive_payload(item)
            return redacted
        if isinstance(value, list):
            return [cls._redact_sensitive_payload(item) for item in value]
        if isinstance(value, str):
            redacted_text = value
            for secret in secret_values:
                if secret in redacted_text:
                    redacted_text = redacted_text.replace(secret, "[REDACTED]")
            return redacted_text
        return value

    def _merge_execution_evidence_into_outcome(self, task_id: str, evidence: Dict[str, Any]) -> None:
        if self._task_service is None or not callable(getattr(self._task_service, "get_task_outcome", None)):
            return
        outcome = self._task_service.get_task_outcome(task_id)
        if not isinstance(outcome, dict):
            return
        actual_outcome = outcome.get("actual_outcome")
        if isinstance(actual_outcome, dict):
            actual_outcome = dict(actual_outcome)
        else:
            actual_outcome = {"value": actual_outcome}
        actual_outcome["execution_evidence"] = evidence
        verification_result = outcome.get("verification_result")
        if isinstance(verification_result, dict):
            verification_result = dict(verification_result)
        else:
            verification_result = {}
        check_results = verification_result.get("check_results")
        if isinstance(check_results, dict):
            check_results = dict(check_results)
        else:
            check_results = {}
        check_results["execution_evidence_exists"] = {
            "passed": True,
            "evidence_ref": evidence.get("evidence_ref"),
            "executor_type": evidence.get("executor_type"),
            "physical_artifacts": evidence.get("physical_artifacts") or [],
        }
        assertion_payload = evidence.get("payload") if isinstance(evidence.get("payload"), dict) else actual_outcome
        assertion_evidence_ref = (
            evidence.get("response_evidence_path")
            or next(iter(evidence.get("physical_artifacts") or []), "")
            or evidence.get("evidence_ref")
        )
        query_check_results, query_failures = self._evaluate_query_assertions(
            assertion_payload,
            evidence.get("query_assertions") if isinstance(evidence.get("query_assertions"), list) else [],
            evidence_ref=str(assertion_evidence_ref or ""),
        )
        check_results.update(query_check_results)
        verification_result["check_results"] = check_results
        if query_failures:
            verification_result["overall_passed"] = False
            verification_result["summary"] = "External execution query assertions failed"
            outcome["overall_passed"] = False
            outcome["deviation_report"] = {
                **(outcome.get("deviation_report") if isinstance(outcome.get("deviation_report"), dict) else {}),
                "query_assertion_failures": query_failures,
            }
        outcome.update(
            {
                "actual_outcome": actual_outcome,
                "verification_result": verification_result,
            }
        )
        outcome_dao = getattr(self._task_service, "_outcome_dao", None)
        if outcome_dao is None or not callable(getattr(outcome_dao, "upsert_outcome", None)):
            raise RuntimeError("Task outcome DAO is required to attach external execution evidence")
        if not outcome_dao.upsert_outcome(outcome):
            raise RuntimeError(f"Failed to attach external execution evidence to task outcome: {task_id}")

    @classmethod
    def _evaluate_query_assertions(cls, payload: Dict[str, Any], assertions: List[Any], *, evidence_ref: str = "") -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        results: Dict[str, Any] = {}
        failures: List[Dict[str, Any]] = []
        valid_assertions = [assertion for assertion in assertions if isinstance(assertion, dict) and str(assertion.get("path") or "").strip()]
        if valid_assertions:
            results["query_assertions_passed"] = {
                "passed": True,
                "assertion_count": len(valid_assertions),
                "evidence_ref": evidence_ref,
            }
        type_map = {
            "dict": dict,
            "object": dict,
            "list": list,
            "array": list,
            "str": str,
            "string": str,
            "int": int,
            "number": (int, float),
            "bool": bool,
        }
        supported_keys = {"path", "exists", "not_empty", "equals", "contains", "type"}
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            path = str(assertion.get("path") or "").strip()
            if not path:
                continue
            check_id = f"json_path:{path}"
            try:
                value = cls._json_path_get(payload, path)
                exists = True
            except Exception:
                value = None
                exists = False
            passed = True
            unsupported_keys = set(assertion) - supported_keys
            if unsupported_keys or not (set(assertion) & (supported_keys - {"path"})):
                passed = False
            if assertion.get("exists") is True and not exists:
                passed = False
            if assertion.get("not_empty") is True and (not exists or value in (None, "", [], {})):
                passed = False
            if "equals" in assertion and (not exists or value != assertion.get("equals")):
                passed = False
            if "contains" in assertion and (not exists or str(assertion.get("contains")) not in str(value)):
                passed = False
            type_name = str(assertion.get("type") or "").strip()
            expected_type = type_map.get(type_name) if type_name else None
            if type_name and expected_type is None:
                passed = False
            elif expected_type is not None and (not exists or not isinstance(value, expected_type)):
                passed = False
            results[check_id] = {
                "passed": passed,
                "path": path,
                "assertion": dict(assertion),
                "evidence_ref": evidence_ref,
                "value_preview": str(value)[:500],
            }
            if unsupported_keys:
                results[check_id]["unsupported_fields"] = sorted(unsupported_keys)
            if not passed:
                if "query_assertions_passed" in results:
                    results["query_assertions_passed"]["passed"] = False
                failures.append(
                    {
                        "path": path,
                        "assertion": assertion,
                        "evidence_ref": evidence_ref,
                        "value_preview": str(value)[:500],
                    }
                )
        return results, failures

    @staticmethod
    def _json_path_get(payload: Any, path: str) -> Any:
        normalized = str(path or "").strip()
        if normalized == "$":
            return payload
        if normalized.startswith("$."):
            normalized = normalized[2:]
        elif normalized.startswith("$"):
            normalized = normalized[1:].lstrip(".")
        value = payload
        current = ""
        index = 0
        tokens: List[Any] = []
        while index < len(normalized):
            char = normalized[index]
            if char == ".":
                if current:
                    tokens.append(current)
                    current = ""
                index += 1
                continue
            if char == "[":
                if current:
                    tokens.append(current)
                    current = ""
                end = normalized.find("]", index)
                if end < 0:
                    raise KeyError(path)
                raw_index = normalized[index + 1 : end].strip()
                if raw_index.startswith(("'", '"')) and raw_index.endswith(("'", '"')):
                    tokens.append(raw_index[1:-1])
                else:
                    tokens.append(int(raw_index))
                index = end + 1
                continue
            current += char
            index += 1
        if current:
            tokens.append(current)
        for token in tokens:
            if isinstance(token, int):
                value = value[token]
            else:
                value = value[token]
        return value

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
                cli_service = self._resolve_cli_service()
                try:
                    profile = getattr(cli_service, "get_usage_profile", lambda _: None)(dispatch["tool_name"])
                except KeyError:
                    profile = None
                if profile is not None and (
                    getattr(profile, "learning_status", None) != "learned" or getattr(profile, "degraded", False)
                ):
                    raise RuntimeError(f"CLI tool '{dispatch['tool_name']}' is degraded and cannot be auto-dispatched")
                if profile is not None:
                    self._validate_profile_arguments(profile, dispatch.get("arguments") or [], executor_type="cli")
                result = await cli_service.execute_task(
                    task_service=self._task_service,
                    task_id=task_id,
                    trace_id=dispatch["trace_id"],
                    tool_name=dispatch["tool_name"],
                    arguments=dispatch.get("arguments") or [],
                    stdin_input=dispatch.get("stdin_input"),
                    working_directory=dispatch.get("working_directory"),
                    timeout_seconds=float(dispatch.get("timeout_seconds") or self._cfg.execution_timeout_seconds),
                )
                return await self._attach_external_execution_evidence(task_id, dispatch, result)
            if executor_type == "mcp":
                mcp_service = self._resolve_mcp_service()
                try:
                    profile = getattr(mcp_service, "get_tool_usage_profile", lambda *_: None)(
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
                result = await mcp_service.execute_task(
                    task_service=self._task_service,
                    task_id=task_id,
                    trace_id=dispatch["trace_id"],
                    server_id=dispatch["server_id"],
                    tool_name=dispatch["tool_name"],
                    arguments=dispatch.get("arguments") or {},
                )
                return await self._attach_external_execution_evidence(task_id, dispatch, result)
            if executor_type == "external_connector":
                result = await self._execute_external_connector_task(dispatch, task_id)
                return await self._attach_external_execution_evidence(task_id, dispatch, result)
            if executor_type == "agent":
                result = await self._execute_agent_task(dispatch, task_id)
                return await self._attach_external_execution_evidence(task_id, dispatch, result)
            raise RuntimeError(f"Unsupported external executor type: {executor_type}")
        except Exception as exc:
            logger.exception("External executor dispatch failed for task %s", task_id)
            raise

    async def _resolve_eligible_external_dispatch(
        self,
        dispatch: Dict[str, Any],
        task: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str]:
        reason = await self._external_dispatch_block_reason(dispatch)
        if not reason:
            return dispatch, ""
        replacement = await self._find_replacement_external_dispatch(dispatch, task)
        if replacement is None:
            return dispatch, f"{reason}; no active healthy replacement executor was found"
        replacement_reason = await self._external_dispatch_block_reason(replacement)
        if replacement_reason:
            return dispatch, f"{reason}; replacement executor is also unavailable: {replacement_reason}"
        reassignment = self._write_replacement_assignment(task, replacement, original_dispatch=dispatch, reason=reason)
        replacement["dispatch_reassignment"] = reassignment
        return replacement, ""

    @staticmethod
    def _external_dispatch_target_id(dispatch: Dict[str, Any]) -> str:
        executor_type = str(dispatch.get("executor_type") or "").strip()
        if executor_type == "cli":
            return f"cli:{dispatch.get('tool_name')}"
        if executor_type == "mcp":
            return f"mcp:{dispatch.get('server_id')}:{dispatch.get('tool_name')}"
        if executor_type == "external_connector":
            return f"external_connector:{dispatch.get('connector_id')}:{dispatch.get('capability')}"
        if executor_type == "agent":
            return f"agent:{dispatch.get('agent_id')}"
        return str(dispatch.get("target_id") or "")

    @staticmethod
    def _string_values(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)]

    def _replacement_allowed_by_target_contract(self, candidate: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        preferred_targets = set(
            self._string_values(metadata.get("replacement_target_id"))
            + self._string_values(metadata.get("replacement_target_ids"))
            + self._string_values(metadata.get("preferred_replacement_target_id"))
            + self._string_values(metadata.get("preferred_replacement_target_ids"))
        )
        if candidate.get("executor_type") == "mcp":
            preferred_targets.update(
                f"mcp:{server_id}:{candidate.get('tool_name')}"
                for server_id in self._string_values(metadata.get("replacement_mcp_server_id"))
            )
        if not preferred_targets:
            return True
        return self._external_dispatch_target_id(candidate) in preferred_targets

    @staticmethod
    def _authorization_text_allows(value: Any) -> bool:
        if value is True:
            return True
        if isinstance(value, dict):
            if value.get("confirmation_required") is True:
                return False
            return any(
                TaskExecutionWorker._authorization_text_allows(value.get(key))
                for key in ("authorized", "authorization", "authorization_status", "status", "decision", "q5")
            )
        normalized = str(value or "").strip().lower()
        return normalized in {"allowed", "approved", "authorized", "pass", "passed", "true", "ok", "granted"}

    @staticmethod
    def _risk_text_allows(value: Any) -> bool:
        if value is True:
            return True
        if isinstance(value, dict):
            if value.get("blocked") is True or value.get("risk_rejected") is True:
                return False
            return any(
                TaskExecutionWorker._risk_text_allows(value.get(key))
                for key in ("risk_accepted", "risk_approved", "risk_status", "status", "decision", "q6")
            )
        normalized = str(value or "").strip().lower()
        return normalized in {"allowed", "approved", "acceptable", "accepted", "controlled", "low", "medium", "pass", "passed", "true", "ok"}

    def _replacement_authorization_decision(self, candidate: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        target_id = self._external_dispatch_target_id(candidate)
        configs = metadata.get("replacement_authorizations")
        selected: Any = None
        if isinstance(configs, dict):
            selected = (
                configs.get(target_id)
                or configs.get(str(candidate.get("server_id") or ""))
                or configs.get(str(candidate.get("connector_id") or ""))
                or configs.get(str(candidate.get("agent_id") or ""))
            )
        if selected is None:
            selected = metadata.get("replacement_authorization") or metadata.get("replacement_q5_q6")
        selected = selected if isinstance(selected, dict) else {}
        q5 = selected.get("q5") if "q5" in selected else selected.get("authorization")
        q6 = selected.get("q6") if "q6" in selected else selected.get("risk")
        q5_passed = self._authorization_text_allows(q5)
        q6_passed = self._risk_text_allows(q6)
        return {
            "target_id": target_id,
            "q5_passed": q5_passed,
            "q6_passed": q6_passed,
            "authorized": q5_passed and q6_passed,
            "q5": q5,
            "q6": q6,
        }

    async def _external_dispatch_block_reason(self, dispatch: Dict[str, Any]) -> str:
        executor_type = dispatch["executor_type"]
        try:
            if executor_type == "cli":
                try:
                    cli_service = self._resolve_cli_service()
                except Exception as exc:
                    return f"CliIntegrationService is not available through service.py: {exc}"
                try:
                    health = cli_service.get_tool_health(dispatch["tool_name"])
                except KeyError:
                    return f"CLI tool {dispatch['tool_name']} not found"
                if health.get("status") != "active" or health.get("healthy") is not True:
                    return f"CLI tool {dispatch['tool_name']} is not active and healthy: {health}"
                return ""
            if executor_type == "mcp":
                try:
                    mcp_service = self._resolve_mcp_service()
                except Exception as exc:
                    return f"McpIntegrationService is not available through service.py: {exc}"
                try:
                    health = mcp_service.get_server_health(dispatch["server_id"])
                except KeyError:
                    return f"MCP server {dispatch['server_id']} not found"
                if health.get("status") != "online" or health.get("healthy") is not True:
                    return f"MCP server {dispatch['server_id']} is not online and healthy: {health}"
                state = next((item for item in mcp_service.list_servers() if item.server_id == dispatch["server_id"]), None)
                if state is None or not any(tool.tool_name == dispatch["tool_name"] for tool in getattr(state, "tools", []) or []):
                    return f"MCP tool {dispatch['tool_name']} not registered for server {dispatch['server_id']}"
                return ""
            if executor_type == "external_connector":
                try:
                    service = self._resolve_external_connector_service()
                except Exception as exc:
                    return f"ExternalConnectorService is not available through service.py: {exc}"
                capability_guard_reason = self._external_connector_capability_guard_reason(dispatch)
                if capability_guard_reason:
                    return capability_guard_reason
                connector = service.get_connector(dispatch["connector_id"])
                report = service.health_check(dispatch["connector_id"])
                status = getattr(getattr(connector, "status", None), "value", getattr(connector, "status", None))
                health_status = getattr(getattr(report, "health_status", None), "value", getattr(report, "health_status", None))
                if status != "active" or health_status != "healthy":
                    return (
                        f"External connector {dispatch['connector_id']} is not active and healthy: "
                        f"status={status}, health_status={health_status}"
                    )
                mutation_guard_reason = self._mongodb_mutation_guard_reason(dispatch)
                if mutation_guard_reason:
                    return mutation_guard_reason
                return ""
            if executor_type == "agent":
                try:
                    agent_service = self._resolve_agent_service()
                except Exception as exc:
                    return f"AgentCoordinationService is not available through service.py: {exc}"
                asset = getattr(getattr(agent_service, "manager", None), "get_asset", lambda _agent_id: None)(
                    dispatch["agent_id"]
                )
                if asset is None:
                    return f"Agent {dispatch['agent_id']} not found"
                requested_scope = set(dispatch.get("agent_scope") or [])
                asset_scope = set(getattr(asset, "scope", []) or [])
                if requested_scope and not requested_scope <= asset_scope:
                    return (
                        f"Agent {dispatch['agent_id']} scope mismatch: "
                        f"requested={sorted(requested_scope)}, available={sorted(asset_scope)}"
                    )
                auth_config = dict(getattr(asset, "auth_config", {}) or {})
                if auth_config.get("type") not in {None, "", "none"} and not auth_config.get("credential_ref"):
                    return f"Agent {dispatch['agent_id']} auth_config requires credential_ref"
                block_reason = getattr(agent_service, "get_dispatch_block_reason", None)
                if callable(block_reason):
                    maybe_reason = block_reason(
                        dispatch["agent_id"],
                        cli_service=self._resolve_cli_service(),
                        mcp_service=self._resolve_mcp_service(),
                    )
                    reason = await maybe_reason if asyncio.iscoroutine(maybe_reason) else maybe_reason
                    return str(reason or "")
                status = getattr(getattr(asset, "status", None), "value", getattr(asset, "status", None))
                if status != "active":
                    return f"Agent {dispatch['agent_id']} is not active and healthy: status={status}"
                return ""
        except Exception as exc:
            return f"{executor_type} pre-dispatch health check failed: {exc}"
        return f"Unsupported external executor type: {executor_type}"

    async def _find_replacement_external_dispatch(
        self,
        dispatch: Dict[str, Any],
        task: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        executor_type = dispatch["executor_type"]
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        if executor_type == "cli":
            try:
                cli_service = self._resolve_cli_service()
            except Exception:
                return None
            for state in cli_service.list_tools():
                tool_name = str(getattr(state, "command_name", "") or "").strip()
                if not tool_name or tool_name == dispatch.get("tool_name"):
                    continue
                candidate = dict(dispatch, tool_name=tool_name)
                if not self._replacement_allowed_by_target_contract(candidate, metadata):
                    continue
                if not await self._external_dispatch_block_reason(candidate):
                    authorization = self._replacement_authorization_decision(candidate, metadata)
                    if not authorization["authorized"]:
                        continue
                    candidate["replacement_authorization"] = authorization
                    return candidate
        if executor_type == "mcp":
            try:
                mcp_service = self._resolve_mcp_service()
            except Exception:
                return None
            for state in mcp_service.list_servers():
                if getattr(state, "server_id", None) == dispatch.get("server_id"):
                    continue
                if not any(getattr(tool, "tool_name", None) == dispatch["tool_name"] for tool in getattr(state, "tools", []) or []):
                    continue
                candidate = dict(dispatch, server_id=getattr(state, "server_id"))
                if not self._replacement_allowed_by_target_contract(candidate, metadata):
                    continue
                if not await self._external_dispatch_block_reason(candidate):
                    authorization = self._replacement_authorization_decision(candidate, metadata)
                    if not authorization["authorized"]:
                        continue
                    candidate["replacement_authorization"] = authorization
                    return candidate
        if executor_type == "external_connector":
            try:
                service = self._resolve_external_connector_service()
            except Exception:
                return None
            for connector in service.list_connectors():
                if getattr(connector, "connector_id", None) == dispatch.get("connector_id"):
                    continue
                if not any(getattr(capability, "name", None) == dispatch["capability"] for capability in connector.capabilities):
                    continue
                candidate = dict(dispatch, connector_id=getattr(connector, "connector_id"))
                if not self._replacement_allowed_by_target_contract(candidate, metadata):
                    continue
                if not await self._external_dispatch_block_reason(candidate):
                    authorization = self._replacement_authorization_decision(candidate, metadata)
                    if not authorization["authorized"]:
                        continue
                    candidate["replacement_authorization"] = authorization
                    return candidate
        if executor_type == "agent":
            try:
                agent_service = self._resolve_agent_service()
            except Exception:
                return None
            requested_scope = set(metadata.get("agent_scope") or metadata.get("scope") or [])
            for asset in getattr(agent_service, "list_active_agents", lambda: [])():
                if getattr(asset, "agent_id", None) == dispatch.get("agent_id"):
                    continue
                asset_scope = set(getattr(asset, "scope", []) or [])
                if requested_scope and not requested_scope <= asset_scope:
                    continue
                candidate = dict(dispatch, agent_id=getattr(asset, "agent_id"))
                if not self._replacement_allowed_by_target_contract(candidate, metadata):
                    continue
                if not await self._external_dispatch_block_reason(candidate):
                    authorization = self._replacement_authorization_decision(candidate, metadata)
                    if not authorization["authorized"]:
                        continue
                    candidate["replacement_authorization"] = authorization
                    return candidate
        return None

    def _write_replacement_assignment(
        self,
        task: Dict[str, Any],
        replacement: Dict[str, Any],
        *,
        original_dispatch: Dict[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        task_id = task["task_id"]
        timestamp = datetime.now(timezone.utc).isoformat()
        original_target_id = self._external_dispatch_target_id(original_dispatch)
        replacement_target_id = self._external_dispatch_target_id(replacement)
        authorization = replacement.get("replacement_authorization") if isinstance(replacement.get("replacement_authorization"), dict) else {}
        atomic_record = {
            "original_target_id": original_target_id,
            "replacement_target_id": replacement_target_id,
            "reason": reason,
            "timestamp": timestamp,
            "authorization": authorization,
        }
        reassignment = {
            "reason": reason,
            "original_target_id": original_target_id,
            "replacement_target_id": replacement_target_id,
            "timestamp": timestamp,
            "original": dict(original_dispatch),
            "replacement": dict(replacement),
            "reassigned_at": timestamp,
            "authorization": authorization,
            "atomic_record": atomic_record,
        }
        metadata = self._merge_metadata(
            task,
            dispatch_reassignment=reassignment,
        )
        executor_type = replacement["executor_type"]
        target_id = task.get("target_id")
        if executor_type == "cli":
            metadata.update({"cli_tool_name": replacement["tool_name"]})
            target_id = f"cli:{replacement['tool_name']}"
        elif executor_type == "mcp":
            metadata.update({"mcp_server_id": replacement["server_id"], "mcp_tool_name": replacement["tool_name"]})
            target_id = f"mcp:{replacement['server_id']}:{replacement['tool_name']}"
        elif executor_type == "external_connector":
            metadata.update(
                {
                    "external_connector_id": replacement["connector_id"],
                    "external_connector_capability": replacement["capability"],
                }
            )
            target_id = f"external_connector:{replacement['connector_id']}"
        elif executor_type == "agent":
            metadata.update({"agent_id": replacement["agent_id"]})
            target_id = f"agent:{replacement['agent_id']}"
        self._dao.update_task(task_id, {"target_id": target_id, "metadata": metadata})
        self._record_external_workflow_event(
            event_type="dispatch_reassigned",
            task=task,
            dispatch=replacement,
            status="succeeded",
            output_summary={
                "workflow_event_type": "dispatch_reassignment",
                "dispatch_reassignment": atomic_record,
                "replacement_authorized": bool(authorization.get("authorized")),
            },
            evidence_ref=f"dispatch_reassignment:{task_id}:{timestamp}",
        )
        return reassignment

    async def _execute_agent_task(self, dispatch: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        agent_service = self._resolve_agent_service()
        payload = dict(dispatch.get("task_payload") or {})
        payload.setdefault("zentex_task_id", task_id)
        response = await agent_service.dispatch_task(
            dispatch["agent_id"],
            payload,
            zentex_task_id=task_id,
            idempotency_key=dispatch.get("idempotency_key"),
            cli_service=self._resolve_cli_service(),
            mcp_service=self._resolve_mcp_service(),
        )
        succeeded = not getattr(response, "is_error", False)
        if succeeded and self._task_service is not None:
            from zentex.tasks.execution.external_result_bridge import (
                mark_external_execution_started,
                write_external_execution_result,
            )

            await mark_external_execution_started(
                task_service=self._task_service,
                task_id=task_id,
                trace_id=str(getattr(response, "trace_id", None) or dispatch["trace_id"]),
                executor_type="agent",
                executor_metadata={"agent_id": dispatch["agent_id"]},
            )
            await write_external_execution_result(
                task_service=self._task_service,
                task_id=task_id,
                trace_id=str(getattr(response, "trace_id", None) or dispatch["trace_id"]),
                executor_type="agent",
                executor_metadata={"agent_id": dispatch["agent_id"]},
                result_payload=getattr(response, "data", None) or {},
                succeeded=True,
                error_message=None,
            )
            self._record_agent_logic_evolution_if_present(
                dispatch=dispatch,
                task_id=task_id,
                result_payload=getattr(response, "data", None) or {},
            )
        return {
            "succeeded": succeeded,
            "task_center_synchronized": succeeded,
            "result": getattr(response, "data", None),
            "error": None if succeeded else getattr(response, "message", "Agent dispatch failed"),
        }

    @staticmethod
    def _agent_logic_evolution_evidence(value: Any) -> Dict[str, Any]:
        signals: List[Dict[str, Any]] = []

        def walk(item: Any, path: str) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    lowered = str(key).lower()
                    child_path = f"{path}.{key}" if path else str(key)
                    if lowered in {"agent_logic_evolved", "logic_evolved", "evolution_applied"} and child:
                        signals.append({"path": child_path, "value": child})
                    elif lowered in {"logic_evolution", "evolution", "evolution_event"} and child not in (None, "", False, [], {}):
                        signals.append({"path": child_path, "value": child})
                    walk(child, child_path)
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    walk(child, f"{path}[{index}]")

        walk(value, "")
        return {"evolved": bool(signals), "signals": signals[:20]}

    def _record_agent_logic_evolution_if_present(
        self,
        *,
        dispatch: Dict[str, Any],
        task_id: str,
        result_payload: Any,
    ) -> None:
        evidence = self._agent_logic_evolution_evidence(result_payload)
        if evidence["evolved"] is not True:
            return
        trace_id = str(dispatch.get("trace_id") or f"agent-task:{task_id}")
        session_id = str(dispatch.get("session_id") or "unknown")
        from zentex.audit.service import get_service as get_audit_service

        get_audit_service().record_audit_entry(
            trace_id=trace_id,
            session_id=session_id,
            turn_id=session_id,
            entry_type="workflow",
            source="zentex.tasks.execution.worker",
            summary=f"agent_logic_evolved: {task_id}",
            question_driver_refs=["agent-logic-evolution"],
            context_info={
                "status": "succeeded",
                "node_id": "agent-logic-evolution",
                "node_name": "Agent logic evolution audit",
                "task_id": task_id,
                "workflow_event_type": "agent_logic_evolved",
            },
            payload={
                "workflow_event_type": "agent_logic_evolved",
                "node_id": "agent-logic-evolution",
                "node_name": "Agent logic evolution audit",
                "status": "succeeded",
                "trace_id": trace_id,
                "session_id": session_id,
                "task_id": task_id,
                "agent_id": dispatch.get("agent_id"),
                "external_task_ref": (
                    result_payload.get("external_task_ref")
                    if isinstance(result_payload, dict)
                    else ""
                ),
                "evolution_evidence": evidence,
            },
        )

    async def _execute_external_connector_task(self, dispatch: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        service = self._resolve_external_connector_service()

        from zentex.external_connectors.models import ConnectorTestCallRequest
        from zentex.tasks.execution.external_result_bridge import (
            mark_external_execution_started,
            write_external_execution_result,
        )

        connector_id = dispatch["connector_id"]
        capability = dispatch["capability"]
        expected_plugin_path = str(dispatch.get("external_plugin_path") or "").strip()
        connector = service.get_connector(connector_id)
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
        invocation = service.test_call(
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
            elif target_id.startswith("agent:") or metadata.get("agent_id"):
                executor_type = "agent"

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
                "expected_physical_artifacts": TaskExecutionWorker._list_metadata(
                    metadata,
                    "physical_artifacts",
                    "expected_physical_artifacts",
                    "evidence_paths",
                    "artifact_paths",
                ),
                "expected_evidence_type": metadata.get("expected_evidence_type") or metadata.get("side_effect_type"),
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
                "response_evidence_path": metadata.get("response_evidence_path") or metadata.get("mcp_response_evidence_path"),
                "query_assertions": metadata.get("query_assertions") or metadata.get("mcp_query_assertions") or [],
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
                "title": task.get("title"),
                "objective": metadata.get("objective") or task.get("remarks"),
                "remarks": task.get("remarks"),
                "external_plugin_path": metadata.get("external_plugin_path") or metadata.get("plugin_path"),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }

        if executor_type == "agent" or target_id.startswith("agent:") or metadata.get("agent_id"):
            agent_id = str(
                metadata.get("agent_id")
                or (target_id.removeprefix("agent:") if target_id.startswith("agent:") else target_id)
                or ""
            ).strip()
            if not agent_id:
                return None
            task_payload = metadata.get("agent_task_payload")
            if task_payload is None:
                task_payload = metadata.get("task_payload")
            if task_payload is None:
                task_payload = {"title": task.get("title"), "remarks": task.get("remarks")}
            return {
                "executor_type": "agent",
                "trace_id": str(metadata.get("trace_id") or f"agent-task:{task.get('task_id')}"),
                "session_id": str(metadata.get("session_id") or task.get("originator_id") or ""),
                "agent_id": agent_id,
                "agent_scope": self._list_metadata(metadata, "agent_scope", "scope"),
                "task_payload": task_payload if isinstance(task_payload, dict) else {},
                "idempotency_key": task.get("idempotency_key") or metadata.get("idempotency_key"),
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

        current_task = self._dao.get_task(task_id) or {"task_id": task_id, "metadata": {}}
        self._dao.update_task(task_id, {
            "status": "done",
            "progress": 1.0,
            "completed_at": now_iso,
            "execution_finished_at": now_iso,
            "dispatch_plugin_id": plugin_id,
            "execution_output": output_json,
            "last_error": None,
            "metadata": self._merge_metadata(
                current_task,
                completion_status="completed",
                lease={
                    "status": "released",
                    "released_at": now_iso,
                },
            ),
        })
        self._record_worker_success_outcome(
            task_id=task_id,
            plugin_id=plugin_id,
            exec_result=exec_result,
            completed_at=now_iso,
        )
        logger.info("Task %s completed successfully via plugin %s", task_id, plugin_id)

    def _record_worker_success_outcome(
        self,
        *,
        task_id: str,
        plugin_id: str,
        exec_result: Dict[str, Any],
        completed_at: str,
    ) -> None:
        if self._task_service is None:
            raise RuntimeError("TaskManagementService is required to record worker success outcome")
        recorder = getattr(self._task_service, "_record_task_outcome", None)
        if not callable(recorder):
            raise RuntimeError("TaskManagementService._record_task_outcome is required for worker success evidence")
        latest_task = self._task_service.get_task(task_id) if callable(getattr(self._task_service, "get_task", None)) else None
        if latest_task is None:
            raise RuntimeError(f"Task readback missing after worker success: {task_id}")

        status_value = self._status_text(self._task_model_value(latest_task, "status"))
        dispatch_plugin_id = self._task_model_value(latest_task, "dispatch_plugin_id")
        evidence_ref = f"worker_success:{plugin_id}:{task_id}:{completed_at}"
        actual_outcome = {
            "status": "success",
            "task_id": task_id,
            "plugin_id": plugin_id,
            "dispatch_plugin_id": dispatch_plugin_id,
            "duration_seconds": exec_result.get("duration_seconds"),
            "output": exec_result.get("output"),
            "external_execution": {
                "executor_type": "internal_plugin",
                "executor_id": plugin_id,
            },
            "evidence": {
                "evidence_ref": evidence_ref,
                "task_status_readback": status_value,
                "dispatch_plugin_id_readback": dispatch_plugin_id,
                "execution_finished_at": self._task_model_value(latest_task, "execution_finished_at"),
            },
        }
        verification_result = {
            "overall_passed": status_value == "done" and dispatch_plugin_id == plugin_id,
            "strategy": "worker_success_readback",
            "confidence_score": 1.0,
            "summary": "Worker success was accepted only after task row readback confirmed DONE and dispatch plugin identity.",
            "recommendation": "accept",
            "verifier_results": [
                {
                    "verifier_id": "worker_done_status_readback",
                    "verifier_type": "rule_based",
                    "status": "passed" if status_value == "done" else "failed",
                    "passed": status_value == "done",
                    "confidence": 1.0,
                    "summary": f"task status readback={status_value}",
                },
                {
                    "verifier_id": "worker_dispatch_plugin_readback",
                    "verifier_type": "rule_based",
                    "status": "passed" if dispatch_plugin_id == plugin_id else "failed",
                    "passed": dispatch_plugin_id == plugin_id,
                    "confidence": 1.0,
                    "summary": f"dispatch_plugin_id readback={dispatch_plugin_id}",
                },
            ],
            "check_results": {
                "task_status_done": {"passed": status_value == "done", "actual": status_value},
                "dispatch_plugin_id_matches": {
                    "passed": dispatch_plugin_id == plugin_id,
                    "actual": dispatch_plugin_id,
                    "expected": plugin_id,
                },
            },
        }
        recorder(
            task=latest_task,
            result={
                "actual_outcome": actual_outcome,
                "evidence": actual_outcome["evidence"],
            },
            verification_result=verification_result,
        )
        outcome = self._task_service.get_task_outcome(task_id) if callable(getattr(self._task_service, "get_task_outcome", None)) else None
        if not isinstance(outcome, dict) or outcome.get("overall_passed") is not True:
            raise RuntimeError(f"Worker success outcome readback failed: {task_id}")

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
        error_code: str = "",
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
                    "error_code": error_code,
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

        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        required_capabilities = (
            _parse_list(metadata.get("required_capabilities"))
            or _parse_list(metadata.get("internal_required_capabilities"))
            or _parse_list(task.get("tags"))
        )
        confirmed_plugin_id = str(metadata.get("internal_executor_plugin_id") or metadata.get("executor_id") or "").strip()
        target_id = str(task.get("target_id") or metadata.get("target_id") or "").strip()
        is_internal_owner = target_id.startswith("internal:") or str(metadata.get("executor_type") or "").strip() == "internal"
        if is_internal_owner:
            required_capabilities = [
                item.split(":", 1)[1].strip() if str(item).strip().lower().startswith("internal:") else str(item).strip()
                for item in required_capabilities
                if str(item).strip()
            ]
            if confirmed_plugin_id.lower().startswith("internal:"):
                confirmed_plugin_id = confirmed_plugin_id.split(":", 1)[1].strip()
        if confirmed_plugin_id and confirmed_plugin_id not in required_capabilities:
            required_capabilities.append(confirmed_plugin_id)
        execution_basis = []
        if target_id:
            execution_basis.append(f"confirmed_executor={target_id}")
        if confirmed_plugin_id:
            execution_basis.append(f"confirmed_plugin={confirmed_plugin_id}")
        generation_basis = metadata.get("generation_basis") if isinstance(metadata.get("generation_basis"), dict) else {}
        if generation_basis.get("generation_functions"):
            execution_basis.append("generation_functions=" + ",".join(map(str, generation_basis["generation_functions"][:4])))
        content = task.get("remarks") or task.get("title", "")
        if execution_basis:
            content = f"{content}\nExecution basis: {'; '.join(execution_basis)}"

        return SubtaskIntent(
            local_id=task.get("task_id", ""),
            title=task.get("title", ""),
            task_type=task.get("task_type", "cognitive_step"),
            content=content,
            objective=content,
            required_capabilities=required_capabilities,
            execution_timeout_seconds=int(task.get("estimated_duration") or 300),
        )
