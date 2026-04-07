import asyncio
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.transcript import BrainTranscriptStore
from plugins.nine_questions.q6_consequences.q6_what_should_i_not_do_plugin import (
    build_q6_what_should_i_not_do_plugin,
    Q6WhatShouldINotDoPlugin
)


@pytest.mark.asyncio
async def test_q6_bottom_line_defense_assertion():
    """
    断言 1（底线防线断言）：
    Mock 传入包含“系统级文件写入权限”的动作空间和“禁止破坏宿主系统”的身份内核。
    强断言大模型正确返回了 ForbiddenZoneProfile。
    """
    print("Running Q6 Assertion Test 1: Bottom-line Defense Assertion...")
    
    # 1. Setup Mock Provider
    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.status = PluginLifecycleStatus.ACTIVE
    mock_provider.plugin_kind.return_value = "model_provider"
    
    # Expected LLM Response
    mock_response = {
        "forbidden_zone_profile": {
            "absolute_red_lines": ["forbidden_key_access", "identity_modification"],
            "performance_tradeoff_bans": ["silent_skip_confirmation", "unauthorized_write_host_config"],
            "prohibited_strategies": ["aggressive_caching_of_vulnerable_data"],
            "contamination_risks": ["identity_leakage_to_untrusted_agent"]
        }
    }
    mock_provider.generate_json.return_value = mock_response
    
    # 2. Setup Mock Transcript Store
    mock_transcript = MagicMock(spec=BrainTranscriptStore)
    
    # 3. Setup Context with "Actionable Space" and "Identity Constraints"
    context = {
        "model_provider": mock_provider,
        "transcript_store": mock_transcript,
        "context_snapshot": {
            "identity_kernel": {
                "non_bypassable_constraints": ["absolute_host_system_integrity"],
                "values": ["safe_orchestration"]
            },
            "q4_capability_boundary_profile": {
                "actionable_space": ["read_config", "write_host_config", "execute_shell"]
            },
            "q5_permission_boundary": {
                "execution_tier": "constrained_execute"
            },
            "memory_strategy_bans": ["previous_crash_on_write_host_config"]
        }
    }
    
    # 4. Execute Plugin
    plugin = build_q6_what_should_i_not_do_plugin()
    result = plugin.run_tool(context)
    
    # 5. Assertions
    # A. Check Traceability
    _, kwargs = mock_provider.generate_json.call_args
    caller_context: ModelProviderCallerContext = kwargs["caller_context"]
    assert caller_context.source_module == "q6_what_should_i_not_do_plugin"
    assert "我即使能做也不该做什么" in caller_context.question_driver_refs
    
    # B. Check Input Propagation 
    input_context = kwargs["context"]
    assert "write_host_config" in input_context["q4_actionable_space"]
    assert "absolute_host_system_integrity" in input_context["identity_kernel"]["non_bypassable_constraints"]
    
    # C. Check Output result
    profile = result.context_updates["q6_forbidden_zone_profile"]
    assert "unauthorized_write_host_config" in profile["performance_tradeoff_bans"]
    assert "identity_modification" in profile["absolute_red_lines"]
    
    print("PASS: Q6 Bottom-line Defense Verified.")


@pytest.mark.asyncio
async def test_q6_anti_forgery_block():
    """
    断言 2（防伪造阻断）：
    Mock 大模型抛出 500 异常，强制断言插件崩溃抛错，确认系统绝无 mock 兜底。
    """
    print("Running Q6 Assertion Test 2: Anti-Forgery Block...")
    
    # 1. Setup Mock Provider to FAIL
    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.status = PluginLifecycleStatus.ACTIVE
    mock_provider.plugin_kind.return_value = "model_provider"
    mock_provider.generate_json.side_effect = RuntimeError("LLM_TIMEOUT")
    
    # 2. Setup Mock Transcript Store
    mock_transcript = MagicMock(spec=BrainTranscriptStore)
    
    # 3. Setup Context
    context = {
        "model_provider": mock_provider,
        "transcript_store": mock_transcript,
        "context_snapshot": {}
    }
    
    # 4. Execute & Expect CRASH
    plugin = build_q6_what_should_i_not_do_plugin()
    
    with pytest.raises(RuntimeError) as excinfo:
        plugin.run_tool(context)
        
    assert "Q6 Forbidden Zone Inference Failed" in str(excinfo.value)
    
    print("PASS: Q6 Anti-Forgery Block Verified. No fake fallback generated.")


if __name__ == "__main__":
    # Standalone script runner
    try:
        asyncio.run(test_q6_bottom_line_defense_assertion())
        asyncio.run(test_q6_anti_forgery_block())
        print("\nALL Q6 REDLINE DEFENSE TESTS PASSED.")
    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        exit(1)
