import pytest
from unittest.mock import MagicMock

from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.transcript import BrainTranscriptStore
from plugins.nine_questions.q5_what_am_i_allowed_to_do.q5_what_am_i_allowed_to_do_plugin import (
    build_q5_what_am_i_allowed_to_do_plugin,
)


def test_q5_precise_permission_inference():
    """
    断言 1（精确权限推演）：
    Mock 传入一个 trust_level=pending 的 Agent 以及 allow_outbound=False 的联系策略。
    强断言大模型正确返回了 PermissionBoundary，且 interaction_scope 被收紧。
    """
    print("Running Q5 Assertion Test 1: Precise Permission Inference...")
    
    # 1. Setup Mock Provider
    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.status = PluginLifecycleStatus.ACTIVE
    mock_provider.plugin_kind.return_value = "model_provider"
    
    # Expected LLM Response
    mock_response = {
        "authorization_boundary_profile": {
            "allowed_action_space": ["read_workspace_state"],
            "forbidden_action_space": [
                {"action": "outbound_request_help", "reason": "contact policy forbids outbound"}
            ],
            "contact_and_org_boundaries": {
                "interaction_scope": "disabled",
                "requires_human_confirmation": True,
                "requires_cloud_audit": False,
            },
            "requires_escalation_actions": ["delegate_to_human"],
        }
    }
    mock_provider.generate_json.return_value = mock_response
    
    # 2. Setup Mock Transcript Store
    mock_transcript = MagicMock(spec=BrainTranscriptStore)
    
    # 3. Setup Context with "Hard Policy"
    context = {
        "model_provider": mock_provider,
        "transcript_store": mock_transcript,
        "context_snapshot": {
            "contact_policy": {
                "allow_outbound": False,
                "allow_inbound": False,
                "whitelist": []
            },
            "q4_capability_boundary_profile": {
                "actionable_space": ["read_workspace_state"],
            },
            "q3_connected_agents": [
                {
                    "agent_id": "agent-x-pending",
                    "trust_level": "pending",
                    "scope": "read_only"
                }
            ],
            "q2_identity_hard_bans": ["forbidden_key_access"],
            "safety_gate_config": {
                "high_risk_interception": True,
                "requires_cloud_audit": False,
                "human_intervention_mode": "read_only"
            }
        },
        "session_id": "audited-session-555",
        "turn_id": "audited-turn-001"
    }
    
    # 4. Execute Plugin
    plugin = build_q5_what_am_i_allowed_to_do_plugin()
    result = plugin.run_tool(context)
    
    # 5. Assertions
    # A. Check Traceability
    args, kwargs = mock_provider.generate_json.call_args
    caller_context: ModelProviderCallerContext = kwargs["caller_context"]
    assert caller_context.source_module == "q5_what_am_i_allowed_to_do_plugin"
    assert "我被允许做什么" in caller_context.question_driver_refs
    
    # B. Check Input Propagation 
    input_context = kwargs["context"]
    assert input_context["contact_policy"]["allow_outbound"] is False
    assert input_context["q3_connected_agents"][0]["trust_level"] == "pending"
    
    # C. Check Output Correctness
    profile = result.context_updates["q5_authorization_boundary_profile"]
    assert profile["allowed_action_space"] == ["read_workspace_state"]
    assert profile["contact_and_org_boundaries"]["interaction_scope"] == "disabled"
    assert "delegate_to_human" in profile["requires_escalation_actions"]
    
    print("PASS: Q5 Precise Permission Inference Verified.")


def test_q5_anti_forgery_block():
    """
    断言 2（防伪造阻断）：
    Mock 大模型抛出 500 异常，强制断言插件崩溃抛错，证明系统绝对没有生成伪造的权限对象。
    """
    print("Running Q5 Assertion Test 2: Anti-Forgery Block...")
    
    # 1. Setup Mock Provider to FAIL
    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.status = PluginLifecycleStatus.ACTIVE
    mock_provider.plugin_kind.return_value = "model_provider"
    mock_provider.generate_json.side_effect = RuntimeError("LLM_SERVICE_UNAVAILABLE_500")
    
    # 2. Setup Mock Transcript Store
    mock_transcript = MagicMock(spec=BrainTranscriptStore)
    
    # 3. Setup Context
    context = {
        "model_provider": mock_provider,
        "transcript_store": mock_transcript,
        "context_snapshot": {
            "contact_policy": {},
            "q3_connected_agents": [],
            "safety_gate_config": {}
        }
    }
    
    # 4. Execute & Expect CRASH
    plugin = build_q5_what_am_i_allowed_to_do_plugin()
    
    with pytest.raises(RuntimeError) as excinfo:
        plugin.run_tool(context)
        
    assert "LLM_SERVICE_UNAVAILABLE_500" in str(excinfo.value)
    
    print("PASS: Q5 Anti-Forgery Block Verified. No mock fallback generated.")
