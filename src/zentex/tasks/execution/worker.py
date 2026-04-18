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

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
            "skipped=%d retried=%d duration_ms=%d",
            stats.tasks_dispatched,
            stats.tasks_succeeded,
            stats.tasks_failed,
            stats.tasks_skipped,
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
        try:
            candidates = self._dao.list_tasks(
                status="todo",
                limit=self._cfg.batch_size,
            )
        except Exception as exc:
            logger.error("TaskExecutionWorker: failed to fetch TODO tasks: %s", exc)
            return []

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
                    depends_on = []

            if depends_on:
                if not self._all_deps_done(depends_on):
                    continue

            ready.append(task)

        return ready

    def _all_deps_done(self, dep_ids: List[str]) -> bool:
        """Return True only if every dependency task has status 'done'."""
        for dep_id in dep_ids:
            try:
                dep = self._dao.get_task(dep_id)
                if dep is None or dep.get("status") != "done":
                    return False
            except Exception as exc:
                logger.warning("Could not fetch dependency %s: %s", dep_id, exc)
                return False
        return True

    async def _process_task(self, task: Dict[str, Any]) -> str:
        """
        Full dispatch → execute → write-back flow for a single task.

        Returns one of: 'succeeded' | 'failed' | 'retried' | 'skipped'
        """
        task_id: str = task["task_id"]
        attempt_count: int = (task.get("attempt_count") or 0) + 1

        # 1. Mark IN_PROGRESS and increment attempt count
        now_iso = datetime.now(timezone.utc).isoformat()
        self._dao.update_task(task_id, {
            "status": "in_progress",
            "attempt_count": attempt_count,
            "execution_started_at": now_iso,
            "started_at": task.get("started_at") or now_iso,
        })

        # 2. Build SubtaskIntent for the router / executor
        subtask_intent = self._build_subtask_intent(task)

        # 3. Get dispatch decision from the router
        decision = None
        try:
            if self._router is not None:
                decision = await self._router.get_dispatch_decision(subtask_intent)
        except Exception as exc:
            logger.warning(
                "Router failed for task %s: %s — will try internal executor directly",
                task_id, exc,
            )

        # 4. Execute on the selected plugin
        if decision is not None:
            plugin_id = decision.selected_executor.executor_id
        else:
            # Fallback: try to match a plugin directly without routing
            plugin_id = await self._direct_plugin_match(subtask_intent)

        if not plugin_id:
            logger.warning("No plugin found for task %s — skipping", task_id)
            self._dao.update_task(task_id, {
                "status": "todo",           # put back to queue
                "last_error": "No matching plugin found for task capabilities",
            })
            return "skipped"

        exec_result = await self._execute_on_plugin(plugin_id, subtask_intent, task_id)

        # 5. Write result back to DB
        if exec_result.get("succeeded"):
            self._write_success(task_id, plugin_id, exec_result)
            self._update_router_credit(decision, plugin_id, succeeded=True,
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
                })
                self._update_router_credit(decision, plugin_id, succeeded=False,
                                           duration=exec_result.get("duration_seconds", 0))
                logger.info(
                    "Task %s attempt %d failed, will retry (max=%d): %s",
                    task_id, attempt_count, self._cfg.max_attempts, error_msg,
                )
                return "retried"
            else:
                self._mark_failed(task_id, error_msg, plugin_id=plugin_id)
                self._update_router_credit(decision, plugin_id, succeeded=False,
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
                output_json = json.dumps({"raw": str(output)})

        self._dao.update_task(task_id, {
            "status": "done",
            "progress": 1.0,
            "completed_at": now_iso,
            "execution_finished_at": now_iso,
            "dispatch_plugin_id": plugin_id,
            "execution_output": output_json,
            "last_error": None,
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
        }
        if plugin_id:
            updates["dispatch_plugin_id"] = plugin_id
        try:
            self._dao.update_task(task_id, updates)
        except Exception as exc:
            logger.error("Failed to mark task %s as failed: %s", task_id, exc)
        logger.error("Task %s permanently failed: %s", task_id, error_msg)

    def _update_router_credit(
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
                record_fn(result)
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
