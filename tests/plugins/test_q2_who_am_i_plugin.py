from __future__ import annotations

from unittest.mock import Mock

import pytest

from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderRemoteError,
)
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from plugins.nine_questions.q2_who_am_i import build_q2_who_am_i_plugin


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


def test_q2_who_am_i_dynamic_inference_and_continuity_inherits_kernel_constraints(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "role_profile": {
                "identity_role": "Zentex 独立外部大脑",
                "active_role": "财务合规审计员",
                "task_role": "证据链核查者",
            },
            "mission_boundary": {
                "current_mission": "在财务审计场景下提供可审计、可回放的结论与建议",
                "priority_duties": ["保持审计链路完整", "明确 LLM 不可用时阻断"],
                "continuity_boundaries": [
                    "禁止篡改审计日志",
                    "禁止越权执行",
                ],
            },
        }
    )

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q2_who_am_i_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q2",
        "decision_id": "decision:q2",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "q1_scene_model": {
                "primary_domain": "财务账单",
                "secondary_domains": ["代码实现"],
                "environment_type": "audit_console",
                "change_rate": "medium",
            },
            "q1_uncertainty_profile": {
                "uncertainty_intensity": 0.6,
                "risk_sources": ["mixed_workspace", "missing_agent"],
            },
            "identity_kernel_snapshot": {
                "meta_drives": ["可审计", "主体连续性"],
                "value_vetoes": ["禁止伪造"],
                "non_bypassable_constraints": ["禁止篡改审计日志", "禁止越权执行"],
            },
            "manual_role_overrides": {},
        },
    }

    result = plugin.run_tool(context)
    assert "active_role=财务合规审计员" in result.summary
    boundary = result.context_updates["q2_mission_boundary"]
    assert "禁止篡改审计日志" in boundary["continuity_boundaries"]

    kwargs = provider.generate_json.call_args.kwargs
    assert isinstance(kwargs["caller_context"], ModelProviderCallerContext)
    assert kwargs["caller_context"].source_module == "q2_who_am_i_plugin"
    assert kwargs["caller_context"].question_driver_refs == ["我是谁"]
    prompt = kwargs["prompt"]
    assert "角色定义包" in prompt
    assert "不可绕过约束" in prompt
    assert "{'identity_role'" not in prompt
    assert "{'non_bypassable_constraints'" not in prompt

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED.value in types


def test_q2_who_am_i_fail_closed_and_provenance_injected(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(side_effect=ModelProviderRemoteError("remote 500"))

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q2_who_am_i_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q2",
        "decision_id": "decision:q2",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "q1_scene_model": {"primary_domain": "财务账单", "secondary_domains": [], "environment_type": "audit", "change_rate": "low"},
            "q1_uncertainty_profile": {"uncertainty_intensity": 0.9, "risk_sources": ["missing_evidence"]},
            "identity_kernel_snapshot": {"meta_drives": [], "value_vetoes": [], "non_bypassable_constraints": ["禁止篡改审计日志"]},
            "manual_role_overrides": {"active_role_override": "人类指定角色"},
        },
    }

    with pytest.raises(ModelProviderRemoteError):
        plugin.run_tool(context)

    kwargs = provider.generate_json.call_args.kwargs
    assert kwargs["caller_context"].question_driver_refs == ["我是谁"]
    assert kwargs["caller_context"].source_module == "q2_who_am_i_plugin"

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_FAILED.value in types
