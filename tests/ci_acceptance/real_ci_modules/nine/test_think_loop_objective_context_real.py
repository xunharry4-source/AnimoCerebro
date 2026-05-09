from __future__ import annotations

import pytest

from zentex.foundation.contracts import TurnRequest
from zentex.kernel.flow_domain.objective_context import build_think_loop_objective_context
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.kernel.state_domain import CognitiveTemporalEngine, SelfModelEngine, WorkingMemoryController
from zentex.nine_questions.objective_engine import ObjectiveProfileMissingError


def _q8_snapshot(suffix: str) -> dict:
    objective = {
        "current_mission": f"consume objective profile in think loop {suffix}",
        "primary_objectives": ["phase 2 and phase 8 must receive objective profile"],
        "secondary_objectives": ["preserve q8 q9 trace"],
        "completion_conditions": ["frame and synthesis consume the same profile"],
        "pause_conditions": ["profile missing"],
        "escalation_conditions": ["profile malformed"],
        "current_phase_tasks": [f"think-loop-objective-{suffix}"],
        "priority_order": [f"think-loop-objective-{suffix}"],
    }
    return {
        "trace_id": f"trace-q8-think-loop-{suffix}",
        "summary": "Q8 ThinkLoop objective context",
        "context_updates": {"q8_objective_profile": objective},
        "result": {"objective_profile": objective},
    }


