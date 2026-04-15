from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any

from zentex.reflection.nine_question_effectiveness import run_question_reflection
from zentex.reflection.service_facade import ReflectionServiceFacade


class NineQuestionReflectionScheduler:
    """Daily scheduler for q1..q9 effectiveness reflection."""

    def __init__(
        self,
        *,
        runtime: Any,
        reflection_service: ReflectionServiceFacade,
        upgrade_execution_service: Any | None = None,
        interval_seconds: int = 3600,
    ) -> None:
        self._runtime = runtime
        self._reflection_service = reflection_service
        self._upgrade_execution_service = upgrade_execution_service
        self._interval_seconds = max(60, int(interval_seconds))
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._last_run_date: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
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
            return

        state = getattr(self._runtime, "nine_question_state", None)
        if state is None or not hasattr(state, "to_payload"):
            return

        state_payload = state.to_payload()
        snapshots = state_payload.get("question_snapshots") if isinstance(state_payload, dict) else {}
        if not isinstance(snapshots, dict) or not snapshots:
            return

        for i in range(1, 10):
            qid = f"q{i}"
            if qid not in snapshots:
                continue
            run_question_reflection(
                reflection_service=self._reflection_service,
                question_id=qid,
                state_payload=state_payload,
                scope="scheduled_daily",
                trigger="scheduled_daily",
                upgrade_execution_service=self._upgrade_execution_service,
            )

        self._last_run_date = today
