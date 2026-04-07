from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.weights.subjective_weight_plugin import (  # noqa: E402
    RationalAuditRejectError,
    SubjectiveWeightPlugin,
    WeightPluginAssembler,
    build_default_conservative_weight,
    build_risk_balanced_weight,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402


def test_invalid_weight_payload_rolls_back_to_conservative_default() -> None:
    assembler = WeightPluginAssembler()

    dirty_payload = {
        "plugin_id": "dirty-risk-profile",
        "version": "9.9.9",
        "is_concurrency_safe": True,
        "status": PluginLifecycleStatus.ACTIVE,
        "health_status": PluginHealthStatus.HEALTHY,
        "rollback_conditions": ["weight_drift_detected"],
        "revocation_reasons": ["reserved_for_weight_audit"],
        "purpose": "Unsafe risk-seeking profile",
        "risk_tolerance": 1.8,
        "cost_sensitivity": 0.05,
        "creativity_bias": 0.05,
        "continuity_bias": 0.05,
        "rationale_tags": ["unsafe"],
    }

    try:
        SubjectiveWeightPlugin.model_validate(dirty_payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("Dirty payload should fail Pydantic validation.")

    mounted = assembler.mount_plugin_payload(dirty_payload)

    assert mounted.plugin_id == "default_conservative_weight"
    assert assembler.active_plugin.plugin_id == "default_conservative_weight"
    assert assembler.weight_fallback_occurred is True
    assert assembler.fallback_reason is not None


def test_rational_audit_rejection_rolls_back_without_crashing() -> None:
    audit_client = Mock()
    audit_client.evaluate.side_effect = RationalAuditRejectError("G25 rejected drifted weights")
    assembler = WeightPluginAssembler(audit_client=audit_client)
    candidate = build_risk_balanced_weight()

    mounted = assembler.mount_plugin(candidate)

    assert mounted.plugin_id == build_default_conservative_weight().plugin_id
    assert assembler.active_plugin.plugin_id == "default_conservative_weight"
    assert assembler.weight_fallback_occurred is True
    assert "G25 rejected" in (assembler.fallback_reason or "")
