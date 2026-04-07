from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.self_model import (  # noqa: E402
    CognitiveStateProfile,
    ConfidenceDriftIndicator,
    LivingSelfModel,
    LivingSelfModelEngine,
)
from zentex.runtime.working_memory import (  # noqa: E402
    AttentionItem,
    FocusBudget,
    WorkingMemoryController,
    WorkingMemoryFrame,
)


def test_focus_budget_enforcement() -> None:
    controller = WorkingMemoryController(
        FocusBudget(
            max_active_focus=2,
            max_suspended_focus=4,
            overflow_policy="drop_oldest",
        )
    )

    frame_1 = controller.upsert_focus(
        AttentionItem(
            focus_id="goal-1",
            focus_type="goal",
            title="Primary goal",
            priority=2,
            urgency=2,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )
    frame_2 = controller.upsert_focus(
        AttentionItem(
            focus_id="goal-2",
            focus_type="question",
            title="Open question",
            priority=1,
            urgency=1,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )
    frame_3 = controller.upsert_focus(
        AttentionItem(
            focus_id="goal-3",
            focus_type="goal",
            title="Overflow goal",
            priority=1,
            urgency=0,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )

    assert isinstance(frame_1, WorkingMemoryFrame)
    assert isinstance(frame_2, WorkingMemoryFrame)
    assert isinstance(frame_3, WorkingMemoryFrame)
    assert len(frame_3.active_focus_ids) == 2
    assert len(controller.list_active_items()) == 2
    assert set(frame_3.active_focus_ids) == {"goal-1", "goal-2"}
    assert "goal-3" in frame_3.suspended_focus_ids


def test_high_risk_interruption_and_resume_hint() -> None:
    controller = WorkingMemoryController(
        FocusBudget(
            max_active_focus=2,
            max_suspended_focus=4,
            overflow_policy="drop_oldest",
        )
    )
    controller.upsert_focus(
        AttentionItem(
            focus_id="task-low",
            focus_type="goal",
            title="Low priority task",
            priority=1,
            urgency=0,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )
    controller.upsert_focus(
        AttentionItem(
            focus_id="task-mid",
            focus_type="question",
            title="Medium question",
            priority=2,
            urgency=1,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )

    frame = controller.upsert_focus(
        AttentionItem(
            focus_id="risk-high",
            focus_type="risk",
            title="Critical risk",
            priority=5,
            urgency=5,
            blocked=True,
            interruptible=False,
            resume_hint=None,
        )
    )

    suspended_items = {item.focus_id: item for item in controller.list_suspended_items()}
    assert "risk-high" in frame.active_focus_ids
    assert "task-low" in frame.suspended_focus_ids
    assert suspended_items["task-low"].resume_hint == "Resume after handling Critical risk"
    assert len(frame.active_focus_ids) == 2


def test_continuous_failure_triggers_conservative_posture() -> None:
    engine = LivingSelfModelEngine()

    model, drift_indicator, recommendations = engine.update_self_model(
        current_state=CognitiveStateProfile(
            load_level="medium",
            stability_level="stable",
            exploration_mode="enabled",
            reasoning_posture="aggressive",
            evidence_posture="normal",
        ),
        recent_strengths=["fast synthesis"],
        current_cognitive_load="medium",
        failure_signals={"consecutive_failures": 3},
    )

    assert isinstance(model, LivingSelfModel)
    assert drift_indicator is None
    assert model.current_state.reasoning_posture == "conservative"
    assert model.current_state.evidence_posture == "strict"
    assert model.current_state.stability_level == "unstable"
    assert recommendations["risk_tolerance"] == "lower"
    assert any(item.pattern_type == "continuous_failures" for item in model.recent_weaknesses)


def test_confidence_drift_indicator_generation() -> None:
    engine = LivingSelfModelEngine()

    model, drift_indicator, recommendations = engine.update_self_model(
        current_state={
            "load_level": "medium",
            "stability_level": "stable",
            "exploration_mode": "limited",
            "reasoning_posture": "balanced",
            "evidence_posture": "normal",
        },
        confidence_signals={
            "statement_confidence": 0.92,
            "evidence_support": 0.18,
        },
    )

    assert isinstance(model, LivingSelfModel)
    assert isinstance(drift_indicator, ConfidenceDriftIndicator)
    assert drift_indicator.statement_confidence == 0.92
    assert drift_indicator.evidence_support == 0.18
    assert drift_indicator.drift_score == 0.74
    assert model.current_state.reasoning_posture == "conservative"
    assert model.current_state.evidence_posture == "strict"
    assert recommendations["expression_posture"] == "more_conservative"
    assert any(item.pattern_type == "overconfidence" for item in model.recent_weaknesses)


def test_strict_no_execution_boundary() -> None:
    external_router = Mock(name="external_router")
    host_command_sender = Mock(name="host_command_sender")

    memory_controller = WorkingMemoryController(
        FocusBudget(
            max_active_focus=1,
            max_suspended_focus=2,
            overflow_policy="drop_oldest",
        )
    )
    memory_controller.upsert_focus(
        AttentionItem(
            focus_id="focus-1",
            focus_type="goal",
            title="Keep internal focus",
            priority=1,
            urgency=1,
            blocked=False,
            interruptible=True,
            resume_hint=None,
        )
    )
    memory_controller.upsert_focus(
        AttentionItem(
            focus_id="focus-2",
            focus_type="risk",
            title="Internal risk only",
            priority=5,
            urgency=5,
            blocked=True,
            interruptible=False,
            resume_hint=None,
        )
    )

    self_model_engine = LivingSelfModelEngine()
    model, drift_indicator, recommendations = self_model_engine.update_self_model(
        current_state=CognitiveStateProfile(
            load_level="high",
            stability_level="stable",
            exploration_mode="enabled",
            reasoning_posture="aggressive",
            evidence_posture="normal",
        ),
        failure_signals={"consecutive_failures": 2},
        confidence_signals={
            "statement_confidence": 0.85,
            "evidence_support": 0.25,
        },
        current_cognitive_load="high",
    )

    assert model.current_state.reasoning_posture == "conservative"
    assert drift_indicator is not None
    assert recommendations["attention_budget_cap"]["suggested_max_active_focus"] == 2
    external_router.assert_not_called()
    host_command_sender.assert_not_called()
