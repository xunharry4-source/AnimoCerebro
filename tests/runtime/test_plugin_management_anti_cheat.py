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
from zentex.core.model_provider_spec import ModelProviderCallerContext  # noqa: E402
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.common.plugin_registry import PluginNotBoundError  # noqa: E402
from zentex.tasks.llm_decomposer import LLMTaskDecomposerPlugin  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402


def _tool(
    *,
    plugin_id: str,
    behavior_key: str,
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
    is_official_release: bool = True,
    supports_multi_active: bool = False,
) -> CognitiveToolSpec:
    return CognitiveToolSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["regression"],
        revocation_reasons=["reserved"],
        tool_type="analysis",
        purpose="test tool",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        required_context=["working_memory"],
        trigger_conditions=["metacognition"],
        behavior_key=behavior_key,
        supports_multi_active=supports_multi_active,
        is_default_version=False,
        is_official_release=is_official_release,
        do_not_use_when=["unsafe_external_action"],
    )


def test_unactivated_candidate_is_hard_blocked() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(_tool(plugin_id="candidate-a", behavior_key="family-a"))

    with pytest.raises(PluginNotBoundError):
        registry.resolve_bound_plugins("family-a")


def test_force_enable_rejects_candidate_plugins() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)
    registry.register(_tool(plugin_id="candidate-b", behavior_key="family-b"))

    with pytest.raises(PermissionError, match="Candidate plugins must be promoted"):
        registry.force_enable_plugin("candidate-b", audit_reason="attempted bypass")


def test_rule_based_test_stub_isolated_from_production_registry() -> None:
    transcript_store = Mock()
    registry = CognitiveToolRegistry(transcript_store=transcript_store)

    with pytest.raises(PermissionError, match="test_stub plugins must not be registered"):
        registry.register(_tool(plugin_id="stub-a", behavior_key="family-a"), source_kind="test_stub")

    sandbox = registry.create_test_sandbox()
    reg = sandbox.register_test_stub(_tool(plugin_id="stub-b", behavior_key="family-a"))
    assert reg is not None
    assert reg.source_kind == "test_stub"

    # Production audit sink must remain untouched by sandbox operations.
    assert transcript_store.append.call_count == 0


def test_rogue_cognitive_tool_spec_boundary_rejected() -> None:
    # read_only=False violates CognitiveToolSpec boundary validator.
    with pytest.raises(ValueError, match="read_only=True"):
        CognitiveToolSpec(
            plugin_id="rogue",
            version="1.0.0",
            is_concurrency_safe=True,
            status=PluginLifecycleStatus.CANDIDATE,
            health_status=PluginHealthStatus.HEALTHY,
            rollback_conditions=["regression"],
            revocation_reasons=["reserved"],
            tool_type="analysis",
            purpose="rogue tool",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_context=["working_memory"],
            trigger_conditions=["metacognition"],
            behavior_key="rogue",
            supports_multi_active=False,
            is_default_version=False,
            is_official_release=True,
            do_not_use_when=["unsafe_external_action"],
            read_only=False,
            side_effect_free=True,
        )


def test_llm_task_decomposer_preserves_caller_context_provenance() -> None:
    mock_provider = Mock()
    mock_provider.generate_json.return_value = {
        "subtasks": [
            {
                "local_id": "step-1",
                "title": "Investigate",
                "task_type": "cognitive_step",
                "content": "Read logs",
                "objective": "Find root cause",
                "requirements": [],
                "depends_on": [],
                "coordination_mode": "sequential",
            }
        ]
    }

    store = BrainTranscriptStore("/tmp/test_llm_task_decomposer_transcript.jsonl")
    plugin = LLMTaskDecomposerPlugin(model_provider=mock_provider, transcript_store=store)
    subtasks = plugin.decompose_mission("Demo Mission", "Demo context")
    assert subtasks and subtasks[0]["local_id"] == "step-1"

    _, kwargs = mock_provider.generate_json.call_args
    caller_context = kwargs["caller_context"]
    assert isinstance(caller_context, ModelProviderCallerContext)
    assert caller_context.question_driver_refs
    assert "mission_decomposition" in caller_context.question_driver_refs
