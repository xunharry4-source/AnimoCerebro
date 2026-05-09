from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Any, Dict, List, Optional, Union

from zentex.module_logs import record_module_log
from zentex.common.startup_markers import log_once
import logging

logger = logging.getLogger(__name__)


class MemoryRepairScheduler:
    """Background scheduler that periodically repairs degraded modular memory."""

    def __init__(
        self,
        *,
        memory_service: Any,
        interval_seconds: int = 3600,
        enabled: bool = True,
        module_log_service: Any = None,
    ) -> None:
        self._memory_service = memory_service
        self._interval_seconds = max(60, int(interval_seconds))
        self._enabled = bool(enabled)
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._module_log_service = module_log_service
        self._state_lock = Lock()
        self._last_cycle_at: Optional[datetime] = None
        self._last_summary: dict[str, Any] = {
            "status": "idle",
            "tickets": 0,
            "repaired_blocks": 0,
            "quarantined_blocks": 0,
            "projection_repairs": 0,
            "errors": [],
        }

    def start(self) -> None:
        if not self._enabled:
            logger.info("Memory repair scheduler disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        log_once("memory.repair.scheduler.started", interval_seconds=self._interval_seconds)
        self._thread = Thread(target=self._run_loop, name="memory-repair-scheduler", daemon=True)
        self._thread.start()
        logger.info("Memory repair scheduler started (interval_seconds=%s)", self._interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "enabled": self._enabled,
                "interval_seconds": self._interval_seconds,
                "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
                "last_summary": dict(self._last_summary),
            }

    def run_once(self) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        summary: dict[str, Any] = {
            "status": "ok",
            "tickets": 0,
            "repaired_blocks": 0,
            "quarantined_blocks": 0,
            "projection_repairs": 0,
            "errors": [],
            "started_at": started_at.isoformat(),
        }
        try:
            tickets = list(self._memory_service.repair_all())
            summary["tickets"] = len(tickets)
            summary["repaired_blocks"] = sum(len(ticket.repaired_blocks) for ticket in tickets)
            summary["quarantined_blocks"] = sum(len(ticket.quarantined_blocks) for ticket in tickets)
            summary["projection_repairs"] = sum(len(ticket.projection_repairs) for ticket in tickets)
        except Exception as exc:  # pragma: no cover - defensive loop guard
            logger.exception("Memory repair scheduler cycle failed: %s", exc)
            summary["status"] = "failed"
            summary["errors"].append(str(exc))
        summary["duration_ms"] = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        with self._state_lock:
            self._last_cycle_at = started_at
            self._last_summary = summary
        self._record_cycle_log(summary)
        return summary

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self._interval_seconds)

    def _record_cycle_log(self, summary: dict[str, Any]) -> None:
        status = str(summary.get("status") or "completed")
        after_status = "failed" if status == "failed" else "completed"
        reason = (
            "记忆修复定时任务执行失败，请查看 errors 详情。"
            if after_status == "failed"
            else "记忆修复定时任务已完成，已检查退化记录并尝试修复投影与隔离异常块。"
        )
        record_module_log(
            self._module_log_service,
            source_module="memory",
            module_label="记忆模块",
            action="scheduled_repair",
            action_label="定时修复已执行",
            object_id="memory-repair-scheduler",
            object_label="记忆修复调度器",
            before_status="running",
            after_status=after_status,
            reason=reason,
            details=dict(summary),
            operator_id="memory-repair-scheduler",
            status=after_status,
        )
