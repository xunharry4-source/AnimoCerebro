from __future__ import annotations

from unittest.mock import Mock

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import AlternativeSpec, ObjectiveSpec, PostureSpec
from zentex.runtime.transcript import BrainTranscriptStore
from plugins.nine_questions.q7_what_else_can_i_do import build_q7_what_else_can_i_do_plugin
from plugins.nine_questions.q8_what_should_i_do_now import build_q8_what_should_i_do_now_plugin
from plugins.nine_questions.q9_how_should_i_act import build_q9_how_should_i_act_plugin


class _AltOracle(AlternativeSpec):
    plugin_id: str = "fallback:human_review"
    version: str = "1.0.0"
    feature_code: str = "alternative.fallback"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["mock"]
    revocation_reasons: list[str] = []

    def get_downgrade_options(self, block_context):
        return []


class _ObjectiveOracle(ObjectiveSpec):
    plugin_id: str = "objective:queue_refiner"
    version: str = "1.0.0"
    feature_code: str = "objective.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["mock"]
    revocation_reasons: list[str] = []

    def refine_task_queue(self, task_queue, context):
        return task_queue


class _PostureOracle(PostureSpec):
    plugin_id: str = "posture:evidence_first"
    version: str = "1.0.0"
    feature_code: str = "posture.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["mock"]
    revocation_reasons: list[str] = []

    def apply_posture(self, decision_trace):
        return {}


def test_q7_prompt_is_humanized_and_not_raw_python_objects(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "alternative_strategy_profile": {
                "fallback_plans": ["转为只读排查"],
                "degradation_strategies": ["缩小范围到证据采集"],
                "collaboration_switches": ["请求人工确认写操作"],
                "exploratory_actions": ["检查最近失败 transcript"],
            }
        }
    )
    registry = Mock()
    registry.get_active_plugins.return_value = [_AltOracle()]
    plugin = build_q7_what_else_can_i_do_plugin()

    result = plugin.run_tool(
        {
            "session_id": "s",
            "turn_id": "t",
            "trace_id": "trace:q7",
            "decision_id": "decision:q7",
            "model_provider": provider,
            "transcript_store": BrainTranscriptStore(tmp_path / "q7.jsonl"),
            "plugin_registry": registry,
            "nine_questions": {
                "q4": {"capability_boundary_profile": {"actionable_space": ["read logs"]}},
                "q5": {"authorization_boundary_profile": {"allowed_action_space": ["read logs"]}},
                "q6": {"forbidden_zone_profile": {"absolute_red_lines": ["no unauthorized write"]}},
            },
        }
    )

    assert "q7_alternative_strategy_profile" in result.context_updates
    prompt = provider.generate_json.call_args.kwargs["prompt"]
    assert "Q1-Q8 认知快照" in prompt
    assert "可用备选策略插件" in prompt
    assert "Fallback Human Review" in prompt
    assert "{'q4':" not in prompt


def test_q8_prompt_is_humanized_and_not_raw_python_objects(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "objective_profile": {
                "current_primary_objective": "完成运行态证据核对",
                "current_phase_tasks": ["审查当前失败链路"],
                "priority_order": ["先修根因", "再重跑验证"],
            },
            "task_queue": {
                "next_self_tasks": [{"task_id": "inspect", "title": "审查失败链路"}],
                "blocked_self_tasks": [{"task_id": "ui", "reason": "等待新的九问结果"}],
                "proactive_actions": [{"task_id": "capture", "title": "抓取新一轮日志"}],
            },
        }
    )
    registry = Mock()
    registry.get_active_plugins.return_value = [_ObjectiveOracle()]
    plugin = build_q8_what_should_i_do_now_plugin()

    result = plugin.run_tool(
        {
            "session_id": "s",
            "turn_id": "t",
            "trace_id": "trace:q8",
            "decision_id": "decision:q8",
            "model_provider": provider,
            "transcript_store": BrainTranscriptStore(tmp_path / "q8.jsonl"),
            "plugin_registry": registry,
            "nine_questions": {
                "q4": {"capability_boundary_profile": {"actionable_space": ["read logs"]}},
                "q5": {"authorization_boundary_profile": {"allowed_action_space": ["read logs"]}},
                "q6": {"forbidden_zone_profile": {"absolute_red_lines": ["no unauthorized write"]}},
                "q7": {"alternative_strategy_profile": {"fallback_plans": ["只读排查"]}},
            },
            "persistent_task_state": [{"task_id": "inspect", "title": "inspect live chain"}],
        }
    )

    assert "q8_objective_profile" in result.context_updates
    prompt = provider.generate_json.call_args.kwargs["prompt"]
    assert "Q1-Q8 认知快照" in prompt
    assert "当前任务状态" in prompt
    assert "可用目标策略插件" in prompt
    assert "Objective Queue Refiner" in prompt
    assert "{'task_id': 'inspect'" not in prompt


def test_q9_prompt_is_humanized_and_not_raw_python_objects(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "evaluation_style": "evidence_first",
            "risk_tolerance": "low",
            "action_rhythm": "small verified steps",
            "confirmation_strategy": "require confirmation before side effects",
            "evolution_direction": "improve runtime evidence quality",
        }
    )
    registry = Mock()
    registry.get_active_plugins.return_value = [_PostureOracle()]
    plugin = build_q9_how_should_i_act_plugin()

    result = plugin.run_tool(
        {
            "session_id": "s",
            "turn_id": "t",
            "trace_id": "trace:q9",
            "decision_id": "decision:q9",
            "model_provider": provider,
            "transcript_store": BrainTranscriptStore(tmp_path / "q9.jsonl"),
            "plugin_registry": registry,
            "nine_question_state": {
                "q1": {"scene_model": {"primary_domain": "audit"}},
                "q8": {"objective_profile": {"current_primary_objective": "verify runtime"}},
            },
        }
    )

    assert result.context_updates["q9_action_posture_profile"]["evaluation_style"] == "evidence_first"
    prompt = provider.generate_json.call_args.kwargs["prompt"]
    assert "Q1-Q8 认知快照" in prompt
    assert "可用姿态策略插件" in prompt
    assert "Posture Evidence First" in prompt
    assert "{'q1':" not in prompt
