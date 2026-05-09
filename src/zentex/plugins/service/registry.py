from __future__ import annotations
"""Migration-safe registry adapters exposed via zentex.plugins.service.

These registries exist so legacy runtime/core callers can bridge into a stable
plugins-owned service domain while the business code is migrated off old imports.
"""


from typing import Any

from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistration
from zentex.plugins.cognitive_spec import CognitiveToolSpec
from zentex.plugins.contracts import BasePluginSpec, PluginLifecycleStatus
from zentex.plugins.execution import ExecutionDomainPlugin


class ExecutionDomainRegistry(AbstractPluginRegistry[ExecutionDomainPlugin]):
    """Legacy execution registry bridged into the plugins service domain."""

    def __init__(self) -> None:
        super().__init__(ExecutionDomainPlugin)


class CognitiveToolRegistry(AbstractPluginRegistry[CognitiveToolSpec]):
    """Legacy cognitive tool registry kept as a compat object during migration."""

    def __init__(self, transcript_store: Optional[Any] = None, audit_logger: Optional[Any] = None) -> None:
        super().__init__(CognitiveToolSpec)
        self.transcript_store = transcript_store
        self.audit_logger = audit_logger

    def query_by_type(self, plugin_type: type[Any]) -> list[PluginRegistration]:
        return [reg for reg in self.list_registrations() if isinstance(reg.spec, plugin_type)]

    def get_active_plugins(self, feature_code: Optional[str] = None) -> list[PluginRegistration]:
        registrations: list[PluginRegistration] = []
        for registration in self.list_registrations():
            spec = registration.spec
            if self._effective_lifecycle_status(spec) != PluginLifecycleStatus.ACTIVE:
                continue
            if getattr(spec, "operational_status", "enabled") != "enabled":
                continue
            if feature_code is not None and getattr(spec, "feature_code", None) != feature_code:
                continue
            registrations.append(registration)
        return registrations

    def get_single_active_plugin(self, feature_code: str) -> PluginRegistration:
        active_plugins = self.get_active_plugins(feature_code)
        if not active_plugins:
            from zentex.common.plugin_registry import PluginNotBoundError

            raise PluginNotBoundError(f"No active bound plugin for {feature_code}")
        if len(active_plugins) > 1:
            from zentex.common.plugin_registry import PluginNotBoundError

            raise PluginNotBoundError(f"Multiple active cognitive tools found for {feature_code}")
        return active_plugins[0]

    def force_enable_plugin(self, plugin_id: str) -> str:
        self.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, audit_reason="force_enable_plugin")
        return plugin_id

    def force_disable_plugin(self, plugin_id: str) -> str:
        self.promote_plugin(plugin_id, PluginLifecycleStatus.DEGRADED, audit_reason="force_disable_plugin")
        return plugin_id


class InMemoryAuditSink:
    """Minimal in-memory audit sink kept for legacy tests and bridge callers."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, payload: dict[str, Any]) -> None:
        self.events.append(dict(payload))
