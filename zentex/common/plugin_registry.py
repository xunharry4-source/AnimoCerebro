from __future__ import annotations

"""
Abstract plugin registry for Zentex.

This registry is not a passive dictionary. It is the first safety gate for all
plugin families built on top of `BasePluginSpec`. It enforces:

- deterministic lifecycle transitions
- audit-reason requirements
- failure isolation for rejected plugin payloads
- safe filtering of active and healthy plugins only
"""

from abc import ABC
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import ValidationError

from zentex.core.plugin_base import (
    BasePluginSpec,
    FunctionalPluginSpec,
    LogicalCognitivePluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)


T = TypeVar("T", bound=BasePluginSpec)


class StateTransitionError(ValueError):
    """Raised when a plugin attempts an illegal lifecycle transition."""


class PluginNotBoundError(RuntimeError):
    """Raised when runtime tries to resolve a plugin that is not actively bound."""


class PluginDependencyError(RuntimeError):
    """Raised when a plugin violates the hard dependency-layer contract."""


class SecurityBlockError(RuntimeError):
    """Raised when a plugin attempts a forbidden upward or privileged resolution."""


@dataclass(frozen=True, slots=True)
class PluginRegistryAuditRecord:
    plugin_id: str
    action: str
    audit_reason: str
    recorded_at: datetime


