from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.cognitive_tools_spec import CognitiveToolSpec  # noqa: E402
from zentex.core.plugin_base import (  # noqa: E402
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.runtime.cognitive_tools.registry import (  # noqa: E402
    CognitiveToolRegistry,
)
from zentex.common.plugin_registry import PluginNotBoundError  # noqa: E402


def _build_cognitive_tool_spec(
    *,
    plugin_id: str = "tool-deliberation",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
    behavior_key: str = "deliberation",
    is_default_version: bool = False,
    is_official_release: bool = True,
    supports_multi_active: bool = False,
) -> CognitiveToolSpec:
    return CognitiveToolSpec(
        plugin_id=plugin_id,
        version=version,
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["tool_runtime_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="analysis",
        purpose="Analyze context without side effects",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        required_context=["working_memory"],
        trigger_conditions=["metacognition"],
        behavior_key=behavior_key,
        supports_multi_active=supports_multi_active,
        is_default_version=is_default_version,
        is_official_release=is_official_release,
        do_not_use_when=["external_execution_requested"],
    )


def test_promote_writes_transcript_audit_record() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registration = registry.register(_build_cognitive_tool_spec(plugin_id="tool-a"))

    assert registration is not None

    registry.promote_plugin(
        "tool-a",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    promoted = registry.promote_plugin(
        "tool-a",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="production rollout approved",
    )

    assert promoted.status == PluginLifecycleStatus.ACTIVE
    assert transcript_store.append.called

    appended_events = [call.args[0] for call in transcript_store.append.call_args_list]
    promote_events = [
        event
        for event in appended_events
        if event["action"] == "promoted"
        and event["new_state"]["status"] == PluginLifecycleStatus.ACTIVE.value
    ]

    assert promote_events
    assert promote_events[-1]["plugin_id"] == "tool-a"
    assert promote_events[-1]["audit_reason"] == "production rollout approved"


def test_record_tool_failure_auto_degrades_and_writes_history() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(_build_cognitive_tool_spec(plugin_id="tool-b"))
    registry.promote_plugin(
        "tool-b",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.promote_plugin(
        "tool-b",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="ready for live reasoning traffic",
    )

    registry.record_tool_failure("tool-b", "timeout-1")
    registry.record_tool_failure("tool-b", "timeout-2")
    degraded = registry.record_tool_failure("tool-b", "timeout-3")

    assert degraded.status == PluginLifecycleStatus.DEGRADED

    appended_events = [call.args[0] for call in transcript_store.append.call_args_list]
    degrade_events = [
        event
        for event in appended_events
        if event["action"] == "promoted"
        and event["new_state"]["status"] == PluginLifecycleStatus.DEGRADED.value
    ]

    assert degrade_events
    assert "timeout-3" in degrade_events[-1]["audit_reason"]


def test_force_enable_deactivates_conflicting_active_plugin_for_same_behavior() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-default",
            behavior_key="risk_assessment",
            is_default_version=True,
        )
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="default activated",
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-alt",
            behavior_key="risk_assessment",
            version="1.1.0",
        )
    )
    registry.promote_plugin(
        "risk-alt",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    result = registry.force_enable_plugin(
        "risk-alt",
        audit_reason="operator activated alternate plugin",
    )

    assert result.registration.status == PluginLifecycleStatus.ACTIVE
    assert result.auto_disabled_plugin_ids == ["risk-default"]
    assert registry.get_registration("risk-alt").status == PluginLifecycleStatus.ACTIVE
    assert registry.get_registration("risk-default").status == PluginLifecycleStatus.DEGRADED

    appended_events = [call.args[0] for call in transcript_store.append.call_args_list]
    conflict_events = [
        event for event in appended_events if event["action"] == "auto_deactivated_conflict"
    ]
    assert conflict_events
    assert conflict_events[-1]["plugin_id"] == "risk-default"


def test_force_disable_restores_previous_official_release_for_single_plugin_behavior() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-default",
            behavior_key="risk_assessment",
            version="1.0.0",
            is_default_version=True,
        )
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="default activated",
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-legacy",
            behavior_key="risk_assessment",
            version="0.9.0",
            is_official_release=True,
        )
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-new",
            behavior_key="risk_assessment",
            version="1.2.0",
            is_official_release=True,
        )
    )
    registry.promote_plugin(
        "risk-new",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.force_enable_plugin(
        "risk-new",
        audit_reason="operator activated new version",
    )

    fallback = registry.force_disable_plugin(
        "risk-new",
        audit_reason="operator forced shutdown for regression",
    )

    assert registry.get_registration("risk-new").status == PluginLifecycleStatus.DEGRADED
    assert fallback.plugin_id == "risk-default"
    assert fallback.status == PluginLifecycleStatus.ACTIVE

    appended_events = [call.args[0] for call in transcript_store.append.call_args_list]
    force_disable_events = [
        event for event in appended_events if event["action"] == "force_disabled"
    ]
    fallback_enable_events = [
        event
        for event in appended_events
        if event["action"] == "force_enabled" and event["plugin_id"] == "risk-default"
    ]

    assert force_disable_events
    assert fallback_enable_events


def test_force_disable_uses_default_when_previous_official_release_is_deleted() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-default",
            behavior_key="risk_assessment",
            version="1.0.0",
            is_default_version=True,
        )
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.promote_plugin(
        "risk-default",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="default activated",
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-legacy",
            behavior_key="risk_assessment",
            version="0.9.0",
            is_official_release=True,
        )
    )
    registry.delete_plugin(
        "risk-legacy",
        audit_reason="legacy plugin removed from catalog",
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-new",
            behavior_key="risk_assessment",
            version="1.2.0",
            is_official_release=True,
        )
    )
    registry.promote_plugin(
        "risk-new",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.force_enable_plugin(
        "risk-new",
        audit_reason="operator activated new version",
    )

    fallback = registry.force_disable_plugin(
        "risk-new",
        audit_reason="candidate regression detected",
    )

    assert fallback.plugin_id == "risk-default"
    assert fallback.status == PluginLifecycleStatus.ACTIVE


def test_force_enable_rejects_non_official_plugin() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="draft-risk-plugin",
            behavior_key="risk_assessment",
            is_official_release=False,
        )
    )

    with pytest.raises(PermissionError):
        registry.force_enable_plugin(
            "draft-risk-plugin",
            audit_reason="operator attempted to force-enable draft plugin",
        )


