from __future__ import annotations

from pathlib import Path
import sys

from pydantic import ValidationError
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.cognitive_tools_spec import CognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus


def _valid_payload() -> dict[str, object]:
    return {
        "plugin_id": "tool-risk-comparator",
        "version": "1.0.0",
        "is_concurrency_safe": True,
        "status": PluginLifecycleStatus.ACTIVE,
        "health_probe_endpoint": "/health/tools/risk-comparator",
        "rollback_conditions": [
            "returned_external_action_payload",
            "attempted_host_execution",
        ],
        "revocation_reasons": [
            "reserved_for_audit_if_revoked",
        ],
        "tool_type": "risk_comparator",
        "purpose": "Compare alternative cognitive options and rank risk tradeoffs.",
        "input_schema": {"type": "object", "required": ["candidates"]},
        "output_schema": {"type": "object", "required": ["ranked_options"]},
        "required_context": ["working_memory", "conflict_snapshot"],
        "trigger_conditions": ["high_risk", "multiple_options_present"],
        "behavior_key": "risk_assessment",
        "do_not_use_when": ["missing_candidates", "read_only_boundary_unknown"],
        "read_only": True,
        "side_effect_free": True,
    }


def test_cognitive_tool_rejects_non_read_only_or_side_effecting_tool() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CognitiveToolSpec.model_validate(
            {
                **_valid_payload(),
                "read_only": False,
            }
        )

    assert "Cognitive tools must be strictly read_only=True and side_effect_free=True" in str(
        exc_info.value
    )

    with pytest.raises(ValidationError) as second_exc:
        CognitiveToolSpec.model_validate(
            {
                **_valid_payload(),
                "side_effect_free": False,
            }
        )

    assert "Cognitive tools must be strictly read_only=True and side_effect_free=True" in str(
        second_exc.value
    )


def test_cognitive_tool_requires_explicit_trigger_conditions() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CognitiveToolSpec.model_validate(
            {
                **_valid_payload(),
                "trigger_conditions": [],
            }
        )

    assert "Cognitive tools must declare trigger_conditions" in str(
        exc_info.value
    )


def test_cognitive_tool_validly_inherits_base_plugin_contract() -> None:
    tool = CognitiveToolSpec.model_validate(_valid_payload())

    assert tool.plugin_id == "tool-risk-comparator"
    assert tool.status == PluginLifecycleStatus.ACTIVE
    assert tool.version == "1.0.0"
    assert tool.rollback_conditions == [
        "returned_external_action_payload",
        "attempted_host_execution",
    ]
    assert tool.tool_type == "risk_comparator"
    assert tool.read_only is True
    assert tool.side_effect_free is True
