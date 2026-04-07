from __future__ import annotations

import pytest
from datetime import datetime, timezone

from zentex.common.plugin_registry import (
    AbstractPluginRegistry,
    PluginDependencyError,
    PluginRegistryAuditRecord,
    SecurityBlockError,
)
from zentex.core.plugin_base import (
    BasePluginSpec,
    FunctionalPluginSpec,
    LogicalCognitivePluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)


class DemoFunctionalPlugin(FunctionalPluginSpec):
    purpose: str

    @classmethod
    def plugin_kind(cls) -> str:
        return "demo_functional"


class DemoLogicalPlugin(LogicalCognitivePluginSpec):
    purpose: str

    @classmethod
    def plugin_kind(cls) -> str:
        return "demo_logical"


class DemoRegistry(AbstractPluginRegistry[BasePluginSpec]):
    def __init__(self) -> None:
        super().__init__(BasePluginSpec)

    def register(self, plugin: BasePluginSpec) -> BasePluginSpec:
        normalized = plugin.model_copy(update={"status": PluginLifecycleStatus.CANDIDATE})
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


def _activate(registry: DemoRegistry, plugin: BasePluginSpec) -> BasePluginSpec:
    registered = registry.register(plugin)
    registry.promote_plugin(
        plugin.plugin_id,
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    return registry.promote_plugin(
        plugin.plugin_id,
        PluginLifecycleStatus.ACTIVE,
        audit_reason="health checks passed",
    )


def _functional(plugin_id: str) -> DemoFunctionalPlugin:
    return DemoFunctionalPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code=f"demo.functional.{plugin_id}",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["audit_failure"],
        revocation_reasons=["reserved_for_audit"],
        purpose="functional capability",
    )


def _logical(plugin_id: str) -> DemoLogicalPlugin:
    return DemoLogicalPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code=f"demo.logical.{plugin_id}",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["audit_failure"],
        revocation_reasons=["reserved_for_audit"],
        purpose="logical orchestrator",
    )


def test_logical_plugin_may_resolve_functional_plugin() -> None:
    registry = DemoRegistry()
    logical = _activate(registry, _logical("q8"))
    functional = _activate(registry, _functional("model-provider"))

    with registry.plugin_call_scope(logical):
        resolved = registry.get_bound_plugin(DemoFunctionalPlugin)

    assert resolved.plugin_id == functional.plugin_id
    assert resolved.plugin_layer.value == "functional"


def test_functional_plugin_cannot_resolve_other_functional_plugins() -> None:
    registry = DemoRegistry()
    caller = _activate(registry, _functional("executor"))
    _activate(registry, _functional("model-provider"))

    with registry.plugin_call_scope(caller):
        with pytest.raises(PluginDependencyError, match="must never resolve other plugins"):
            registry.get_bound_plugin(DemoFunctionalPlugin)

    audit = registry.get_audit_records()[-1]
    assert audit.plugin_id == caller.plugin_id
    assert audit.action == "dependency_blocked"


def test_functional_plugin_cannot_resolve_logical_plugins() -> None:
    registry = DemoRegistry()
    caller = _activate(registry, _functional("executor"))
    _activate(registry, _logical("q8"))

    with registry.plugin_call_scope(caller):
        with pytest.raises(SecurityBlockError, match="must never resolve logical cognitive plugins"):
            registry.get_bound_plugin(DemoLogicalPlugin)

    audit = registry.get_audit_records()[-1]
    assert audit.plugin_id == caller.plugin_id
    assert audit.action == "security_blocked"
