from __future__ import annotations
"""
SystemAssembler — initialises all services in dependency order and wires them together.

The assembler is the heart of the startup process.  It uses ServiceDependencyGraph
to compute a safe init order, initialises each service (gracefully handling missing
optional modules), and finally injects cross-service references into the kernel.
"""


import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from zentex.launcher.config.startup_config import StartupConfig
from zentex.launcher.assembly.service_registry import ServiceRegistry
from zentex.launcher.assembly.dependency_graph import ServiceDependencyGraph
from zentex.common.startup_markers import log_once

logger = logging.getLogger(__name__)

# Track which (service_name, attribute) pairs have already been warned about so
# the scheduler loop does not flood logs with the same warning every 15 seconds.
_STUB_WARNED: set[str] = set()


# ---------------------------------------------------------------------------
# Stub service — used when an optional module's service cannot be imported
# ---------------------------------------------------------------------------

class _StubService:
    """Placeholder used when an optional service module is not yet installed or fails to init.

    The ``_is_stub`` class attribute lets callers (e.g. ``_require_task_service``
    in routers) detect that this is a stub and return a proper 503 error instead
    of attempting to use the stub and crashing on the None return value.
    """

    _is_stub: bool = True  # Sentinel checked by router dependency guards

    def __init__(self, name: str, error_detail: Optional[str] = None) -> None:
        self.name = name
        self.error_detail = error_detail

    def health_check(self) -> dict:
        return {
            "stub": True,
            "name": self.name,
            "error": self.error_detail,
            "status": "missing_provider" if self.error_detail else "not_installed"
        }

    def __getattr__(self, name: str) -> Any:
        """Fail-closed for any attempted stub method access.

        Each (service_name, attribute_name) combination logs exactly once, then
        any attempted call raises a runtime error instead of fabricating an
        empty/no-op result.
        """
        warn_key = f"{self.name}.{name}"
        if warn_key not in _STUB_WARNED:
            _STUB_WARNED.add(warn_key)
            logger.warning(
                "StubService '%s' accessed for attribute '%s' — service not available. "
                "This warning is shown only once per attribute.",
                self.name, name,
            )
        detail = self.error_detail or "Service not available"

        def _fail(*args, **kwargs):
            raise RuntimeError(f"StubService '{self.name}.{name}' invoked: {detail}")

        return _fail


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AssemblyResult:
    """Outcome of a SystemAssembler.assemble() call."""

    success: bool
    registry: ServiceRegistry
    errors: dict[str, str] = field(default_factory=dict)
    init_order: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

# Services that MUST succeed for the system to be usable.
_REQUIRED_SERVICES: frozenset[str] = frozenset({"foundation", "kernel"})

# Mapping from short service name → keyword arg name expected by
# KernelService.attach_dependencies().
_KERNEL_DEP_KWARG: dict[str, str] = {
    "environment": "environment_service",
    "cognition": "cognition_service",
    "safety": "safety_service",
    "plugins": "plugins_service",
    "memory": "memory_service",
    "audit": "audit_service",
    "llm": "llm_service",
    "foundation": "foundation_service",
    "agents": "agent_service",
    "reflection": "reflection_service",
    "learning": "learning_service",
    "tasks": "task_service",
}


