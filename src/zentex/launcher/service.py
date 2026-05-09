from __future__ import annotations
"""
Public service boundary for zentex.launcher.
Single entry point for starting the Zentex system.

External callers should import LauncherService or get_launcher() from here.
No other launcher internals should be imported directly by external modules.
"""


import logging
from enum import Enum
from typing import TYPE_CHECKING, Dict, Any, Optional

from zentex.launcher.config.startup_config import StartupConfig
from zentex.launcher.config.env_reader import EnvReader
from zentex.launcher.config.config_validator import ConfigValidator
from zentex.launcher.assembly.service_registry import ServiceRegistry
from zentex.launcher.assembly.assembler import SystemAssembler, AssemblyResult
from zentex.launcher.entrypoints.web_dev import create_web_app
from zentex.launcher.entrypoints.daemon import DaemonController, create_daemon

logger = logging.getLogger(__name__)


class LauncherStatus(str, Enum):
    """Refined startup status of the Zentex launcher."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETE = "complete"           # All services (required & optional) started
    PARTIAL_FAILED = "partial_failed" # Required services ok, some optional failed
    DEGRADED = "degraded"           # Started with stubs/mocks due to failures
    FAILED = "failed"               # Required services failed


class LauncherService:
    """Single public interface for starting and stopping the Zentex system."""

    def __init__(self) -> None:
        self._registry: Optional[ServiceRegistry] = None
        self._config: Optional[StartupConfig] = None
        self._daemon: Optional[DaemonController] = None
        self._app: Optional[object] = None
        self._assembly_errors: Dict[str, str] = {}
        self._status: LauncherStatus = LauncherStatus.NOT_STARTED

    # ------------------------------------------------------------------
    # Startup helpers
    # ------------------------------------------------------------------

    def _load_and_validate(self, config: Optional[StartupConfig]) -> StartupConfig:
        """Load config from env if not supplied, then validate it."""
        if config is None:
            config = EnvReader().read()

        result = ConfigValidator().validate(config)
        for warning in result.warnings:
            logger.warning("Config warning: %s", warning)

        if not result.valid:
            error_lines = "\n  - ".join(result.errors)
            raise RuntimeError(
                f"Invalid startup configuration:\n  - {error_lines}"
            )

        return config

    def _assemble(self, config: StartupConfig) -> ServiceRegistry:
        """Assemble all services and return the populated registry."""
        assembler = SystemAssembler(config)
        result: AssemblyResult = assembler.assemble()
        self._assembly_errors = result.errors

        if not result.success:
            self._status = LauncherStatus.FAILED
            failed = [
                f"{name}: {msg}" for name, msg in result.errors.items()
            ]
            raise RuntimeError(
                "Required services failed to initialise:\n  "
                + "\n  ".join(failed)
            )

        # Determine if status is COMPLETE or PARTIAL_FAILED
        if result.errors:
            self._status = LauncherStatus.PARTIAL_FAILED
            for name, msg in result.errors.items():
                logger.warning("Optional service '%s' failed: %s", name, msg)
        else:
            self._status = LauncherStatus.COMPLETE

        return result.registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_web(self, config: Optional[StartupConfig] = None) -> object:
        """Load config, assemble services, build a FastAPI app, and return it.

        Args:
            config: Optional pre-built StartupConfig.  If None, config is
                    loaded from environment variables via EnvReader.

        Returns:
            A FastAPI application instance (or a dict if FastAPI is not
            installed — see create_web_app() for details).

        Raises:
            RuntimeError: If config is invalid or required services fail.
        """
        config = self._load_and_validate(config)
        self._config = config

        registry = self._assemble(config)
        self._registry = registry

        self._app = create_web_app(registry)
        logger.info("Web app created and ready.")
        return self._app

    def start_daemon(self, config: Optional[StartupConfig] = None) -> DaemonController:
        """Load config, assemble services, create and start a DaemonController.

        Args:
            config: Optional pre-built StartupConfig.  If None, config is
                    loaded from environment variables via EnvReader.

        Returns:
            A running DaemonController instance.

        Raises:
            RuntimeError: If config is invalid or required services fail.
        """
        config = self._load_and_validate(config)
        self._config = config

        registry = self._assemble(config)
        self._registry = registry

        daemon = create_daemon(registry)
        daemon.start()
        self._daemon = daemon
        logger.info("Daemon started.")
        return daemon

    def shutdown(self) -> None:
        """Gracefully stop the daemon and attempt to close all services."""
        if self._daemon is not None:
            try:
                self._daemon.stop()
            except Exception as exc:
                logger.error("Error stopping daemon: %s", exc)
            self._daemon = None

        if self._registry is not None:
            for name in self._registry.all_names():
                svc = self._registry.get(name)
                if svc is None:
                    continue
                for method_name in ("shutdown", "close"):
                    method = getattr(svc, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception as exc:
                            logger.warning(
                                "Error calling %s.%s(): %s", name, method_name, exc
                            )
                        break  # only call one of shutdown/close per service

            self._registry = None

        self._config = None
        self._app = None
        logger.info("LauncherService shut down.")

    def get_status(self) -> dict:
        """Return a status snapshot for monitoring / health checks."""
        return {
            "status": self._status.value,
            "initialized": self._registry is not None,
            "config_env": self._config.environment if self._config is not None else "",
            "errors": self._assembly_errors,
            "services": (
                self._registry.status_summary()
                if self._registry is not None
                else {}
            ),
        }

    # ------------------------------------------------------------------
    # Service accessor methods (read-only)
    # ------------------------------------------------------------------

    def get_foundation_service(self) -> Optional[object]:
        """Return the initialised FoundationService instance, or None if not available.

        FoundationService provides protocol definitions and system capabilities.
        This is a required service; it is guaranteed to exist after start_web()
        or start_daemon() succeeds.

        Returns:
            The FoundationService instance, or None if the system has not been started.
        """
        if self._registry is None:
            return None
        return self._registry.get("foundation")

    def get_kernel_service(self) -> Optional[object]:
        """Return the initialised KernelService instance, or None if not available.

        KernelService handles session management, turn execution, and state queries.
        This is a required service; it is guaranteed to exist after start_web()
        or start_daemon() succeeds.

        Returns:
            The KernelService instance, or None if the system has not been started.
        """
        if self._registry is None:
            return None
        return self._registry.get("kernel")

    def get_memory_service(self) -> Optional[object]:
        """Return the initialised memory service instance, or None if not available.

        The memory service handles recall, consolidation, and memory persistence.
        This is an optional service; it may be None if the memory module is not
        installed or if assembly failed.

        Returns:
            The memory service instance, or None if not available or not started.
        """
        if self._registry is None:
            return None
        return self._registry.get("memory")

    def get_plugins_service(self) -> Optional[object]:
        """Return the initialised plugins service instance, or None if not available.

        The plugins service orchestrates execution of cognitive (Q1-Q9) and
        functional plugins. It is required for turn execution to work properly.

        Returns:
            The plugins service instance, or None if not available or not started.
        """
        if self._registry is None:
            return None
        return self._registry.get("plugins")


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_default_launcher: Optional[LauncherService] = None


def get_launcher() -> LauncherService:
    """Return the module-level LauncherService singleton, creating it if necessary."""
    global _default_launcher
    if _default_launcher is None:
        _default_launcher = LauncherService()
    return _default_launcher
