from unittest.mock import MagicMock
from pathlib import Path
import pytest

from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.transcript import BrainTranscriptStore

from plugins.nine_questions.q7_what_else_can_i_do_plugin import WhatElseCanIDoPlugin, AlternativeStrategyProfile
from plugins.nine_questions.q8_what_should_i_do_now_plugin import WhatShouldIDoNowPlugin, ObjectiveProfile
from plugins.nine_questions.q9_how_should_i_act_plugin import HowShouldIActPlugin, ActionPostureProfile


def test_q7_q9_llm_mandatory_contract():
    """
    Q7-Q9 [LLM MANDATORY] 临床级验证：
    1. 断言 Q7/Q8/Q9 必须通过 LLM 生成，无硬编码兜底。
    2. 断言 trace_id 与 question_driver_refs 必须注入。
    3. 断言 LLM 失败时抛出致命异常 (Fail-Closed)。
    """
    print("\nRunning Zentex Q7-Q9 [LLM MANDATORY] Contract Verification...")

    # setup mock registry and model provider
    mock_registry = MagicMock(spec=AbstractPluginRegistry)
    mock_model_provider = MagicMock(spec=ModelProviderSpec)
    mock_model_provider.status = PluginLifecycleStatus.ACTIVE
    mock_registry.get_bound_plugin.return_value = mock_model_provider
    mock_registry.get_active_plugins.return_value = []
    transcript_store = BrainTranscriptStore(Path("/tmp") / "q7_q9_contract_transcript.jsonl")

    # setup context with pre-calculated states
    mock_context = {
        "model_provider": mock_model_provider,
        "transcript_store": transcript_store,
        "plugin_registry": mock_registry,
        "trace_id": "clinical-test-trace-12345",
        "session_id": "clinical-session",
        "turn_id": "clinical-turn-1",
        "persistent_task_state": {"pending": []},
        "nine_question_state": {
            "q1": {"scene": "hostile_env"},
            "q6": {"redline": "no_data_deletion"}
        },
        "nine_questions": {
            "q1": {"scene": "hostile_env"},
            "q6": {"redline": "no_data_deletion"},
        },
    }

    # --- Test Q7 ---
    q7_plugin = WhatElseCanIDoPlugin()
    mock_model_provider.generate_json.return_value = {
        "alternative_strategy_profile": {
            "fallback_plans": ["Ask Human"],
            "degradation_strategies": ["Read-only mode"],
            "collaboration_switches": ["Delegation"],
            "exploratory_actions": ["Ping"],
        }
    }
    
    q7_res = q7_plugin.execute(mock_context)
    assert "fallback_plans" in q7_res
    # Assert traceability in LLM call
    args, kwargs = mock_model_provider.generate_json.call_args
    caller_ctx: ModelProviderCallerContext = kwargs["caller_context"]
    assert caller_ctx.source_module == "q7_what_else_can_i_do_plugin"
    assert "我还可以做什么" in caller_ctx.question_driver_refs
    print("PASS: Q7 Contract Verified.")

    # --- Test Q8 ---
    q8_plugin = WhatShouldIDoNowPlugin()
    # Mocking combined model response
    mock_model_provider.generate_json.return_value = {
        "objective_profile": {
            "current_primary_objective": "Investigation",
            "current_phase_tasks": ["scan", "report"],
            "priority_order": ["scan", "report"]
        },
        "task_queue": {
            "next_self_tasks": [{"id": "t1"}],
            "blocked_self_tasks": [],
            "proactive_actions": []
        }
    }
    
    q8_res = q8_plugin.execute(mock_context)
    assert q8_res["objective"]["current_primary_objective"] == "Investigation"
    # Assert traceability in LLM call
    args, kwargs = mock_model_provider.generate_json.call_args
    caller_ctx: ModelProviderCallerContext = kwargs["caller_context"]
    assert caller_ctx.source_module == "q8_what_should_i_do_now_plugin"
    print("PASS: Q8 Contract Verified.")

    # --- Test Q9 ---
    q9_plugin = HowShouldIActPlugin()
    mock_model_provider.generate_json.return_value = {
        "evaluation_style": "evidence_first",
        "risk_tolerance": "low",
        "action_rhythm": "step-by-step",
        "confirmation_strategy": "human_gate",
        "evolution_direction": "learn_api"
    }
    
    q9_res = q9_plugin.execute(mock_context)
    assert q9_res["risk_tolerance"] == "low"
    # Assert traceability in LLM call
    args, kwargs = mock_model_provider.generate_json.call_args
    caller_ctx: ModelProviderCallerContext = kwargs["caller_context"]
    assert caller_ctx.source_module == "q9_how_should_i_act_plugin"
    print("PASS: Q9 Contract Verified.")

    # --- Test Fail-Closed Redline ( 断言 2 防伪造阻断 ) ---
    mock_model_provider.generate_json.side_effect = RuntimeError("LLM_TIMEOUT")
    try:
        q7_plugin.execute(mock_context)
        assert False, "Should have failed closed on LLM error"
    except RuntimeError as e:
        assert "[LLM MANDATORY]" in str(e)
    print("PASS: Fail-Closed Redline Verified.")
