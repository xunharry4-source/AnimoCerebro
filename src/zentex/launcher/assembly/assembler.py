"""
SystemAssembler — initialises all services in dependency order and wires them together.

The assembler is the heart of the startup process.  It uses ServiceDependencyGraph
to compute a safe init order, initialises each service (gracefully handling missing
optional modules), and finally injects cross-service references into the kernel.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from zentex.launcher.config.startup_config import StartupConfig
from zentex.launcher.assembly.service_registry import ServiceRegistry
from zentex.launcher.assembly.dependency_graph import ServiceDependencyGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stub service — used when an optional module's service cannot be imported
# ---------------------------------------------------------------------------

class _StubService:
    """Placeholder used when an optional service module is not yet installed."""

    def __init__(self, name: str) -> None:
        self.name = name

    def health_check(self) -> dict:
        return {"stub": True, "name": self.name}


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
    "llm": "llm_service",
    "foundation": "foundation_service",
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
                stub = _StubService(name)
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
        else:
            # Optional external service — graceful fallback to stub on ImportError.
            try:
                module = __import__(
                    f"zentex.{name}.service",
                    fromlist=["get_service"],
                )
                get_service_fn = getattr(module, "get_service")
                instance = get_service_fn()
                # Launcher only assembles the public service entrypoint. It must
                # not trigger module-internal lifecycle work such as plugin
                # discovery, registration, rehydration, or relation seeding.
            except ImportError:
                logger.warning(
                    "Optional service 'zentex.%s.service' not found — using stub.",
                    name,
                )
                instance = _StubService(name)
            except AttributeError:
                logger.warning(
                    "Optional service 'zentex.%s.service' has no get_service() — using stub.",
                    name,
                )
                instance = _StubService(name)

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

        dep_names = ["environment", "cognition", "safety", "plugins", "memory", "llm", "foundation"]
        kwargs: dict[str, Any] = {}
        for short_name in dep_names:
            kwarg_name = _KERNEL_DEP_KWARG.get(short_name, f"{short_name}_service")
            kwargs[kwarg_name] = registry.get(short_name)

        try:
            attach(**kwargs)
            logger.info("Injected dependencies into kernel service.")
        except Exception as exc:
            logger.error("Failed to inject dependencies into kernel: %s", exc)
