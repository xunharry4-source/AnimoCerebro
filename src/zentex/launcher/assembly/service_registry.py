"""
ServiceRegistry — thread-safe registry of all initialised service instances.

Each entry tracks the instance, health state, initialisation duration, and any
error message that was recorded when marking a service unhealthy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class ServiceEntry:
    """Metadata record for a single registered service."""

    name: str
    instance: object
    healthy: bool = True
    init_duration_ms: float = 0.0
    error: str = ""


class ServiceRegistry:
    """Thread-safe registry of named service instances."""

    def __init__(self) -> None:
        self._entries: dict[str, ServiceEntry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        instance: object,
        init_duration_ms: float = 0.0,
    ) -> None:
        """Register *instance* under *name*."""
        with self._lock:
            self._entries[name] = ServiceEntry(
                name=name,
                instance=instance,
                healthy=True,
                init_duration_ms=init_duration_ms,
                error="",
            )

    def mark_unhealthy(self, name: str, error: str) -> None:
        """Mark a registered service as unhealthy, recording the *error* message."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is not None:
                entry.healthy = False
                entry.error = error

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, name: str) -> object | None:
        """Return the service instance for *name*, or None if not registered."""
        with self._lock:
            entry = self._entries.get(name)
            return entry.instance if entry is not None else None

    def get_entry(self, name: str) -> ServiceEntry | None:
        """Return the full ServiceEntry for *name*, or None."""
        with self._lock:
            return self._entries.get(name)

    def all_names(self) -> list[str]:
        """Return a snapshot list of all registered service names."""
        with self._lock:
            return list(self._entries.keys())

    # ------------------------------------------------------------------
    # Health & status
    # ------------------------------------------------------------------

    def health_check_all(self) -> dict:
        """Call health_check() on every registered service that exposes it.

        Returns a mapping of service name → {"healthy": bool, "error": str}.
        """
        with self._lock:
            snapshot = list(self._entries.values())

        result: dict[str, dict] = {}
        for entry in snapshot:
            healthy = entry.healthy
            error = entry.error
            hc = getattr(entry.instance, "health_check", None)
            if callable(hc):
                try:
                    hc_result = hc()
                    # If the service returns an explicit "healthy" flag, honour it.
                    if isinstance(hc_result, dict) and "healthy" in hc_result:
                        healthy = bool(hc_result["healthy"])
                except Exception as exc:
                    healthy = False
                    error = str(exc)
            result[entry.name] = {"healthy": healthy, "error": error}
        return result

    def status_summary(self) -> dict:
        """Return a concise summary suitable for health-endpoint responses."""
        with self._lock:
            snapshot = list(self._entries.values())

        total = len(snapshot)
        healthy_count = sum(1 for e in snapshot if e.healthy)
        services = [
            {"name": e.name, "healthy": e.healthy, "init_ms": e.init_duration_ms}
            for e in snapshot
        ]
        return {
            "total": total,
            "healthy": healthy_count,
            "unhealthy": total - healthy_count,
            "services": services,
        }
