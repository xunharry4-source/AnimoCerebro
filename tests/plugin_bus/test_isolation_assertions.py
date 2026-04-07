from __future__ import annotations

import pytest
from zentex.common.plugin_registry import PluginNotBoundError
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, event: dict) -> None:
        self.events.append(event)


def _build_spec(plugin_id: str, feature_code: str, status: PluginLifecycleStatus) -> CognitiveToolSpec:
    return CognitiveToolSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code=feature_code,
        behavior_key=feature_code,
        is_concurrency_safe=True,
        status=status,
        purpose="Test isolation",
        rollback_conditions=["manual_rollback"] if status == PluginLifecycleStatus.ACTIVE else [],
        revocation_reasons=["test_revocation"] if status == PluginLifecycleStatus.REVOKED else [],
        tool_type="cognitive",
        input_schema={},
        output_schema={},
        required_context=[],
        trigger_conditions=["always"],
        do_not_use_when=["never"],
        health_status=PluginHealthStatus.HEALTHY,
    )


def test_runtime_isolation_assertion():
    """
    Assertion Test: Non-active plugins MUST be physically isolated from runtime resolution.
    
    Target: CognitiveToolRegistry
    Logic: get_single_active_plugin and get_active_plugins MUST NOT return 'candidate' or 'revoked' plugins.
    """
    sink = InMemoryAuditSink()
    registry = CognitiveToolRegistry(transcript_store=sink)
    
    # 1. Register a candidate plugin
    candidate_spec = _build_spec("test.candidate", "core.test_feature", PluginLifecycleStatus.CANDIDATE)
    registry.register(candidate_spec)
    
    # 2. Register an active plugin
    active_spec = _build_spec("test.active", "core.test_feature", PluginLifecycleStatus.ACTIVE)
    # Registration starts as candidate, then promoted
    registry.register(active_spec)
    registry.promote_plugin("test.active", PluginLifecycleStatus.SANDBOX_VERIFIED, audit_reason="Verifying in sandbox")
    registry.promote_plugin("test.active", PluginLifecycleStatus.ACTIVE, audit_reason="Enabling for test")
    
    # Assertion A: Runtime query for 'core.test_feature' MUST ONLY return 'test.active'
    active_plugins = registry.get_active_plugins("core.test_feature")
    assert len(active_plugins) == 1
    assert active_plugins[0].plugin_id == "test.active"
    
    single_active = registry.get_single_active_plugin("core.test_feature")
    assert single_active.plugin_id == "test.active"
    
    # Assertion B: Candidate plugin MUST be physically absent from runtime resolution
    all_active_ids = [p.spec.plugin_id for p in registry.get_active_plugins("core.test_feature")]
    assert "test.candidate" not in all_active_ids
    
    # 3. Revoke the active plugin
    registry.revoke_plugin("test.active", reason="Emergency stop")
    
    # Assertion C: After revocation, runtime query MUST FAIL with PluginNotBoundError
    with pytest.raises(PluginNotBoundError):
        registry.get_single_active_plugin("core.test_feature")
        
    assert len(registry.get_active_plugins("core.test_feature")) == 0


def test_sandbox_resolution_bypass_prevention():
    """
    Assertion Test: Inactive plugin resolution is ONLY allowed inside a sandbox.
    """
    sink = InMemoryAuditSink()
    registry = CognitiveToolRegistry(transcript_store=sink)
    
    candidate_spec = _build_spec("test.target", "core.test_feature", PluginLifecycleStatus.CANDIDATE)
    registry.register(candidate_spec)
    
    # Assertion D: Direct resolution of inactive plugin in production registry MUST FAIL
    with pytest.raises(PluginNotBoundError):
        registry.resolve_plugin_for_test("test.target")
        
    # Assertion E: Resolution WORKS inside a sandbox
    sandbox = registry.create_test_sandbox()
    registration = sandbox.resolve_plugin_for_test("test.target")
    assert registration.plugin_id == "test.target"


def test_concurrency_violation_fail_closed():
    """
    Assertion Test: Multiple active plugins for a single-instance feature MUST trigger Fail-Closed.
    """
    sink = InMemoryAuditSink()
    # Mocking single-instance enforcement
    registry = CognitiveToolRegistry(transcript_store=sink)
    
    spec1 = _build_spec("test.1", "core.singleton", PluginLifecycleStatus.ACTIVE)
    spec2 = _build_spec("test.2", "core.singleton", PluginLifecycleStatus.ACTIVE)
    
    registry.register(spec1)
    registry.promote_plugin("test.1", PluginLifecycleStatus.SANDBOX_VERIFIED, audit_reason="Verifying 1")
    registry.promote_plugin("test.1", PluginLifecycleStatus.ACTIVE, audit_reason="Enabled 1")
    
    # Hack to inject a second active plugin for the same feature to test Fail-Closed
    # (Normally registry.promote_plugin or force_enable_plugin would deactivate the other one if supports_multiple is False)
    # But we want to test the protection in get_single_active_plugin itself.
    
    registry.register(spec2)
    # Bypass the built-in deactivation to simulate a corrupted or multi-active state
    registration2 = registry.get_registration("test.2")
    registry._plugins["test.2"] = registration2.spec.model_copy(update={"status": PluginLifecycleStatus.ACTIVE})
    registry._registrations["test.2"] = registration2.model_copy(update={"spec": registry._plugins["test.2"]})
    
    # Assertion F: get_single_active_plugin MUST throw Error when multiple are active
    with pytest.raises(PluginNotBoundError) as excinfo:
        registry.get_single_active_plugin("core.singleton")
    assert "Multiple active cognitive tools found" in str(excinfo.value)
