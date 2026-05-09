from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
TickHandler = Callable[[str | None, str], dict[str, Any]]


@dataclass
class BrainDaemonState:
    heartbeat_state: str = "paused"
    running: bool = False
    interval_seconds: float = 30.0
    max_consecutive_failures: int = 3
    tick_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    backoff_seconds: float = 0.0
    last_tick_at: str | None = None
    last_success_at: str | None = None
    last_error: str = ""
    last_trace_id: str = ""
    last_session_id: str = ""
    last_observation: dict[str, Any] = field(default_factory=dict)


class BrainDaemon:
    def __init__(self, *, tick_handler: TickHandler) -> None:
        self._tick_handler = tick_handler
        self._state = BrainDaemonState()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._history: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def control(
        self,
        *,
        action: str,
        session_id: str | None = None,
        interval_seconds: float | None = None,
        max_consecutive_failures: int | None = None,
        run_background: bool = False,
    ) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized == "start":
            return self.start(
                session_id=session_id,
                interval_seconds=interval_seconds,
                max_consecutive_failures=max_consecutive_failures,
                run_background=run_background,
            )
        if normalized == "tick":
            return self.tick(session_id=session_id)
        if normalized == "pause":
            return self.pause(reason="manual_control")
        if normalized == "resume":
            return self.resume()
        if normalized == "stop":
            return self.stop()
        raise ValueError(f"Unsupported BrainDaemon action: {action}")

    def start(
        self,
        *,
        session_id: str | None = None,
        interval_seconds: float | None = None,
        max_consecutive_failures: int | None = None,
        run_background: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if interval_seconds is not None:
                if interval_seconds <= 0:
                    raise ValueError("interval_seconds must be > 0")
                self._state.interval_seconds = float(interval_seconds)
            if max_consecutive_failures is not None:
                if max_consecutive_failures <= 0:
                    raise ValueError("max_consecutive_failures must be > 0")
                self._state.max_consecutive_failures = int(max_consecutive_failures)
            self._state.running = True
            if self._state.heartbeat_state in {"paused", "degraded"}:
                self._state.heartbeat_state = "active"
            self._state.last_error = ""
            if session_id:
                self._state.last_session_id = session_id
            self._record_locked("started", {"run_background": run_background})
            if run_background and (self._thread is None or not self._thread.is_alive()):
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._run_loop,
                    name="zentex-brain-daemon",
                    daemon=True,
                )
                self._thread.start()
            return self._status_locked()

    def pause(self, *, reason: str) -> dict[str, Any]:
        with self._lock:
            self._state.heartbeat_state = "paused"
            self._record_locked("paused", {"reason": reason})
            return self._status_locked()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            self._state.running = True
            self._state.heartbeat_state = "active"
            self._state.last_error = ""
            self._record_locked("resumed", {})
            return self._status_locked()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._state.running = False
            self._state.heartbeat_state = "paused"
            self._stop_event.set()
            self._record_locked("stopped", {})
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)
        with self._lock:
            self._thread = None
            return self._status_locked()

    def tick(self, *, session_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            state_before = self._state.heartbeat_state
            if not self._state.running:
                self._record_locked("tick_skipped", {"reason": "not_running"})
                return self._status_locked(extra={"tick_executed": False, "skip_reason": "not_running"})
            if state_before == "paused":
                self._record_locked("tick_skipped", {"reason": "paused"})
                return self._status_locked(extra={"tick_executed": False, "skip_reason": "paused"})
            if state_before == "fused":
                self._record_locked("tick_skipped", {"reason": "fused"})
                return self._status_locked(extra={"tick_executed": False, "skip_reason": "fused"})
            trace_id = f"g3-brain-daemon:{uuid4().hex}"
            self._state.last_trace_id = trace_id
            if session_id:
                self._state.last_session_id = session_id

        try:
            observation = self._tick_handler(session_id, trace_id)
        except Exception as exc:
            with self._lock:
                self._state.tick_count += 1
                self._state.failure_count += 1
                self._state.consecutive_failures += 1
                self._state.last_tick_at = datetime.now(UTC).isoformat()
                self._state.last_error = f"{exc.__class__.__name__}: {exc}"
                self._state.backoff_seconds = min(300.0, 2.0 ** max(0, self._state.consecutive_failures - 1))
                if self._state.consecutive_failures >= self._state.max_consecutive_failures:
                    self._state.heartbeat_state = "fused"
                else:
                    self._state.heartbeat_state = "degraded"
                self._record_locked("tick_failed", {"error": self._state.last_error})
                return self._status_locked(extra={"tick_executed": True, "tick_success": False})

        with self._lock:
            self._state.tick_count += 1
            self._state.success_count += 1
            self._state.consecutive_failures = 0
            self._state.backoff_seconds = 0.0
            self._state.heartbeat_state = "active"
            now = datetime.now(UTC).isoformat()
            self._state.last_tick_at = now
            self._state.last_success_at = now
            self._state.last_error = ""
            self._state.last_observation = observation
            self._state.last_session_id = str(observation.get("session_id") or session_id or "")
            self._record_locked("tick_completed", {"trace_id": trace_id})
            return self._status_locked(extra={"tick_executed": True, "tick_success": True})

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                sleep_seconds = max(0.05, self._state.backoff_seconds or self._state.interval_seconds)
            self.tick(session_id=None)
            self._stop_event.wait(timeout=sleep_seconds)

    def _status_locked(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "feature_code": "G3",
            "heartbeat_state": self._state.heartbeat_state,
            "running": self._state.running,
            "interval_seconds": self._state.interval_seconds,
            "max_consecutive_failures": self._state.max_consecutive_failures,
            "tick_count": self._state.tick_count,
            "success_count": self._state.success_count,
            "failure_count": self._state.failure_count,
            "consecutive_failures": self._state.consecutive_failures,
            "backoff_seconds": self._state.backoff_seconds,
            "last_tick_at": self._state.last_tick_at,
            "last_success_at": self._state.last_success_at,
            "last_error": self._state.last_error,
            "last_trace_id": self._state.last_trace_id,
            "last_session_id": self._state.last_session_id,
            "last_observation": self._state.last_observation,
            "history": list(self._history[-20:]),
        }
        if extra:
            payload.update(extra)
        return payload

    def _record_locked(self, event: str, payload: dict[str, Any]) -> None:
        self._history.append(
            {
                "event": event,
                "payload": dict(payload),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


def build_kernel_daemon_tick_handler(kernel_service: Any) -> TickHandler:
    def _handler(session_id: str | None, trace_id: str) -> dict[str, Any]:
        resolved_session_id = session_id or getattr(kernel_service, "_DEFAULT_SESSION_ID", "zentex-default-session")
        if callable(getattr(kernel_service, "_get_or_create_default_state", None)) and not session_id:
            kernel_service._get_or_create_default_state()
        elif callable(getattr(kernel_service, "_get_state", None)) and kernel_service._get_state(resolved_session_id) is None:
            raise ValueError(f"Session state missing for BrainDaemon tick: {resolved_session_id}")

        turn_id = f"brain-daemon-tick-{uuid4().hex}"
        observation = kernel_service.observe_environment(resolved_session_id, turn_id)
        _write_kernel_daemon_transcript(
            kernel_service,
            session_id=resolved_session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            event="g3_brain_daemon_tick_completed",
            payload={
                "observation_keys": sorted(observation.keys()),
                "heartbeat_state": "active",
            },
        )
        return {
            "session_id": resolved_session_id,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "observation": observation,
        }

    return _handler


def _write_kernel_daemon_transcript(
    kernel_service: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    state = kernel_service._get_state(session_id) if callable(getattr(kernel_service, "_get_state", None)) else None
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("BrainDaemon requires a session transcript store")
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="kernel.brain_daemon",
            payload={
                "feature_code": "G3",
                "entry_type": event,
                "trace_id": trace_id,
                **payload,
            },
        )
    )