def _q9_snapshot(suffix: str) -> dict:
    evaluation = {
        "role_context": "think loop executor",
        "resource_context": "real phase context",
        "risk_level": "medium",
        "evaluation_weights": {
            "accuracy": 0.30,
            "creativity": 0.20,
            "speed": 0.10,
            "continuity": 0.25,
            "risk_control": 0.15,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "objective_context_real",
        "action_rhythm_hint": "phase_2_then_phase_8",
    }
    evolution = {
        "allowed_directions": ["tighten phase context use"],
        "risk_threshold": 0.4,
        "forbidden_directions": ["ignore q9 evaluation profile"],
        "validation_requirements": ["assert phase 2 and phase 8 context"],
    }
    return {
        "trace_id": f"trace-q9-think-loop-{suffix}",
        "summary": "Q9 ThinkLoop evaluation context",
        "context_updates": {
            "q9_evaluation_profile": evaluation,
            "q9_evolution_profile": evolution,
            "q9_action_posture": {
                "evaluation_profile": evaluation,
                "evolution_profile": evolution,
            },
        },
        "result": {
            "evaluation_profile": evaluation,
            "evolution_profile": evolution,
        },
    }


def _snapshot_map(suffix: str) -> dict:
    return {
        "q8": _q8_snapshot(suffix),
        "q9": _q9_snapshot(suffix),
    }


class RecordingKernelBridge:
    def __init__(self) -> None:
        self.frame_context: dict | None = None
        self.decision_context: dict | None = None

    def observe_environment(self, session_id: str, turn_id: str) -> dict:
        return {"observed": True, "observe_session_id": session_id, "observe_turn_id": turn_id}

    def evaluate_drive(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"drive_checked": context["observed"], "drive_turn_id": turn_id}

    def evaluate_cognition(self, session_id: str, turn_id: str, context: dict) -> dict:
        self.frame_context = dict(context)
        objective = context["nine_question_objective_context"]
        return {
            "frame_consumed_objective_context": True,
            "frame_source_trace_ids": objective["source_trace_ids"],
            "frame_dominant_meta_value_lenses": objective["evaluation_profile"]["dominant_meta_value_lenses"],
        }

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        return {"conflicts": []}

    def run_simulation(self, session_id: str, context: dict) -> dict:
        return {"simulation": {"branches": ["keep objective profile active"]}}

    def run_metacognition(self, session_id: str, context: dict) -> dict:
        return {"metacognition": {"objective_context_seen": context["frame_consumed_objective_context"]}}

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        return {"tool_results": []}

    def synthesize_decision(self, session_id: str, context: dict) -> dict:
        self.decision_context = dict(context)
        objective = context["nine_question_objective_context"]
        return {
            "response": f"decision used {objective['evaluation_profile']['dominant_meta_value_lenses'][0]}",
            "decision_consumed_objective_context": True,
            "decision_source_trace_ids": objective["source_trace_ids"],
            "decision_meta_value_lens_weights": objective["evaluation_profile"]["meta_value_lens_weights"],
        }

    def consolidate_memory(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"memory_consolidated": True}


def test_objective_context_builder_returns_exact_meta_lens_mapping_for_frame() -> None:
    suffix = "builder"
    result = build_think_loop_objective_context(
        context={"nine_question_state": {"question_snapshots": _snapshot_map(suffix)}},
        phase_name="frame",
    )

    objective_context = result["nine_question_objective_context"]
    assert objective_context["profile_status"] == "ready"
    assert objective_context["target_phase"] == "frame"
    assert objective_context["source_trace_ids"] == {
        "q8": "trace-q8-think-loop-builder",
        "q9": "trace-q9-think-loop-builder",
    }
    assert objective_context["evaluation_profile"]["evaluation_weights"] == {
        "accuracy": 0.30,
        "creativity": 0.20,
        "speed": 0.10,
        "continuity": 0.25,
        "risk_control": 0.15,
    }
    assert objective_context["evaluation_profile"]["meta_value_lens_weights"] == {
        "system_capability_lens": 0.25,
        "user_efficiency_lens": 0.1,
        "user_value_lens": 0.5,
    }
    assert objective_context["evaluation_profile"]["dominant_meta_value_lenses"] == ["user_value_lens"]


def test_objective_context_builder_fails_closed_for_malformed_q9() -> None:
    suffix = "bad-q9"
    snapshots = {"q8": _q8_snapshot(suffix), "q9": {"trace_id": f"trace-q9-{suffix}", "context_updates": {}}}

    with pytest.raises(ObjectiveProfileMissingError) as exc_info:
        build_think_loop_objective_context(
            context={"nine_question_state": {"question_snapshots": snapshots}},
            phase_name="frame",
        )

    assert "q9.evaluation_profile" in exc_info.value.missing_sources
    assert "q9.evolution_profile" in exc_info.value.missing_sources


def test_think_loop_phase_2_and_phase_8_consume_real_objective_context() -> None:
    suffix = "e2e"
    bridge = RecordingKernelBridge()
    loop = ThinkLoop(bridge=bridge)
    request = TurnRequest(
        turn_id="turn-think-loop-objective",
        session_id="session-think-loop-objective",
        user_input="execute with q8/q9 profile",
        context={"nine_question_state": {"question_snapshots": _snapshot_map(suffix)}},
    )

    results = loop.run(
        request=request,
        working_memory=WorkingMemoryController(max_slots=8),
        self_model=SelfModelEngine(session_id=request.session_id),
        temporal=CognitiveTemporalEngine(session_id=request.session_id),
    )

    by_phase = {result.phase_name: result for result in results}
    assert by_phase["frame"].error == ""
    assert by_phase["frame"].output["frame_consumed_objective_context"] is True
    assert by_phase["frame"].output["frame_source_trace_ids"] == {
        "q8": "trace-q8-think-loop-e2e",
        "q9": "trace-q9-think-loop-e2e",
    }
    assert by_phase["decision_synthesis"].output["decision_consumed_objective_context"] is True
    assert by_phase["decision_synthesis"].output["decision_meta_value_lens_weights"] == {
        "system_capability_lens": 0.25,
        "user_efficiency_lens": 0.1,
        "user_value_lens": 0.5,
    }
    assert by_phase["decision_synthesis"].output["response"] == "decision used user_value_lens"

    assert bridge.frame_context is not None
    assert bridge.decision_context is not None
    assert bridge.frame_context["nine_question_objective_context"]["target_phase"] == "frame"
    assert bridge.decision_context["nine_question_objective_context"]["target_phase"] == "decision_synthesis"
    assert bridge.decision_context["frame_consumed_objective_context"] is True
