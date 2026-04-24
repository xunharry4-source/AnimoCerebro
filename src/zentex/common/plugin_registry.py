from __future__ import annotations
"""Migration-safe plugin registry compat layer.

This module restores the historical `zentex.common.plugin_registry` public
surface while routing new code toward the `zentex.plugins` contract layer.
It is a transitional boundary and should remain fail-closed.
"""


from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generic, Iterator, TypeVar, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict

from zentex.plugins.contracts import (
    BasePluginSpec,
    FunctionalPluginSpec,
    LogicalCognitivePluginSpec,
    PluginLifecycleStatus,
)


PluginSpecT = TypeVar("PluginSpecT", bound=BasePluginSpec)


class PluginRegistryError(RuntimeError):
    """Base error for compatibility registry operations."""


class PluginNotBoundError(PluginRegistryError):
    """Raised when no active plugin can be resolved for a request."""


class StateTransitionError(PluginRegistryError):
    """Raised when a lifecycle transition violates the migration rules."""


class PluginDependencyError(PluginRegistryError):
    """Raised when a functional plugin attempts forbidden dependency lookup."""


class SecurityBlockError(PluginRegistryError):
    """Raised when a functional plugin attempts to reach a logical plugin."""


class PluginRegistryAuditRecord(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin_id: str
    action: str
    audit_reason: str
    recorded_at: datetime


class PluginRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin_id: str
    spec: Any
    description: str = ""

    @property
    def plugin(self) -> Any:
        return self.spec


class AbstractPluginRegistry(Generic[PluginSpecT]):
    """Minimal compat registry used by legacy business code and tests."""

    def __init__(self, spec_type: type[PluginSpecT]) -> None:
        self._spec_type = spec_type
        self._plugins: dict[str, PluginSpecT] = {}
        self._registrations: dict[str, PluginRegistration] = {}
        self._audit_records: list[PluginRegistryAuditRecord] = []
        self._caller_stack: list[BasePluginSpec] = []
        self._allow_inactive_resolution = False

    def _record_audit(self, plugin_id: str, action: str, audit_reason: str) -> None:
        self._audit_records.append(
            PluginRegistryAuditRecord(
                plugin_id=plugin_id,
                action=action,
                audit_reason=audit_reason,
                recorded_at=datetime.now(timezone.utc),
            )
        )

    def _normalize_spec(
        self,
        plugin: PluginSpecT,
        *,
        lifecycle_status: Optional[PluginLifecycleStatus] = None,
        revocation_reason: Optional[str] = None,
    ) -> PluginSpecT:
        updates: dict[str, Any] = {}
        if lifecycle_status is not None:
            updates["lifecycle_status"] = lifecycle_status
            updates["status"] = lifecycle_status
        if revocation_reason:
            existing_reasons = list(getattr(plugin, "revocation_reasons", []) or [])
            if revocation_reason not in existing_reasons:
                existing_reasons.append(revocation_reason)
            updates["revocation_reasons"] = existing_reasons
        return plugin.model_copy(update=updates) if updates else plugin

    def _store_spec(self, plugin: PluginSpecT, *, description: str = "") -> PluginSpecT:
        self._plugins[plugin.plugin_id] = plugin
        self._registrations[plugin.plugin_id] = PluginRegistration(
            plugin_id=plugin.plugin_id,
            spec=plugin,
            description=description,
        )
        return plugin

    def _effective_lifecycle_status(self, plugin: Any) -> Union[PluginLifecycleStatus, Any]:
        status = getattr(plugin, "lifecycle_status", None)
        if status is None:
            status = getattr(plugin, "status", None)
        extra = getattr(plugin, "__pydantic_extra__", None)
        if isinstance(extra, dict) and "status" in extra:
            status = extra["status"]
        return status

    def register(self, plugin: PluginSpecT, *, description: str = "") -> PluginSpecT:
        normalized = self._normalize_spec(plugin, lifecycle_status=PluginLifecycleStatus.CANDIDATE)
        self._store_spec(normalized, description=description)
        self._record_audit(normalized.plugin_id, "registered", "registered_as_candidate")
        return normalized

    def get_registered_plugin(self, plugin_id: str) -> Optional[PluginSpecT]:
        return self._plugins.get(plugin_id)

    def get_registration(self, plugin_id: str) -> Optional[PluginRegistration]:
        return self._registrations.get(plugin_id)

    def list_registrations(self) -> list[PluginRegistration]:
        return list(self._registrations.values())

    def get_audit_records(self) -> list[PluginRegistryAuditRecord]:
        return list(self._audit_records)

    def _validate_transition(
        self,
        current: PluginLifecycleStatus,
        target: PluginLifecycleStatus,
    ) -> None:
        if current == PluginLifecycleStatus.CANDIDATE and target == PluginLifecycleStatus.ACTIVE:
            raise StateTransitionError("candidate -> active requires sandbox verification first")

    def promote_plugin(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        audit_reason: str,
    ) -> PluginSpecT:
        plugin = self._plugins[plugin_id]
        self._validate_transition(plugin.lifecycle_status, target_status)
        updated = self._normalize_spec(plugin, lifecycle_status=target_status)
        self._store_spec(updated)
        self._record_audit(plugin_id, "promoted", audit_reason)
        return updated

    def revoke_plugin(self, plugin_id: str, reason: str) -> PluginSpecT:
        if not str(reason).strip():
            raise ValueError("audit_reason must not be empty")
        plugin = self._plugins[plugin_id]
        updated = self._normalize_spec(
            plugin,
            lifecycle_status=PluginLifecycleStatus.REVOKED,
            revocation_reason=reason,
        )
        self._store_spec(updated)
        self._record_audit(plugin_id, "revoked", reason)
        return updated

    def get_active_plugins(self, feature_code: Optional[str] = None) -> list[PluginSpecT]:
        active_plugins: list[PluginSpecT] = []
        for plugin in self._plugins.values():
            if self._effective_lifecycle_status(plugin) != PluginLifecycleStatus.ACTIVE:
                continue
            if getattr(plugin, "operational_status", "enabled") != "enabled":
                continue
            if feature_code is not None and getattr(plugin, "feature_code", None) != feature_code:
                continue
            active_plugins.append(plugin)
        return active_plugins

    def get_single_active_plugin(self, feature_code: str) -> PluginSpecT:
        active_plugins = self.get_active_plugins(feature_code)
        if not active_plugins:
            raise PluginNotBoundError(f"No active bound plugin for {feature_code}")
        if len(active_plugins) > 1:
            raise PluginNotBoundError(f"Multiple active cognitive tools found for {feature_code}")
        return active_plugins[0]

    @contextmanager
    def plugin_call_scope(self, caller: BasePluginSpec) -> Iterator[None]:
        self._caller_stack.append(caller)
        try:
            yield
        finally:
            self._caller_stack.pop()

    def _record_forbidden_lookup(self, action: str, audit_reason: str) -> None:
        caller = self._caller_stack[-1]
        self._record_audit(caller.plugin_id, action, audit_reason)

    def get_bound_plugin(self, plugin_type: type[PluginSpecT]) -> PluginSpecT:
        caller = self._caller_stack[-1] if self._caller_stack else None
        if isinstance(caller, FunctionalPluginSpec):
            if issubclass(plugin_type, LogicalCognitivePluginSpec):
                self._record_forbidden_lookup(
                    "security_blocked",
                    "functional plugins must never resolve logical cognitive plugins",
                )
                raise SecurityBlockError(
                    "functional plugins must never resolve logical cognitive plugins"
                )
            self._record_forbidden_lookup(
                "dependency_blocked",
                "functional plugins must never resolve other plugins",
            )
            raise PluginDependencyError("functional plugins must never resolve other plugins")

        active_plugins = [
            plugin for plugin in self._plugins.values()
            if isinstance(plugin, plugin_type)
            and self._effective_lifecycle_status(plugin) == PluginLifecycleStatus.ACTIVE
            and getattr(plugin, "operational_status", "enabled") == "enabled"
        ]
        if not active_plugins:
            raise PluginNotBoundError(f"No active bound plugin for {plugin_type.__name__}")
        if len(active_plugins) > 1:
            raise PluginNotBoundError(f"Multiple active plugins found for {plugin_type.__name__}")
        return active_plugins[0]

    def create_test_sandbox(self) -> "AbstractPluginRegistry[PluginSpecT]":
        sandbox = self.__class__(self._spec_type) if self.__class__ is AbstractPluginRegistry else self.__class__()  # type: ignore[call-arg]
        sandbox._plugins = dict(self._plugins)
        sandbox._registrations = dict(self._registrations)
        sandbox._audit_records = list(self._audit_records)
        sandbox._allow_inactive_resolution = True
        return sandbox

    def resolve_plugin_for_test(self, plugin_id: str) -> PluginRegistration:
        if not self._allow_inactive_resolution:
            raise PluginNotBoundError("Inactive plugin resolution is only available inside a sandbox")
        registration = self._registrations.get(plugin_id)
        if registration is None:
            raise PluginNotBoundError(f"No plugin registered for {plugin_id}")
        return registration


class PluginRegistry(AbstractPluginRegistry[BasePluginSpec]):
    def __init__(self) -> None:
        super().__init__(BasePluginSpec)
