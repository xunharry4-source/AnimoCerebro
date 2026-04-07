from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.session import BrainSessionSnapshot  # noqa: E402
from zentex.runtime.think_loop import BrainTurnResult, ThinkLoop  # noqa: E402
from plugins.provider_tools import ModelProviderError, ToolInvocationResponse  # noqa: E402


def _build_mock_session() -> mock.Mock:
    session = mock.Mock()
    session.session_id = "session-think-loop"
    session.turn_counter = 2
    session.current_workspace = {"cwd": "/workspace/zentex"}
    session.active_goal_frame = {
        "goals": [{"title": "Protect continuity"}],
    }
    session.last_working_memory = {
        "current_focus_summary": "Stabilize runtime replay",
    }
    session.last_temporal_agenda = {
        "overdue_items": ["refresh working state"],
    }
    session.last_metacognition = {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": ["cache_cold"],
    }
    session.get_snapshot.return_value = BrainSessionSnapshot(
        session_id="session-think-loop",
        turn_count=2,
        active_goal_titles=["Protect continuity"],
        current_focus_summary="Stabilize runtime replay",
        overdue_items=["refresh working state"],
        current_reasoning_mode="deliberate",
        degraded_flags=["cache_cold"],
        last_turn_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
    )
    return session


def test_think_loop_stateless_execution() -> None:
    mock_session = _build_mock_session()
    llm_tool = mock.Mock()
    llm_tool.config.default_model = "gemini-3-flash(auto)"
    llm_tool.call.side_effect = [
        ToolInvocationResponse(
            provider="openai_compat",
            model="gemini-3-flash(auto)",
            output_text="frame-summary",
            raw_response={"id": "frame"},
        ),
        ToolInvocationResponse(
            provider="openai_compat",
            model="gemini-3-flash(auto)",
            output_text="decision-summary",
            raw_response={"id": "decision"},
        ),
    ]
    think_loop = ThinkLoop(llm_tool=llm_tool)

    assert vars(think_loop) == {"llm_tool": llm_tool, "llm_tool_name": "openai_compat"}

    result = think_loop.run(mock_session)

    assert isinstance(result, BrainTurnResult)
    assert result.session_id == mock_session.session_id
    assert isinstance(result.started_at, datetime)
    assert isinstance(result.finished_at, datetime)
    assert result.started_at <= result.finished_at
    assert result.turn_id.startswith(f"{mock_session.session_id}-turn-")

    # Statelessness: the loop should not retain per-run state on the instance.
    assert vars(think_loop) == {"llm_tool": llm_tool, "llm_tool_name": "openai_compat"}


def test_think_loop_9_phases_orchestration() -> None:
    mock_session = _build_mock_session()
    think_loop = ThinkLoop()
    call_order: list[str] = []

    observed = {
        "turn_id": "turn-test",
        "started_at": datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc),
        "workspace": mock_session.current_workspace,
        "session_snapshot": mock_session.get_snapshot.return_value,
        "external_inputs": [],
        "host_status": {"status": "ok"},
    }
    framed = {
        "observed": observed,
        "context_snapshot": {"frame": "ok"},
    }
    working_state = {
        "working_memory": {"focus": "x"},
        "temporal_agenda": {"overdue_items": []},
        "living_self_model": {"current_reasoning_mode": "baseline", "degraded_flags": []},
    }
    risks = {
        "conflict_snapshot": {"conflicts": []},
    }
    simulation = {
        "counterfactual_simulation": {"branches": []},
        "interaction_mind": {"stakeholders": []},
    }
    metacognition = {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": [],
        "tool_plan": [],
        "escalation_required": False,
    }
    tool_invocations = [{"tool_name": "mock_tool", "status": "skipped"}]
    decision_summary = {"status": "pause"}
    consolidation = {
        "reflection_record": {"summary": "done"},
        "consolidation": {"ready_for_transcript": True},
    }

    def record(name: str, payload):
        def _side_effect(*args, **kwargs):
            call_order.append(name)
            return payload
        return _side_effect

    with (
        mock.patch.object(think_loop, "_phase_1_observe", side_effect=record("phase_1", observed)) as phase_1,
        mock.patch.object(think_loop, "_phase_2_frame", side_effect=record("phase_2", framed)) as phase_2,
        mock.patch.object(think_loop, "_phase_3_update_working_state", side_effect=record("phase_3", working_state)) as phase_3,
        mock.patch.object(think_loop, "_phase_4_detect_cognitive_risks", side_effect=record("phase_4", risks)) as phase_4,
        mock.patch.object(think_loop, "_phase_5_simulate", side_effect=record("phase_5", simulation)) as phase_5,
        mock.patch.object(think_loop, "_phase_6_metacognition", side_effect=record("phase_6", metacognition)) as phase_6,
        mock.patch.object(think_loop, "_phase_7_orchestrate_cognitive_tools", side_effect=record("phase_7", tool_invocations)) as phase_7,
        mock.patch.object(think_loop, "_phase_8_synthesize_decision", side_effect=record("phase_8", decision_summary)) as phase_8,
        mock.patch.object(think_loop, "_phase_9_consolidate", side_effect=record("phase_9", consolidation)) as phase_9,
    ):
        think_loop.run(mock_session)

    assert call_order == [
        "phase_1",
        "phase_2",
        "phase_3",
        "phase_4",
        "phase_5",
        "phase_6",
        "phase_7",
        "phase_8",
        "phase_9",
    ]
    phase_1.assert_called_once()
    phase_2.assert_called_once()
    phase_3.assert_called_once()
    phase_4.assert_called_once()
    phase_5.assert_called_once()
    phase_6.assert_called_once()
    phase_7.assert_called_once()
    phase_8.assert_called_once()
    phase_9.assert_called_once()


