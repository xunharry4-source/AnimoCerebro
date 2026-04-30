from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Dict, List, Optional, Union

from zentex.common.startup_markers import log_once

logger = logging.getLogger(__name__)


class TaskAutoLoopScheduler:
    """Background scheduler for task lifecycle maintenance.

    The scheduler performs two maintenance passes:
    - auto-resume suspended tasks whose recovery time has arrived
    - detect timed-out running tasks, close them, and republish eligible ones
    """

    def __init__(
        self,
        *,
        task_service: Any,
        interval_seconds: int = 15,
        batch_size: int = 50,
        enabled: bool = True,
    ) -> None:
        self._task_service = task_service
        self._interval_seconds = max(5, int(interval_seconds))
        self._batch_size = max(1, int(batch_size))
        self._enabled = bool(enabled)
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._last_cycle_at: Optional[datetime] = None
        self._last_cycle_stats: Optional[Dict[str, Any]] = None

    def start(self) -> None:
        if not self._enabled:
            logger.info("Task auto loop scheduler disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        log_once(
            "tasks.scheduler.started",
            interval_seconds=self._interval_seconds,
            batch_size=self._batch_size,
        )
        self._thread = Thread(target=self._run_loop, name="task-auto-loop", daemon=True)
        self._thread.start()
        logger.info(
            "Task auto loop scheduler started (interval_seconds=%s, batch_size=%s)",
            self._interval_seconds,
            self._batch_size,
        )

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def status(self) -> Dict[str, Any]:
        thread = self._thread
        return {
            "enabled": self._enabled,
            "running": bool(thread is not None and thread.is_alive()),
            "interval_seconds": self._interval_seconds,
            "batch_size": self._batch_size,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "last_cycle_stats": dict(self._last_cycle_stats or {}),
        }

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
            "auto_resumed_count": 0,
            "timed_out_count": 0,
            "republished_count": 0,
            "tasks_dispatched": 0,
            "errors": [],
        }

        # 1. Dispatch Pass: Run the worker logic to execute TODO tasks
        dispatch_fn = getattr(self._task_service, "run_worker_cycle", None)
        if callable(dispatch_fn):
            try:
                # The real TaskService methods are async coroutines.  StubService
                # no-ops are sync lambdas that return None.  Use isawaitable() so
                # this scheduler works correctly regardless of which is injected.
                result = dispatch_fn()
                dispatch_stats = await result if inspect.isawaitable(result) else result
                stats["tasks_dispatched"] = (dispatch_stats or {}).get(
                    "tasks_dispatched",
                    (dispatch_stats or {}).get("tasks_processed", 0),
                )
                stats["dispatch_stats"] = dispatch_stats or {}
            except Exception as exc:
                logger.exception("Task dispatch pass failed: %s", exc)
                stats["errors"].append({"stage": "dispatch", "error": str(exc)})

        auto_resume_fn = getattr(self._task_service, "check_auto_resume_tasks", None)
        if callable(auto_resume_fn):
            try:
                result = auto_resume_fn()
                resumed_tasks = await result if inspect.isawaitable(result) else result
                stats["auto_resumed_count"] = len(resumed_tasks or [])
            except Exception as exc:  # pragma: no cover - defensive loop guard
                logger.exception("Task auto-resume pass failed: %s", exc)
                stats["errors"].append({"stage": "auto_resume", "error": str(exc)})

        timeout_fn = getattr(self._task_service, "check_timeout_and_republish_tasks", None)
        if callable(timeout_fn):
            try:
                result = timeout_fn(limit=self._batch_size)
                timeout_results = await result if inspect.isawaitable(result) else result
                stats["timed_out_count"] = len(timeout_results or [])
                stats["republished_count"] = sum(1 for item in timeout_results or [] if item.get("republished"))
            except Exception as exc:  # pragma: no cover - defensive loop guard
                logger.exception("Task timeout pass failed: %s", exc)
                stats["errors"].append({"stage": "timeout", "error": str(exc)})

        elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        stats["cycle_duration_ms"] = elapsed_ms
        self._last_cycle_at = started_at
        self._last_cycle_stats = stats

        did_work = any(
            (
                stats["auto_resumed_count"],
                stats["timed_out_count"],
                stats["republished_count"],
                len(stats["errors"]),
            )
        )
        log_fn = logger.info if did_work else logger.debug
        log_fn(
            "Task auto loop cycle completed: dispatched=%s auto_resumed=%s timed_out=%s republished=%s duration_ms=%s",
            stats["tasks_dispatched"],
            stats["auto_resumed_count"],
            stats["timed_out_count"],
            stats["republished_count"],
            elapsed_ms,
        )

    @property
    def last_cycle_at(self) -> Optional[datetime]:
        return self._last_cycle_at