class SystemAssembler:
    """Assembles all zentex services in topological order."""

    def __init__(self, config: StartupConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(self) -> AssemblyResult:
        """Initialise all services and return an AssemblyResult."""
        graph = ServiceDependencyGraph()

        # Fail fast if the static graph already has cycles (shouldn't happen
        # unless NODES is edited incorrectly).
        cycles = graph.detect_cycles()
        if cycles:
            raise RuntimeError(
                f"Cycle detected in service dependency graph: {cycles}"
            )

        order = graph.topological_sort()
        registry = ServiceRegistry()
        errors: dict[str, str] = {}

        for name in order:
            try:
                instance, duration_ms = self._init_service(name, registry)
                registry.register(name, instance, init_duration_ms=duration_ms)
                logger.info("Initialised service '%s' in %.1f ms", name, duration_ms)
            except Exception as exc:
                error_msg = str(exc)
                errors[name] = error_msg
                logger.error(
                    "Failed to initialise service '%s': %s", name, error_msg
                )
                # Register a stub so downstream services don't explode on lookup.
                stub = _StubService(name, error_detail=error_msg)
                registry.register(name, stub, init_duration_ms=0.0)
                registry.mark_unhealthy(name, error_msg)

                if name in _REQUIRED_SERVICES:
                    # Required service failed — abort immediately.
                    return AssemblyResult(
                        success=False,
                        registry=registry,
                        errors=errors,
                        init_order=order,
                    )

        # Wire up cross-service references.
        self._inject_dependencies(registry)

        success = not any(name in errors for name in _REQUIRED_SERVICES)
        return AssemblyResult(
            success=success,
            registry=registry,
            errors=errors,
            init_order=order,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_service(
        self, name: str, registry: ServiceRegistry
    ) -> tuple[object, float]:
        """Initialise the named service and return (instance, duration_ms)."""
        start = time.monotonic()

        instance: Any

        if name == "foundation":
            from zentex.foundation.service import get_service  # type: ignore[import]
            instance = get_service()
        elif name == "kernel":
            from zentex.kernel.service import get_service as get_kernel_service  # type: ignore[import]
            instance = get_kernel_service(
                transcript_db_dir=self._config.kernel.transcript_db_dir
            )
        elif name == "cognition":
            # Mandatory explicit initialization for CognitionService
            from zentex.cognition.service import init_cognition_service
            from plugins.simulation.thought.thought_sandbox_plugin import build_default_thought_sandbox
            
            llm_service = registry.get("llm")
            # registry.get("llm") might return a stub if it failed, but init_cognition_service handles it
            
            # Instantiate default simulation plugin
            simulation_plugins = [build_default_thought_sandbox()]
            
            instance = init_cognition_service(
                llm_service=llm_service,
                simulation_plugins=simulation_plugins
            )
        else:
            # Optional external service — graceful fallback to stub on ImportError.
            try:
                module = __import__(
                    f"zentex.{name}.service",
                    fromlist=["get_service"],
                )
                get_service_fn = getattr(module, "get_service")
                if name in {"cli", "mcp"}:
                    instance = get_service_fn(llm_service=registry.get("llm"))
                else:
                    instance = get_service_fn()
                # Launcher only assembles the public service entrypoint. It must
                # not trigger module-internal lifecycle work such as plugin
                # discovery, registration, rehydration, or relation seeding.
            except ImportError:
                logger.warning(
                    "Optional service 'zentex.%s.service' not found — using stub.",
                    name,
                )
                instance = _StubService(name, error_detail="Module not found (ImportError)")
            except AttributeError:
                logger.warning(
                    "Optional service 'zentex.%s.service' has no get_service() — using stub.",
                    name,
                )
                instance = _StubService(name, error_detail="get_service() missing (AttributeError)")

        duration_ms = (time.monotonic() - start) * 1000.0
        return instance, duration_ms

    def _inject_dependencies(self, registry: ServiceRegistry) -> None:
        """Inject external service references into the kernel via attach_dependencies()."""
        kernel = registry.get("kernel")
        if kernel is None:
            logger.warning("Kernel not in registry; skipping dependency injection.")
            return

        attach = getattr(kernel, "attach_dependencies", None)
        if not callable(attach):
            logger.warning(
                "Kernel service has no attach_dependencies() method; "
                "skipping dependency injection."
            )
            return

        dep_names = ["environment", "cognition", "safety", "plugins", "memory", "audit", "llm", "foundation", "agents", "reflection", "learning", "tasks"]
        kwargs: dict[str, Any] = {}
        for short_name in dep_names:
            kwarg_name = _KERNEL_DEP_KWARG.get(short_name, f"{short_name}_service")
            kwargs[kwarg_name] = registry.get(short_name)

        try:
            attach(**kwargs)
            logger.info("Injected dependencies into kernel service.")
        except Exception as exc:
            logger.error("Failed to inject dependencies into kernel: %s", exc)

        self._attach_audit_transcript_projection(kernel, registry.get("audit"))

        # 3. Attach tasks dependencies (late binding for circular plugin references)
        tasks = registry.get("tasks")
        if getattr(tasks, "_is_stub", False):
            logger.warning("SystemAssembler: skipping dependency injection for stub 'tasks' service.")
        elif tasks and hasattr(tasks, "attach_dependencies"):
            tasks.attach_dependencies(
                plugin_service=registry.get("plugins"),
                transcript_store=getattr(kernel, "transcript_store", None),
                cli_service=registry.get("cli"),
                mcp_service=registry.get("mcp"),
            )
            logger.info("SystemAssembler: Attached dependencies to 'tasks' service.")

    def _attach_audit_transcript_projection(self, kernel: Any, audit_service: Any) -> None:
        """Wire transcript writes into the audit store without coupling modules."""
        if getattr(audit_service, "_is_stub", False):
            logger.warning("SystemAssembler: skipping audit transcript projection for stub audit service.")
            return
        audit_store = getattr(audit_service, "store", None)
        sync_entries = getattr(audit_store, "sync_from_transcript_entries", None)
        attach_listener = getattr(kernel, "add_transcript_entry_listener", None)
        if not callable(sync_entries) or not callable(attach_listener):
            logger.warning("SystemAssembler: audit transcript projection unavailable.")
            return

        def _project_transcript_entry(entry: Any) -> None:
            sync_entries([entry])

        attach_listener("audit_trace_store_projection", _project_transcript_entry)
        logger.info("SystemAssembler: Attached transcript-to-audit projection listener.")
