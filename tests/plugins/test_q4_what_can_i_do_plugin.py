from __future__ import annotations

from unittest.mock import Mock

import pytest

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderRemoteError
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from plugins.nine_questions.q4_what_can_i_do import build_q4_what_can_i_do_plugin


def _read_jsonl(path):
    import json

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_q4_what_can_i_do_anti_hallucination_read_only_strips_write_actions(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "capability_boundary_profile": {
                "capability_upper_limits": ["仅能进行静态分析与只读审计"],
                "actionable_space": ["read logs", "static analyze code"],
                "executable_strategies": ["request human permission upgrade"],
            }
        }
    )

    store = BrainTranscriptStore(tmp_path / "transcript.jsonl")
    plugin = build_q4_what_can_i_do_plugin()

    context = {
        "session_id": "s",
        "turn_id": "t",
        "trace_id": "trace:q4",
        "decision_id": "decision:q4",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "snapshot_version": 3,
            "q1_scene_model": {"primary_domain": "审计", "secondary_domains": [], "environment_type": "console", "change_rate": "low"},
            "q1_uncertainty_profile": {"uncertainty_intensity": 0.2, "risk_sources": []},
            "q2_role_profile": {"identity_role": "Zentex", "active_role": "审计员", "task_role": "能力评估"},
            "q2_mission_boundary": {"current_mission": "能力边界", "priority_duties": [], "continuity_boundaries": ["禁止伪造能力"]},
            "q3_unified_asset_inventory": {
                "available_cognitive_tools": ["risk-comparator"],
                "available_execution_tools": [],
                "connected_agents": [],
                "activated_strategy_patches": [],
                "accessible_workspace_zones": ["src/"],
                "permissions": {"mode": "read_only"},
            },
            "q3_resource_evaluation": {"resource_status": "degraded", "missing_critical_assets": ["no exec"], "bottleneck_node": "execution_tools"},
        },
    }

    result = plugin.run_tool(context)
    profile = result.context_updates["q4_capability_boundary_profile"]
    assert all("write" not in str(item).lower() for item in profile["actionable_space"])

    kwargs = provider.generate_json.call_args.kwargs
    assert isinstance(kwargs["caller_context"], ModelProviderCallerContext)
    assert kwargs["caller_context"].source_module == "q4_what_can_i_do_plugin"
    assert kwargs["caller_context"].question_driver_refs == ["我能做什么"]
    prompt = kwargs["prompt"]
    assert "执行工具目录" in prompt
    assert "Q3 资产清单" in prompt
    assert "{'available_cognitive_tools'" not in prompt

    rows = _read_jsonl(store.file_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED.value in types


def test_q4_what_can_i_do_fail_closed(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(side_effect=ModelProviderRemoteError("remote 500"))

    store = BrainTranscriptStore(tmp_path / "transcript.jsonl")
    plugin = build_q4_what_can_i_do_plugin()

    context = {
        "session_id": "s",
        "turn_id": "t",
        "trace_id": "trace:q4",
        "decision_id": "decision:q4",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "snapshot_version": 3,
            "q1_scene_model": {"primary_domain": "审计", "secondary_domains": [], "environment_type": "console", "change_rate": "low"},
            "q1_uncertainty_profile": {"uncertainty_intensity": 0.2, "risk_sources": []},
            "q2_role_profile": {"identity_role": "Zentex", "active_role": "审计员", "task_role": "能力评估"},
            "q2_mission_boundary": {"current_mission": "能力边界", "priority_duties": [], "continuity_boundaries": ["禁止伪造能力"]},
            "q3_unified_asset_inventory": {"available_cognitive_tools": [], "available_execution_tools": [], "connected_agents": [], "activated_strategy_patches": [], "accessible_workspace_zones": [], "permissions": {"mode": "read_only"}},
            "q3_resource_evaluation": {"resource_status": "critically_lacking", "missing_critical_assets": ["llm"], "bottleneck_node": "llm"},
        },
    }

    with pytest.raises(ModelProviderRemoteError):
        plugin.run_tool(context)

    kwargs = provider.generate_json.call_args.kwargs
    assert kwargs["caller_context"].question_driver_refs == ["我能做什么"]
    rows = _read_jsonl(store.file_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_FAILED.value in types
