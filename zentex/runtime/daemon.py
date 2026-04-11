from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class HeartbeatState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DEGRADED = "degraded"
    FUSED = "fused"  # Absolute stop due to critical failure


class BrainDaemon:
    """
    The background heartbeat of the Zentex system.
    
    Responsible for periodic execution of the cognitive tick loop.
    Implements a state machine to handle resilience and failure isolation.
    """
    def __init__(
        self,
        tick_fn: Callable[[], Any],
        tick_interval: float = 60.0,
        max_consecutive_failures: int = 5,
        fused_threshold: int = 15
    ):
        self._tick_fn = tick_fn
        self._interval = tick_interval
        self._state = HeartbeatState.PAUSED
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        self.consecutive_failures = 0
        self.total_failures = 0
        self.last_tick_at: Optional[datetime] = None
        self.next_tick_at: Optional[datetime] = None
        
        self.max_consecutive_failures = max_consecutive_failures
        self.fused_threshold = fused_threshold

    @property
    def state(self) -> HeartbeatState:
        return self._state

    def start(self):
        if self._state == HeartbeatState.FUSED:
            logger.error("Cannot start a fused daemon. Reset required.")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("Daemon is already running.")
            return

        self._stop_event.clear()
        self._state = HeartbeatState.ACTIVE
        self._thread = threading.Thread(target=self._run_loop, name="BrainDaemon", daemon=True)
        self._thread.start()
        logger.info(f"BrainDaemon started with interval={self._interval}s")

    def stop(self):
        self._stop_event.set()
        self._state = HeartbeatState.PAUSED
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("BrainDaemon stopped.")

    def reset(self):
        """Reset failures and allow restarts after fusing."""
        self.consecutive_failures = 0
        self.total_failures = 0
        if self._state == HeartbeatState.FUSED:
            self._state = HeartbeatState.PAUSED
        logger.info("BrainDaemon reset.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self._state == HeartbeatState.PAUSED:
                time.sleep(1)
                continue

            try:
                start_time = time.time()
                self.last_tick_at = datetime.now(timezone.utc)
                
                # Execute the actual cognitive work
                logger.debug("Executing daemon tick...")
                self._tick_fn()
                
                # Success logic
                self.consecutive_failures = 0
                if self._state == HeartbeatState.DEGRADED:
                    logger.info("Daemon recovered to ACTIVE state.")
                    self._state = HeartbeatState.ACTIVE

            except Exception as e:
                self.consecutive_failures += 1
                self.total_failures += 1
                logger.exception(f"Daemon tick failed (consecutive={self.consecutive_failures}): {e}")
                
                if self.consecutive_failures >= self.fused_threshold:
                    self._state = HeartbeatState.FUSED
                    logger.critical("DAEMON FUSED: Too many consecutive failures. Manual intervention required.")
                    break
                elif self.consecutive_failures >= self.max_consecutive_failures:
                    self._state = HeartbeatState.DEGRADED
                    logger.warning("Daemon entering DEGRADED mode.")

            # Calculate sleep time
            elapsed = time.time() - start_time
            sleep_time = max(0, self._interval - elapsed)
            
            # Apply backoff if degraded
            if self._state == HeartbeatState.DEGRADED:
                sleep_time *= 2  # Simple linear backoff for now
            
            self.next_tick_at = datetime.now(timezone.utc).fromtimestamp(time.time() + sleep_time)
            
            # Sleep in small chunks to stay responsive to stop_event
            for _ in range(int(sleep_time)):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
            time.sleep(sleep_time % 1)

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "next_tick_at": self.next_tick_at.isoformat() if self.next_tick_at else None,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "interval": self._interval
        }