class AbstractPluginRegistry(ABC, Generic[T]):
    """
    Generic safety registry for plugin lifecycle management.

    Core guarantees:
    - all registered plugins are normalized to `candidate`
    - candidate plugins cannot jump directly to `active`
    - degrade/revoke paths require auditable reasons
    - invalid plugin payloads are isolated as rejected events
    """

    def __init__(self, plugin_type: type[T]) -> None:
        self.plugin_type = plugin_type
        self._plugins: dict[str, T] = {}
        self._audit_records: list[PluginRegistryAuditRecord] = []
        self._caller_context: ContextVar[BasePluginSpec | None] = ContextVar(
            f"plugin_registry_caller_{id(self)}",
            default=None,
        )

    @contextmanager
    def plugin_call_scope(self, caller: BasePluginSpec):
        token: Token[BasePluginSpec | None] = self._caller_context.set(caller)
        try:
            yield
        finally:
            self._caller_context.reset(token)

    def register(self, plugin: T) -> T | None:
        """
        Register a plugin and force its initial state to `candidate`.

        Failure isolation:
        - invalid plugin payloads are caught and recorded as rejected events
        - the registry itself must not crash on validation failure
        """

        try:
            normalized = self.plugin_type.model_validate(
                {
                    **plugin.model_dump(),
                    "status": PluginLifecycleStatus.CANDIDATE,
                }
            )
        except ValidationError as exc:
            plugin_id = self._extract_plugin_id(plugin)
            self._audit_records.append(
                PluginRegistryAuditRecord(
                    plugin_id=plugin_id,
                    action="rejected",
                    audit_reason=str(exc),
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            return None

        self._plugins[normalized.plugin_id] = normalized
        self._audit_records.append(
            PluginRegistryAuditRecord(
                plugin_id=normalized.plugin_id,
                action="registered",
                audit_reason="registered_as_candidate",
                recorded_at=datetime.now(timezone.utc),
            )
        )
        return normalized

    def promote_plugin(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        audit_reason: str,
    ) -> T:
        self._require_audit_reason(audit_reason)
        plugin = self._get_plugin_or_raise(plugin_id)

        if (
            plugin.status == PluginLifecycleStatus.CANDIDATE
            and target_status == PluginLifecycleStatus.ACTIVE
        ):
            raise StateTransitionError(
                "Illegal plugin status transition: candidate -> active"
            )

        try:
            promoted = plugin.transition_to(target_status)
        except ValueError as exc:
            raise StateTransitionError(str(exc)) from exc

        self._plugins[plugin_id] = promoted
        self._audit_records.append(
            PluginRegistryAuditRecord(
                plugin_id=plugin_id,
                action=f"promoted_to_{target_status.value}",
                audit_reason=audit_reason,
                recorded_at=datetime.now(timezone.utc),
            )
        )
        return promoted

    def revoke_plugin(self, plugin_id: str, reason: str) -> T:
        self._require_audit_reason(reason)
        plugin = self._get_plugin_or_raise(plugin_id)

        try:
            revoked = plugin.transition_to(
                PluginLifecycleStatus.REVOKED,
                revocation_reasons=[reason],
            )
        except ValueError as exc:
            raise StateTransitionError(str(exc)) from exc

        self._plugins[plugin_id] = revoked
        self._audit_records.append(
            PluginRegistryAuditRecord(
                plugin_id=plugin_id,
                action="revoked",
                audit_reason=reason,
                recorded_at=datetime.now(timezone.utc),
            )
        )
        return revoked

    def get_single_active_plugin(self, feature_code: str) -> T:
        """
        Generalized Fail-Closed routing for core feature organs.

        Strict requirements:
        - plugin status must be 'active'
        - exactly one plugin must be active for this feature_code
        - failure to find exactly one results in PluginNotBoundError
        """
        self._guard_registry_resolution(
            requested_feature_code=feature_code,
            requested_plugin_type=None,
        )
        active = self.get_active_plugins(feature_code)
        if not active:
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: {feature_code}"
            )
        if len(active) > 1:
            raise PluginNotBoundError(
                f"Multiple active plugins are bound to single-plugin feature: {feature_code}"
            )
        return active[0]

    def get_active_plugins(self, feature_code: str | None = None) -> list[T]:
        """
        Generalized routing for capability enhancement patches.

        Strict requirements:
        - plugin status must be 'active'
        - returns a filtered list from the registry
        """
        self._guard_registry_resolution(
            requested_feature_code=feature_code,
            requested_plugin_type=None,
        )
        requested_feature_code = (feature_code or "").strip() or None
        active_plugins: list[T] = []
        for plugin in self._plugins.values():
            if plugin.status != PluginLifecycleStatus.ACTIVE:
                continue
            if self._caller_requires_functional_only() and isinstance(
                plugin,
                LogicalCognitivePluginSpec,
            ):
                continue
            if requested_feature_code is not None and plugin.feature_code != requested_feature_code:
                continue
            if not self._is_plugin_healthy(plugin):
                continue
            active_plugins.append(plugin)
        return active_plugins

    def get_bound_plugin(self, plugin_type: type[T]) -> T:
        """
        Resolve exactly one active plugin instance by Python type.

        This is a generic helper for IoC wiring in runtime components that want a
        strongly typed plugin contract (e.g. ModelProviderSpec). It remains
        fail-closed:
        - only ACTIVE plugins are visible
        - unhealthy plugins are hidden
        - empty or multiple matches raise PluginNotBoundError
        """
        self._guard_registry_resolution(
            requested_feature_code=None,
            requested_plugin_type=plugin_type,
        )
        candidates: list[T] = []
        for plugin in self._plugins.values():
            if plugin.status != PluginLifecycleStatus.ACTIVE:
                continue
            if not isinstance(plugin, plugin_type):
                continue
            if self._caller_requires_functional_only() and isinstance(
                plugin,
                LogicalCognitivePluginSpec,
            ):
                continue
            if not self._is_plugin_healthy(plugin):
                continue
            candidates.append(plugin)

        if not candidates:
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: {plugin_type.__name__}"
            )
        if len(candidates) > 1:
            raise PluginNotBoundError(
                f"Multiple active plugins are bound to single-plugin query: {plugin_type.__name__}"
            )
        return candidates[0]

    def get_plugin(self, plugin_id: str) -> T:
        plugin = self._get_plugin_or_raise(plugin_id)
        self._guard_registry_resolution(
            requested_feature_code=getattr(plugin, "feature_code", None),
            requested_plugin_type=type(plugin),
        )
        if plugin.status != PluginLifecycleStatus.ACTIVE:
            raise PluginNotBoundError(
                f"Plugin is not bound for runtime use because it is not active: {plugin_id}"
            )
        return plugin

    def get_registered_plugin(self, plugin_id: str) -> T:
        return self._get_plugin_or_raise(plugin_id)

    def get_audit_records(self) -> list[PluginRegistryAuditRecord]:
        return list(self._audit_records)

    def _get_plugin_or_raise(self, plugin_id: str) -> T:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown plugin: {plugin_id}") from exc

    def _require_audit_reason(self, audit_reason: str) -> None:
        if not audit_reason or not audit_reason.strip():
            raise ValueError("audit_reason must not be empty")

    def _is_plugin_healthy(self, plugin: T) -> bool:
        if plugin.health_status is not None:
            return plugin.health_status == PluginHealthStatus.HEALTHY
        return plugin.health_probe_endpoint is not None

    def _extract_plugin_id(self, plugin: object) -> str:
        value = getattr(plugin, "plugin_id", None)
        if isinstance(value, str) and value.strip():
            return value
        return "unknown"

    def _caller_requires_functional_only(self) -> bool:
        caller = self._caller_context.get()
        return isinstance(caller, LogicalCognitivePluginSpec)

    def _guard_registry_resolution(
        self,
        *,
        requested_feature_code: str | None,
        requested_plugin_type: type[object] | None,
    ) -> None:
        caller = self._caller_context.get()
        if caller is None:
            return

        target_is_logical = self._target_is_logical(
            requested_feature_code=requested_feature_code,
            requested_plugin_type=requested_plugin_type,
        )

        if isinstance(caller, FunctionalPluginSpec):
            if target_is_logical:
                action = "security_blocked"
                message = (
                    "Functional plugins must never resolve logical cognitive plugins "
                    f"through the registry: caller={caller.plugin_id}"
                )
                error_cls: type[RuntimeError] = SecurityBlockError
            else:
                action = "dependency_blocked"
                message = (
                    "Functional plugins must never resolve other plugins through the "
                    f"registry: caller={caller.plugin_id}"
                )
                error_cls = PluginDependencyError
            self._audit_records.append(
                PluginRegistryAuditRecord(
                    plugin_id=caller.plugin_id,
                    action=action,
                    audit_reason=message,
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            raise error_cls(message)

        if isinstance(caller, LogicalCognitivePluginSpec) and target_is_logical:
            message = (
                "Logical cognitive plugins may only orchestrate functional plugins "
                f"through the registry: caller={caller.plugin_id}"
            )
            self._audit_records.append(
                PluginRegistryAuditRecord(
                    plugin_id=caller.plugin_id,
                    action="dependency_blocked",
                    audit_reason=message,
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            raise PluginDependencyError(message)

    def _target_is_logical(
        self,
        *,
        requested_feature_code: str | None,
        requested_plugin_type: type[object] | None,
    ) -> bool:
        if requested_plugin_type is not None and issubclass(
            requested_plugin_type,
            LogicalCognitivePluginSpec,
        ):
            return True
        feature_code = (requested_feature_code or "").strip()
        return feature_code.startswith("nine_questions.")