def test_force_disable_rejects_last_active_plugin_without_fallback() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="solo-plugin",
            behavior_key="solo_behavior",
            is_default_version=True,
        )
    )
    registry.promote_plugin(
        "solo-plugin",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    registry.promote_plugin(
        "solo-plugin",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="default activated",
    )

    assert registry.can_force_disable_plugin("solo-plugin") is False

    with pytest.raises(ValueError, match="no fallback is available"):
        registry.force_disable_plugin(
            "solo-plugin",
            audit_reason="operator attempted unsafe shutdown",
        )


def test_runtime_resolution_requires_active_bound_plugin() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="timeline-probe",
            behavior_key="temporal_review",
        )
    )

    with pytest.raises(PluginNotBoundError, match="No active bound plugin"):
        registry.resolve_bound_plugins("temporal_review")

    registry.promote_plugin(
        "timeline-probe",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox review passed",
    )
    with pytest.raises(PluginNotBoundError, match="No active bound plugin"):
        registry.resolve_bound_plugins("temporal_review")

    registry.promote_plugin(
        "timeline-probe",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="production rollout approved",
    )
    resolved = registry.resolve_bound_plugins("temporal_review")
    assert [item.plugin_id for item in resolved] == ["timeline-probe"]


def test_runtime_usage_rejects_inactive_plugin_and_test_sandbox_isolated() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-preview",
            behavior_key="risk_assessment",
            is_official_release=False,
        )
    )

    with pytest.raises(PluginNotBoundError, match="not active"):
        registry.record_tool_usage("risk-preview")

    production_event_count = len(transcript_store.append.call_args_list)
    sandbox = registry.create_test_sandbox()
    test_registration = sandbox.resolve_plugin_for_test("risk-preview")
    sandbox.record_tool_usage("risk-preview")

    assert test_registration.plugin_id == "risk-preview"
    assert sandbox.get_registration("risk-preview").usage_count == 1
    assert registry.get_registration("risk-preview").usage_count == 0
    assert len(transcript_store.append.call_args_list) == production_event_count