def test_turn_result_data_assembly() -> None:
    mock_session = _build_mock_session()
    think_loop = ThinkLoop()
    specific_metacognition = {
        "thought_mode": "deep",
        "current_reasoning_mode": "deep",
        "degraded_flags": ["none"],
        "tool_plan": ["compare_risks"],
        "escalation_required": False,
    }
    specific_decision = {
        "action_intent": "pause",
        "status": "needs_confirmation",
        "summary": "Human confirmation required before execution.",
    }

    observed = {
        "turn_id": "turn-assembly",
        "started_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        "workspace": mock_session.current_workspace,
        "session_snapshot": mock_session.get_snapshot.return_value,
        "external_inputs": [],
        "host_status": {"status": "ok"},
    }
    framed = {
        "observed": observed,
        "context_snapshot": {"frame": "assembled"},
    }
    working_state = {
        "working_memory": {"current_focus_summary": "assembly focus"},
        "temporal_agenda": {"overdue_items": []},
        "living_self_model": {"current_reasoning_mode": "baseline", "degraded_flags": []},
    }
    risks = {
        "conflict_snapshot": {"conflicts": ["uncertain identity"]},
    }
    simulation = {
        "counterfactual_simulation": {"branches": ["a", "b"], "selected_branch": "b"},
        "interaction_mind": {"stakeholders": ["host"]},
    }
    tool_invocations = [{"tool_name": "planner", "status": "completed"}]
    consolidation = {
        "reflection_record": {"summary": "reflection kept"},
        "consolidation": {"ready_for_transcript": True},
    }

    with (
        mock.patch.object(think_loop, "_phase_1_observe", return_value=observed),
        mock.patch.object(think_loop, "_phase_2_frame", return_value=framed),
        mock.patch.object(think_loop, "_phase_3_update_working_state", return_value=working_state),
        mock.patch.object(think_loop, "_phase_4_detect_cognitive_risks", return_value=risks),
        mock.patch.object(think_loop, "_phase_5_simulate", return_value=simulation),
        mock.patch.object(think_loop, "_phase_6_metacognition", return_value=specific_metacognition),
        mock.patch.object(think_loop, "_phase_7_orchestrate_cognitive_tools", return_value=tool_invocations),
        mock.patch.object(think_loop, "_phase_8_synthesize_decision", return_value=specific_decision),
        mock.patch.object(think_loop, "_phase_9_consolidate", return_value=consolidation),
    ):
        result = think_loop.run(mock_session)

    assert isinstance(result, BrainTurnResult)
    assert result.metacognition == specific_metacognition
    assert result.decision_summary == specific_decision
    assert result.context_snapshot == {"frame": "assembled"}
    assert result.working_memory == {"current_focus_summary": "assembly focus"}
    assert result.conflict_snapshot == {"conflicts": ["uncertain identity"]}
    assert result.tool_invocations == [{"tool_name": "planner", "status": "completed"}]
    assert result.reflection_record == {"summary": "reflection kept"}


def test_llm_mandatory_phases_use_openai_compat_tool() -> None:
    mock_session = _build_mock_session()
    llm_tool = mock.Mock()
    llm_tool.config.default_model = "gemini-3-flash(auto)"
    llm_tool.call.side_effect = [
        ToolInvocationResponse(
            provider="openai_compat",
            model="gemini-3-flash(auto)",
            output_text="frame-summary",
            raw_response={"id": "frame"},
        ),
        ToolInvocationResponse(
            provider="openai_compat",
            model="gemini-3-flash(auto)",
            output_text="decision-summary",
            raw_response={"id": "decision"},
        ),
    ]
    think_loop = ThinkLoop(llm_tool=llm_tool)

    result = think_loop.run(mock_session)

    assert llm_tool.call.call_count == 2
    first_call = llm_tool.call.call_args_list[0]
    second_call = llm_tool.call.call_args_list[1]
    assert "nine-question framing summary" in first_call.args[0].prompt
    assert "decision summary" in second_call.args[0].prompt
    assert result.context_snapshot["nine_question_frame"]["frame_summary"] == "frame-summary"
    assert result.context_snapshot["nine_question_frame"]["provider"] == "openai_compat"
    assert result.decision_summary["summary"] == "decision-summary"
    assert result.decision_summary["provider"] == "openai_compat"
    assert first_call.args[0].model == "gemini-3-flash(auto)"
    assert second_call.args[0].model == "gemini-3-flash(auto)"


def test_llm_failure_in_mandatory_phase_surfaces_without_rule_fallback() -> None:
    mock_session = _build_mock_session()
    llm_tool = mock.Mock()
    llm_tool.config.default_model = "gemini-3-flash(auto)"
    llm_tool.call.side_effect = ModelProviderError("gateway unavailable")
    think_loop = ThinkLoop(llm_tool=llm_tool)

    with mock.patch.object(think_loop, "_phase_3_update_working_state") as phase_3:
        with mock.patch.object(think_loop, "_phase_8_synthesize_decision") as phase_8:
            with pytest.raises(ModelProviderError) as exc_info:
                think_loop.run(mock_session)

    assert "gateway unavailable" in str(exc_info.value)
    phase_3.assert_not_called()
    phase_8.assert_not_called()
