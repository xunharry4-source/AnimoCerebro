from __future__ import annotations
"""
Daemon entrypoint — background controller that monitors service health and
manages session timeouts while the system is running.
"""


import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from zentex.foundation.meta import SESSION_DEFAULT_TIMEOUT_SECONDS
from zentex.launcher.assembly.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


class DaemonController:
    """Background controller that runs a heartbeat loop for the running system."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self._running: bool = False
        self._thread: threading.Optional[Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background heartbeat thread."""
        if self._running:
            logger.warning("DaemonController.start() called while already running.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="zentex-daemon-heartbeat",
            daemon=True,
        )
        self._thread.start()
        logger.info("DaemonController started.")

    def stop(self) -> None:
        """Signal the heartbeat loop to stop and wait for the thread to finish."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=60)
            self._thread = None
        logger.info("DaemonController stopped.")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """Run until self._running is False, checking health every 30 seconds."""
        while self._running:
            try:
                health = self._registry.health_check_all()
                for name, info in health.items():
                    if not info.get("healthy", True):
                        logger.warning(
                            "Service '%s' is unhealthy: %s",
                            name,
                            info.get("error", "unknown"),
                        )
            except Exception as exc:
                logger.error("Heartbeat health check error: %s", exc)

            try:
                self._check_session_timeouts()
            except Exception as exc:
                logger.error("Session timeout check error: %s", exc)

            # Sleep in small increments so stop() is responsive.
            for _ in range(30):
                if not self._running:
                    break
                time.sleep(1)

    def _check_session_timeouts(self) -> None:
        """Suspend sessions that have exceeded the default timeout."""
        kernel = self._registry.get("kernel")
        if kernel is None:
            return

        # Gather active sessions.
        list_fn = getattr(kernel, "list_active_sessions", None)
        if not callable(list_fn):
            return
        session_ids: list[str] = list_fn()

        # Ask the lifecycle manager to identify timed-out sessions.
        lifecycle = getattr(kernel, "_lifecycle", None)
        if lifecycle is None:
            return

        check_fn = getattr(lifecycle, "check_timeouts", None)
        if not callable(check_fn):
            return

        try:
            timed_out: list[str] = check_fn(SESSION_DEFAULT_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.error("check_timeouts failed: %s", exc)
            return

        for session_id in timed_out:
            try:
                suspend_fn = getattr(kernel, "suspend_session", None)
                if callable(suspend_fn):
                    suspend_fn(session_id)
                    logger.info("Suspended timed-out session: %s", session_id)
            except Exception as exc:
                logger.error(
                    "Failed to suspend session %s: %s", session_id, exc
                )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_daemon(registry: ServiceRegistry) -> DaemonController:
    """Create (but do not start) a DaemonController for *registry*."""
    return DaemonController(registry)
