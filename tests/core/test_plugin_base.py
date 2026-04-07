from __future__ import annotations

from pydantic import ValidationError
import pytest

from zentex.core.plugin_base import (
    BasePluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)


class DemoPluginSpec(BasePluginSpec):
    @classmethod
    def plugin_kind(cls) -> str:
        return "demo"


def test_active_plugin_without_rollback_conditions_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DemoPluginSpec(
            plugin_id="demo-plugin",
            version="1.0.0",
            is_concurrency_safe=True,
            status=PluginLifecycleStatus.ACTIVE,
            health_probe_endpoint="/healthz/demo-plugin",
            rollback_conditions=[],
            revocation_reasons=["reserved_for_future_audit"],
        )

    assert "Active plugins must explicitly define rollback_conditions" in str(exc_info.value)


def test_revoked_plugin_without_reasons_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DemoPluginSpec(
            plugin_id="demo-plugin",
            version="1.0.0",
            is_concurrency_safe=False,
            status=PluginLifecycleStatus.REVOKED,
            health_status=PluginHealthStatus.UNHEALTHY,
            rollback_conditions=["signature_verification_failed"],
            revocation_reasons=[],
        )

    assert "Must provide reasons for degradation or revocation" in str(exc_info.value)


def test_candidate_to_sandbox_verified_to_active_flow_and_serialization() -> None:
    candidate = DemoPluginSpec(
        plugin_id="demo-plugin",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        health_probe_endpoint="/healthz/demo-plugin",
        rollback_conditions=[
            "signature_verification_failed",
            "privilege_escalation_attempted",
        ],
        revocation_reasons=["reserved_for_audit_if_revoked"],
    )

    sandbox_verified = candidate.transition_to(PluginLifecycleStatus.SANDBOX_VERIFIED)
    active = sandbox_verified.transition_to(PluginLifecycleStatus.ACTIVE)

    assert candidate.status == PluginLifecycleStatus.CANDIDATE
    assert sandbox_verified.status == PluginLifecycleStatus.SANDBOX_VERIFIED
    assert active.status == PluginLifecycleStatus.ACTIVE
    assert active.rollback_conditions == [
        "signature_verification_failed",
        "privilege_escalation_attempted",
    ]

    payload = active.model_dump()
    restored = DemoPluginSpec.model_validate(payload)
    restored_from_json = DemoPluginSpec.model_validate_json(active.model_dump_json())

    assert payload["plugin_id"] == "demo-plugin"
    assert payload["status"] == PluginLifecycleStatus.ACTIVE
    assert restored == active
    assert restored_from_json == active
