from __future__ import annotations

from unittest.mock import Mock

import pytest

from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderRemoteError,
)
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from plugins.nine_questions.q3_what_do_i_have import build_q3_what_do_i_have_plugin


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


def test_q3_what_do_i_have_inventory_degraded_and_offline_agent_removed(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "unified_asset_inventory": {
                "available_cognitive_tools": ["risk-comparator", "task-decomposer"],
                "available_execution_tools": ["execution:local_system"],
                "connected_agents": [
                    {"agent_id": "peer-1", "status": "online", "capabilities": ["review"]},
                ],
                "activated_strategy_patches": ["patch:auditing:v1"],
                "accessible_workspace_zones": ["src/", "docs/"],
            },
            "resource_evaluation": {
                "resource_status": "degraded",
                "missing_critical_assets": ["缺少在线 browser agent"],
                "bottleneck_node": "agent_connectivity",
            },
        }
    )

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q3_what_do_i_have_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q3",
        "decision_id": "decision:q3",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "workspace_assets": {
                "accessible_workspace_zones": ["src/", "docs/"],
                "core_directories": ["src/", "docs/"],
                "core_files": ["src/main.py", "docs/README.md"],
            },
            "active_tools": {
                "available_cognitive_tools": ["risk-comparator", "task-decomposer"],
                "available_execution_tools": ["execution:local_system"],
            },
            "connected_agents": [
                {"agent_id": "openClaw", "status": "offline", "capabilities": ["browser"]},
                {"agent_id": "peer-1", "status": "online", "capabilities": ["review"]},
            ],
            "loaded_memories": {"activated_strategy_patches": ["patch:auditing:v1"]},
            "permissions": {
                "tenant_scope": "dev",
                "brain_scope": "local",
                "tokens": ["llm"],
                "accessible_workspace_zones": ["src/", "docs/"],
            },
        },
    }

    result = plugin.run_tool(context)
    assert "resource_status=degraded" in result.summary
    inventory = result.context_updates["q3_unified_asset_inventory"]
    assert all(agent.get("status") != "offline" for agent in inventory["connected_agents"])

    kwargs = provider.generate_json.call_args.kwargs
    assert isinstance(kwargs["caller_context"], ModelProviderCallerContext)
    assert kwargs["caller_context"].source_module == "q3_what_do_i_have_plugin"
    assert kwargs["caller_context"].question_driver_refs == ["我有什么"]
    assert "认知工具目录" in kwargs["prompt"]
    assert "Execution Domains (Physical Drivers)" not in kwargs["prompt"]

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED.value in types


def test_q3_what_do_i_have_fail_closed_and_provenance_injected(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(side_effect=ModelProviderRemoteError("remote 500"))

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q3_what_do_i_have_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q3",
        "decision_id": "decision:q3",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "workspace_assets": {"accessible_workspace_zones": ["src/"]},
            "active_tools": {"available_cognitive_tools": [], "available_execution_tools": []},
            "connected_agents": [],
            "loaded_memories": {"activated_strategy_patches": []},
            "permissions": {"tenant_scope": "dev", "brain_scope": "local", "tokens": []},
        },
    }

    with pytest.raises(ModelProviderRemoteError):
        plugin.run_tool(context)

    kwargs = provider.generate_json.call_args.kwargs
    assert kwargs["caller_context"].question_driver_refs == ["我有什么"]
    assert kwargs["caller_context"].source_module == "q3_what_do_i_have_plugin"

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_FAILED.value in types
