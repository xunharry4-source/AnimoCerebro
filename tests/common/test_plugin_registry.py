from __future__ import annotations

import pytest

from zentex.common.plugin_registry import (
    AbstractPluginRegistry,
    PluginNotBoundError,
    StateTransitionError,
)
from zentex.core.plugin_base import (
    BasePluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)


class DemoPluginSpec(BasePluginSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "demo"


class DemoPluginRegistry(AbstractPluginRegistry[DemoPluginSpec]):
    def __init__(self) -> None:
        super().__init__(DemoPluginSpec)


def build_plugin(
    *,
    plugin_id: str,
    feature_code: str = "test.domain",
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY,
) -> DemoPluginSpec:
    return DemoPluginSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code=feature_code,
        is_concurrency_safe=True,
        status=status,
        health_status=health_status,
        rollback_conditions=["signature_verification_failed"],
        revocation_reasons=["reserved_for_audit"],
    )


def test_register_then_direct_promote_to_active_is_blocked() -> None:
    registry = DemoPluginRegistry()
    plugin = registry.register(build_plugin(plugin_id="plugin-a"))

    assert plugin is not None
    assert plugin.status == PluginLifecycleStatus.CANDIDATE

    with pytest.raises(StateTransitionError) as exc_info:
        registry.promote_plugin(
            "plugin-a",
            PluginLifecycleStatus.ACTIVE,
            audit_reason="attempt to bypass sandbox stage",
        )

    assert "candidate -> active" in str(exc_info.value)


def test_revoke_requires_non_empty_reason() -> None:
    registry = DemoPluginRegistry()
    plugin = registry.register(build_plugin(plugin_id="plugin-b"))
    assert plugin is not None

    with pytest.raises(ValueError) as exc_info:
        registry.revoke_plugin("plugin-b", reason="")

    assert "audit_reason must not be empty" in str(exc_info.value)


def test_get_active_plugins_excludes_degraded_and_revoked_plugins() -> None:
    registry = DemoPluginRegistry()

    active_plugin = registry.register(build_plugin(plugin_id="plugin-active"))
    degraded_plugin = registry.register(build_plugin(plugin_id="plugin-degraded"))
    revoked_plugin = registry.register(build_plugin(plugin_id="plugin-revoked"))

    assert active_plugin is not None
    assert degraded_plugin is not None
    assert revoked_plugin is not None

    registry.promote_plugin(
        "plugin-active",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    registry.promote_plugin(
        "plugin-active",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="health probe and sandbox checks passed",
    )

    registry.promote_plugin(
        "plugin-degraded",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="entered sandbox path",
    )
    registry.promote_plugin(
        "plugin-degraded",
        PluginLifecycleStatus.DEGRADED,
        audit_reason="health probe degraded during verification",
    )

    registry.revoke_plugin(
        "plugin-revoked",
        reason="signature verification failed during review",
    )

    active_plugins = registry.get_active_plugins()
    active_plugin_ids = [plugin.plugin_id for plugin in active_plugins]

    assert active_plugin_ids == ["plugin-active"]
    assert "plugin-degraded" not in active_plugin_ids
    assert "plugin-revoked" not in active_plugin_ids


def test_feature_code_routing_rejects_candidate_plugin() -> None:
    registry = DemoPluginRegistry()
    plugin = registry.register(build_plugin(plugin_id="candidate", feature_code="test.domain"))
    assert plugin is not None

    with pytest.raises(PluginNotBoundError, match="No active bound plugin"):
        registry.get_single_active_plugin("test.domain")


def test_feature_code_routing_returns_multiple_active_plugins() -> None:
    registry = DemoPluginRegistry()
    plugin_a = registry.register(build_plugin(plugin_id="q1-a", feature_code="nine_questions.q1"))
    plugin_b = registry.register(build_plugin(plugin_id="q1-b", feature_code="nine_questions.q1"))
    assert plugin_a is not None
    assert plugin_b is not None

    for plugin_id in ("q1-a", "q1-b"):
        registry.promote_plugin(
            plugin_id,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
            audit_reason="sandbox ok",
        )
        registry.promote_plugin(
            plugin_id,
            PluginLifecycleStatus.ACTIVE,
            audit_reason="health ok",
        )

    active = registry.get_active_plugins("nine_questions.q1")
    assert sorted([p.plugin_id for p in active]) == ["q1-a", "q1-b"]
