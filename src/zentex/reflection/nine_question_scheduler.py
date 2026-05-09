from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Dict, List, Optional, Union

from zentex.module_logs import record_module_log
from zentex.reflection.nine_question_effectiveness import run_question_reflection
from zentex.reflection.service import ReflectionService
from zentex.common.startup_markers import log_once


class NineQuestionReflectionScheduler:
    """Daily scheduler for q1..q9 effectiveness reflection."""

    def __init__(
        self,
        *,
        runtime: Any,
        reflection_service: ReflectionService,
        upgrade_execution_service: Any = None,
        interval_seconds: int = 3600,
        module_log_service: Any = None,
    ) -> None:
        self._runtime = runtime
        self._reflection_service = reflection_service
        self._upgrade_execution_service = upgrade_execution_service
        self._module_log_service = module_log_service
        self._interval_seconds = max(60, int(interval_seconds))
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._last_run_date: Optional[str] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        log_once(
            "reflection.scheduler.started",
            interval_seconds=self._interval_seconds,
        )
        self._thread = Thread(target=self._run_loop, name="nq-reflection-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._maybe_run_daily()
            except Exception:
                # keep scheduler alive; failures are non-fatal
                pass
            self._stop_event.wait(self._interval_seconds)

    def _maybe_run_daily(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._last_run_date == today:
            self._record_scheduler_log(
                status="skipped",
                reflected_count=0,
                reason=f"{today} 已完成过九问定时反思，本轮跳过。",
            )
            return

        state = getattr(self._runtime, "nine_question_state", None)
        if state is None or not hasattr(state, "to_payload"):
            self._record_scheduler_log(
                status="skipped",
                reflected_count=0,
                reason="运行时没有可用的九问状态快照，无法生成定时反思。",
            )
            return

        state_payload = state.to_payload()
        snapshots = state_payload.get("question_snapshots") if isinstance(state_payload, dict) else {}
        if not isinstance(snapshots, dict) or not snapshots:
            self._record_scheduler_log(
                status="skipped",
                reflected_count=0,
                reason="九问状态快照为空，本轮没有可反思的问题。",
            )
            return

        reflected_count = 0
        errors: list[str] = []
        for i in range(1, 10):
            qid = f"q{i}"
            if qid not in snapshots:
                continue
            try:
                run_question_reflection(
                    reflection_service=self._reflection_service,
                    question_id=qid,
                    state_payload=state_payload,
                    scope="scheduled_daily",
                    trigger="scheduled_daily",
                    upgrade_execution_service=self._upgrade_execution_service,
                )
                reflected_count += 1
            except Exception as exc:
                errors.append(f"{qid}: {exc}")

        self._last_run_date = today
        self._record_scheduler_log(
            status="failed" if errors else "completed",
            reflected_count=reflected_count,
            reason=(
                "九问定时反思执行时出现失败，请查看 errors 详情。"
                if errors
                else f"九问定时反思已完成，本轮生成 {reflected_count} 个问题反思。"
            ),
            details={"date": today, "errors": errors, "snapshot_count": len(snapshots)},
        )

    def _record_scheduler_log(
        self,
        *,
        status: str,
        reflected_count: int,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        record_module_log(
            self._module_log_service,
            source_module="reflection",
            module_label="反思模块",
            action="scheduled_daily_reflection",
            action_label="九问定时反思已执行",
            object_id="nine-question-reflection-scheduler",
            object_label="九问每日反思调度器",
            before_status="running",
            after_status=status,
            reason=reason,
            details={"reflected_count": reflected_count, **(details or {})},
            operator_id="nine-question-reflection-scheduler",
            status=status,
        )
