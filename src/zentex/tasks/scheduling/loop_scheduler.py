from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskAutoLoopScheduler:
    """Background scheduler for task lifecycle maintenance AND execution.

    The scheduler runs three passes per cycle:
    1. **Execution pass** — dispatch TODO tasks to plugins via TaskExecutionWorker
    2. **Auto-resume pass** — wake suspended tasks whose recovery time has arrived
    3. **Timeout pass** — detect timed-out in-progress tasks, close and republish

    The execution worker is optional: if no worker is provided (e.g. during
    testing or when no plugin_layer is available) the scheduler falls back to
    the original maintenance-only behaviour.
    """

    def __init__(
        self,
        *,
        task_service: Any,
        interval_seconds: int = 15,
        batch_size: int = 50,
        enabled: bool = True,
        # --- new: optional execution worker ---
        execution_worker: Optional[Any] = None,
    ) -> None:
        self._task_service = task_service
        self._interval_seconds = max(5, int(interval_seconds))
        self._batch_size = max(1, int(batch_size))
        self._enabled = bool(enabled)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._last_cycle_at: datetime | None = None

        # TaskExecutionWorker — may be None if not configured
        self._execution_worker = execution_worker

    def start(self) -> None:
        if not self._enabled:
            logger.info("Task auto loop scheduler disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run_loop, name="task-auto-loop", daemon=True)
        self._thread.start()
        logger.info(
            "Task auto loop scheduler started "
            "(interval_seconds=%s, batch_size=%s, execution_worker=%s)",
            self._interval_seconds,
            self._batch_size,
            "enabled" if self._execution_worker is not None else "disabled",
        )

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def set_execution_worker(self, worker: Any) -> None:
        """Attach or replace the execution worker at runtime.

        Useful when the plugin_layer / router become available after the
        scheduler has already been started (e.g. after plugin bootstrap).
        """
        self._execution_worker = worker
        logger.info(
            "TaskAutoLoopScheduler: execution worker %s",
            "attached" if worker is not None else "detached",
        )

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                asyncio.run(self._run_cycle())
            except Exception as exc:  # pragma: no cover - defensive loop guard
                logger.exception("Task auto loop cycle failed: %s", exc)
            self._stop_event.wait(self._interval_seconds)

    async def _run_cycle(self) -> None:
        started_at = datetime.now(timezone.utc)
        stats: dict[str, Any] = {
            "cycle_started_at": started_at.isoformat(),
            "execution_dispatched": 0,
            "execution_succeeded": 0,
            "execution_failed": 0,
            "execution_skipped": 0,
            "auto_resumed_count": 0,
            "timed_out_count": 0,
            "republished_count": 0,
            "errors": [],
        }

        # ── Pass 1: Execute dispatchable tasks ───────────────────────────
        if self._execution_worker is not None:
            try:
                worker_stats = await self._execution_worker.run_cycle()
                stats["execution_dispatched"] = worker_stats.tasks_dispatched
                stats["execution_succeeded"] = worker_stats.tasks_succeeded
                stats["execution_failed"] = worker_stats.tasks_failed
                stats["execution_skipped"] = worker_stats.tasks_skipped
                if worker_stats.errors:
                    stats["errors"].extend(worker_stats.errors)
            except Exception as exc:  # pragma: no cover
                logger.exception("Execution worker pass failed: %s", exc)
                stats["errors"].append({"stage": "execution", "error": str(exc)})

        # ── Pass 2: Auto-resume suspended tasks ──────────────────────────
        auto_resume_fn = getattr(self._task_service, "check_auto_resume_tasks", None)
        if callable(auto_resume_fn):
            try:
                resumed_tasks = await auto_resume_fn()
                stats["auto_resumed_count"] = len(resumed_tasks or [])
            except Exception as exc:  # pragma: no cover
                logger.exception("Task auto-resume pass failed: %s", exc)
                stats["errors"].append({"stage": "auto_resume", "error": str(exc)})

        # ── Pass 3: Detect and republish timed-out tasks ─────────────────
        timeout_fn = getattr(self._task_service, "check_timeout_and_republish_tasks", None)
        if callable(timeout_fn):
            try:
                timeout_results = await timeout_fn(limit=self._batch_size)
                stats["timed_out_count"] = len(timeout_results or [])
                stats["republished_count"] = sum(
                    1 for item in timeout_results or [] if item.get("republished")
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("Task timeout pass failed: %s", exc)
                stats["errors"].append({"stage": "timeout", "error": str(exc)})

        elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        stats["cycle_duration_ms"] = elapsed_ms
        self._last_cycle_at = started_at

        logger.info(
            "Task auto loop cycle completed: "
            "exec_dispatched=%s exec_ok=%s exec_fail=%s exec_skip=%s | "
            "auto_resumed=%s timed_out=%s republished=%s | duration_ms=%s",
            stats["execution_dispatched"],
            stats["execution_succeeded"],
            stats["execution_failed"],
            stats["execution_skipped"],
            stats["auto_resumed_count"],
            stats["timed_out_count"],
            stats["republished_count"],
            elapsed_ms,
        )

    @property
    def last_cycle_at(self) -> datetime | None:
        return self._last_cycle_at
