from __future__ import annotations

from unittest.mock import Mock

import pytest

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderRemoteError
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from plugins.nine_questions.q5_what_am_i_allowed_to_do import build_q5_what_am_i_allowed_to_do_plugin


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


def test_q5_allowed_space_is_strict_subset_of_q4_actionable_space(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "authorization_boundary_profile": {
                "allowed_action_space": ["read logs"],
                "forbidden_action_space": [
                    {"action": "delete global logs", "reason": "read_only tenant"}
                ],
                "contact_and_org_boundaries": {"contact_enabled": False},
                "requires_escalation_actions": ["request human confirmation"],
            }
        }
    )

    store = BrainTranscriptStore(tmp_path / "transcript.jsonl")
    plugin = build_q5_what_am_i_allowed_to_do_plugin()

    context = {
        "session_id": "s",
        "turn_id": "t",
        "trace_id": "trace:q5",
        "decision_id": "decision:q5",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "snapshot_version": 9,
            "q4_capability_boundary_profile": {
                "actionable_space": ["read logs", "delete global logs", "request human confirmation"]
            },
            "contact_policy": {"contact_enabled": False, "whitelist": []},
            "tenant_scope": {"tenant_scope": "dev", "secrecy_level": "low", "mode": "read_only"},
            "agent_trust_policy": {"default_trust_level": "read_only", "allowed_scopes": ["read_only"]},
            "q3_connected_agents": [{"agent_id": "peer-1", "trust_level": "read_only", "scope": "read_only"}],
        },
    }

    result = plugin.run_tool(context)
    profile = result.context_updates["q5_authorization_boundary_profile"]
    assert set(profile["allowed_action_space"]).issubset(
        set(context["context_snapshot"]["q4_capability_boundary_profile"]["actionable_space"])
    )

    kwargs = provider.generate_json.call_args.kwargs
    assert isinstance(kwargs["caller_context"], ModelProviderCallerContext)
    assert kwargs["caller_context"].source_module == "q5_what_am_i_allowed_to_do_plugin"
    assert kwargs["caller_context"].question_driver_refs == ["我被允许做什么"]
    prompt = kwargs["prompt"]
    assert "Q4 能力边界" in prompt
    assert "allowed_action_space" in prompt
    assert "{'actionable_space'" not in prompt

    rows = _read_jsonl(store.file_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED.value in types


def test_q5_fail_closed(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(side_effect=ModelProviderRemoteError("remote 500"))

    store = BrainTranscriptStore(tmp_path / "transcript.jsonl")
    plugin = build_q5_what_am_i_allowed_to_do_plugin()

    context = {
        "session_id": "s",
        "turn_id": "t",
        "trace_id": "trace:q5",
        "decision_id": "decision:q5",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "snapshot_version": 9,
            "q4_capability_boundary_profile": {"actionable_space": ["read logs"]},
            "contact_policy": {"contact_enabled": False},
            "tenant_scope": {"tenant_scope": "dev"},
            "agent_trust_policy": {"default_trust_level": "read_only"},
            "q3_connected_agents": [],
        },
    }

    with pytest.raises(ModelProviderRemoteError):
        plugin.run_tool(context)

    kwargs = provider.generate_json.call_args.kwargs
    assert kwargs["caller_context"].question_driver_refs == ["我被允许做什么"]
    rows = _read_jsonl(store.file_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_FAILED.value in types
