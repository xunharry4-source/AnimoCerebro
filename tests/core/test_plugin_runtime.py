from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError
import pytest

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_runtime import (
    PluginDegradeState,
    PluginHealthProbeResult,
    PluginLoadAction,
    PluginLoadResult,
    PluginRevocationRecord,
    PluginRollbackDecision,
)


def test_valid_rolled_back_plugin_load_result() -> None:
    health_probe = PluginHealthProbeResult(
        plugin_id="simulator-a",
        version="2.0.0",
        health_status=PluginHealthStatus.UNHEALTHY,
        checked_at=datetime.now(timezone.utc),
        latency_ms=180.0,
        timed_out=False,
        error_message="semantic divergence detected",
    )
    rollback_decision = PluginRollbackDecision(
        plugin_id="simulator-a",
        from_version="2.0.0",
        target_version="1.9.4",
        trigger_condition="semantic_divergence_detected",
        reason="rollback to audited stable sandbox",
        decided_at=datetime.now(timezone.utc),
        isolated=True,
    )

    result = PluginLoadResult(
        plugin_id="simulator-a",
        requested_version="2.0.0",
        effective_version="1.9.4",
        status=PluginLifecycleStatus.DEGRADED,
        action=PluginLoadAction.ROLLED_BACK,
        degrade_state=PluginDegradeState.ISOLATED,
        loaded_at=datetime.now(timezone.utc),
        health_probe=health_probe,
        audit_reason="new simulator violated sandbox safety invariants",
        error_message="rollback executed after unhealthy probe",
        rollback_target_version="1.9.4",
        rollback_decision=rollback_decision,
    )

    assert result.action == PluginLoadAction.ROLLED_BACK
    assert result.rollback_target_version == "1.9.4"
    assert result.rollback_decision.target_version == "1.9.4"
    assert result.degrade_state == PluginDegradeState.ISOLATED


def test_rolled_back_result_requires_target_version() -> None:
    rollback_decision = PluginRollbackDecision(
        plugin_id="weights-a",
        from_version="3.1.0",
        target_version="3.0.2",
        trigger_condition="risk_weight_drift",
        reason="restore conservative profile",
        decided_at=datetime.now(timezone.utc),
        isolated=False,
    )

    with pytest.raises(ValidationError) as exc_info:
        PluginLoadResult(
            plugin_id="weights-a",
            requested_version="3.1.0",
            effective_version="3.0.2",
            status=PluginLifecycleStatus.DEGRADED,
            action=PluginLoadAction.ROLLED_BACK,
            degrade_state=PluginDegradeState.DEGRADED,
            loaded_at=datetime.now(timezone.utc),
            audit_reason="drift exceeded approved threshold",
            rollback_decision=rollback_decision,
            error_message="profile isolated after drift",
        )

    assert "rollback_target_version" in str(exc_info.value)


def test_revoked_result_requires_audit_and_revocation_record() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PluginLoadResult(
            plugin_id="identity-pack-a",
            requested_version="5.2.0",
            effective_version="5.2.0",
            status=PluginLifecycleStatus.REVOKED,
            action=PluginLoadAction.REVOKED,
            degrade_state=PluginDegradeState.ISOLATED,
            loaded_at=datetime.now(timezone.utc),
            error_message="attempted privileged override",
        )

    message = str(exc_info.value)
    assert "Audit reason" in message or "revocation_record" in message


def test_unhealthy_health_probe_requires_error_message() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PluginHealthProbeResult(
            plugin_id="tool-a",
            version="1.3.0",
            health_status=PluginHealthStatus.UNHEALTHY,
            checked_at=datetime.now(timezone.utc),
            latency_ms=250.0,
            timed_out=False,
        )

    assert "error_message" in str(exc_info.value)


def test_revoked_result_accepts_full_audit_contract() -> None:
    health_probe = PluginHealthProbeResult(
        plugin_id="tool-b",
        version="4.0.0",
        health_status=PluginHealthStatus.UNHEALTHY,
        checked_at=datetime.now(timezone.utc),
        latency_ms=90.0,
        timed_out=False,
        error_message="attempted execution bypass",
    )
    revocation_record = PluginRevocationRecord(
        plugin_id="tool-b",
        version="4.0.0",
        reason="attempted execution bypass",
        revocation_condition="requested_host_execution_permission",
        recorded_at=datetime.now(timezone.utc),
    )

    result = PluginLoadResult(
        plugin_id="tool-b",
        requested_version="4.0.0",
        effective_version="4.0.0",
        status=PluginLifecycleStatus.REVOKED,
        action=PluginLoadAction.REVOKED,
        degrade_state=PluginDegradeState.ISOLATED,
        loaded_at=datetime.now(timezone.utc),
        health_probe=health_probe,
        audit_reason="tool attempted to cross the no-execution boundary",
        error_message="plugin revoked and isolated",
        revocation_record=revocation_record,
    )

    assert result.revocation_record is not None
    assert result.revocation_record.revocation_condition == "requested_host_execution_permission"
    assert result.status == PluginLifecycleStatus.REVOKED
