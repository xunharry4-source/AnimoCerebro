from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.metacognition import (  # noqa: E402
    EscalationDecision,
    MetaCognitionController,
    ReasoningModeDecision,
    ToolInvocationPlan,
)


def _mock_registry() -> Mock:
    registry = Mock()
    conflict_tool = Mock()
    conflict_tool.spec.tool_id = "conflict_checker"
    conflict_tool.spec.purpose = "Conflict checker for unresolved assumptions"
    review_tool = Mock()
    review_tool.spec.tool_id = "review_auditor"
    review_tool.spec.purpose = "Review confidence drift and audit assumptions"
    planner_tool = Mock()
    planner_tool.spec.tool_id = "agenda_planner"
    planner_tool.spec.purpose = "Plan overdue agenda items"
    registry.list.return_value = [conflict_tool, review_tool, planner_tool]
    return registry


def _flatten_payload(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _flatten_payload(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _flatten_payload(item)
        return
    yield str(value)


def test_high_load_prevents_deep_reasoning() -> None:
    controller = MetaCognitionController()
    living_self_model = {
        "degraded_flags": ["budget_pressure", "cognitive_overload"],
    }
    budget = {
        "remaining": 0.1,
    }

    reasoning_mode, tool_plan, escalation = controller.generate_decisions(
        working_memory={"evidence": ["evt-1", "evt-2"]},
        living_self_model=living_self_model,
        budget=budget,
        agenda={},
        tool_registry=_mock_registry(),
    )

    assert isinstance(reasoning_mode, ReasoningModeDecision)
    assert isinstance(tool_plan, ToolInvocationPlan)
    assert isinstance(escalation, EscalationDecision)
    assert reasoning_mode.reasoning_depth != "deep"
    assert reasoning_mode.reasoning_depth == "shallow"
    assert reasoning_mode.selection_reason != ""


def test_low_evidence_triggers_clarification() -> None:
    controller = MetaCognitionController()

    reasoning_mode, _, escalation = controller.generate_decisions(
        working_memory={
            "high_risk": True,
            "evidence": [],
        },
        living_self_model={"degraded_flags": []},
        budget={"remaining": 0.9},
        agenda={"critical_items": ["unsafe_change"]},
        tool_registry=_mock_registry(),
    )

    assert reasoning_mode.interaction_posture == "clarify"
    assert escalation.decision_type in {"clarify", "revisit", "defer"}
    assert escalation.decision_type == "clarify"
    assert escalation.reason != ""


def test_continuous_failures_trigger_revisit() -> None:
    controller = MetaCognitionController()

    reasoning_mode, _, escalation = controller.generate_decisions(
        working_memory={
            "evidence": ["evt-1"],
        },
        living_self_model={
            "consecutive_failures": 3,
            "degraded_flags": [],
        },
        budget={"remaining": 0.8},
        agenda={},
        tool_registry=_mock_registry(),
    )

    assert escalation.decision_type == "revisit"
    assert escalation.reason != ""
    assert reasoning_mode.selection_reason != ""
    assert reasoning_mode.interaction_posture == "review"


def test_strict_no_execution_boundary() -> None:
    controller = MetaCognitionController()

    reasoning_mode, tool_plan, escalation = controller.generate_decisions(
        working_memory={
            "unresolved_assumptions": True,
            "evidence": ["evt-1"],
            "weakness_flags": ["confidence_drift"],
        },
        living_self_model={
            "degraded_flags": ["confidence_drift"],
        },
        budget={"remaining": 0.7},
        agenda={"overdue_items": ["inspect backlog"]},
        tool_registry=_mock_registry(),
    )

    forbidden_markers = {
        "external_action",
        "write_file",
        "network_call",
        "execute_shell",
        "send_message",
        "http_request",
    }
    combined_payload = {
        "reasoning_mode": asdict(reasoning_mode),
        "tool_plan": asdict(tool_plan),
        "escalation": asdict(escalation),
    }
    flattened = set(_flatten_payload(combined_payload))

    assert isinstance(reasoning_mode, ReasoningModeDecision)
    assert isinstance(tool_plan, ToolInvocationPlan)
    assert isinstance(escalation, EscalationDecision)
    assert forbidden_markers.isdisjoint(flattened)
    assert all(tool_id in {"conflict_checker", "review_auditor", "agenda_planner"} for tool_id in tool_plan.selected_tools)
