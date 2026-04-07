from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.plugin_base import PluginLifecycleStatus  # noqa: E402
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402
from zentex.runtime.nine_questions.router import build_event  # noqa: E402

from plugins.nine_questions.q2_who_am_i.q2_who_am_i_plugin import (  # noqa: E402
    build_q2_who_am_i_plugin,
)
from plugins.nine_questions.q3_what_do_i_have.q3_what_do_i_have_plugin import (  # noqa: E402
    build_q3_what_do_i_have_plugin,
)
from plugins.nine_questions.q4_what_can_i_do.q4_what_can_i_do_plugin import (  # noqa: E402
    build_q4_what_can_i_do_plugin,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.q5_what_am_i_allowed_to_do_plugin import (  # noqa: E402
    build_q5_what_am_i_allowed_to_do_plugin,
)


@dataclass
class ManagedRecord:
    plugin: object
    feature_key: str


class FakeModelProvider:
    def __init__(self, calls: list[str]) -> None:
        self.plugin_id = "model-provider-fake"
        self.version = "9.9.9"
        self.status = PluginLifecycleStatus.ACTIVE
        self._calls = calls

    def plugin_kind(self) -> str:
        return "model_provider"

    def generate_json(self, **kwargs):  # type: ignore[no-untyped-def]
        caller_context = kwargs.get("caller_context")
        invocation_phase = getattr(caller_context, "invocation_phase", "unknown")
        self._calls.append(str(invocation_phase))

        if invocation_phase == "nine_question_q2_who_am_i":
            return {
                "role_profile": {
                    "identity_role": "operator",
                    "active_role": "operator",
                    "task_role": "operator",
                },
                "mission_boundary": {
                    "current_mission": "keep system stable",
                    "priority_duties": [],
                    "continuity_boundaries": ["no external execution"],
                },
            }
        if invocation_phase == "nine_question_q3_what_do_i_have":
            return {
                "unified_asset_inventory": {
                    "available_cognitive_tools": [],
                    "available_execution_tools": [],
                    "connected_agents": [],
                    "activated_strategy_patches": [],
                    "accessible_workspace_zones": [],
                },
                "resource_evaluation": {
                    "resource_status": "sufficient",
                    "missing_critical_assets": [],
                    "bottleneck_node": "none",
                },
            }
        if invocation_phase == "nine_question_q4_what_can_i_do":
            return {
                "capability_boundary_profile": {
                    "capability_upper_limits": [],
                    "actionable_space": [],
                    "executable_strategies": [],
                }
            }
        if invocation_phase == "nine_question_q5_authorization":
            return {
                "authorization_boundary_profile": {
                    "allowed_action_space": [],
                    "forbidden_action_space": [],
                    "contact_and_org_boundaries": {},
                    "requires_escalation_actions": [],
                }
            }
        raise AssertionError(f"Unexpected invocation_phase: {invocation_phase}")


def _build_runtime_with_q2_to_q5(*, calls: list[str]) -> BrainRuntime:
    transcript_path = PROJECT_ROOT / "tmp_test_nine_question_router_transcript.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()

    runtime = BrainRuntime(transcript_store=BrainTranscriptStore(transcript_path))
    provider = FakeModelProvider(calls)
    runtime.managed_plugin_records = {
        "model-provider-fake": ManagedRecord(
            plugin=provider,
            feature_key="model_provider:fake",
        )
    }

    registry = CognitiveToolRegistry(audit_logger=mock.Mock())
    for plugin in (
        build_q2_who_am_i_plugin(),
        build_q3_what_do_i_have_plugin(),
        build_q4_what_can_i_do_plugin(),
        build_q5_what_am_i_allowed_to_do_plugin(),
    ):
        reg = registry.register(plugin, source_kind="builtin", description=plugin.purpose)
        assert reg is not None
        registry.promote_plugin(plugin.plugin_id, PluginLifecycleStatus.SANDBOX_VERIFIED, audit_reason="test")
        registry.promote_plugin(plugin.plugin_id, PluginLifecycleStatus.ACTIVE, audit_reason="test")
    runtime.cognitive_tool_registry = registry
    return runtime


def test_new_agent_event_only_triggers_q3_to_q5() -> None:
    calls: list[str] = []
    runtime = _build_runtime_with_q2_to_q5(calls=calls)
    session = runtime.create_session("session-router")
    session.last_context_snapshot = {
        "active_tools": {
            "available_cognitive_tools": [],
            "available_execution_tools": [],
        },
        "connected_agents": [],
        "loaded_memories": {"activated_strategy_patches": []},
        "permissions": {"accessible_workspace_zones": []},
    }

    state = session.current_nine_question_state
    runtime.nine_question_router.publish(
        state,
        build_event(
            event_type="agent_connected",
            reason="new_agent_connected",
            trace_id="event:new-agent",
            dirty_questions=["q3", "q4", "q5"],
            payload={"agent_id": "agent-1"},
        ),
    )
    runtime.process_nine_question_events(session=session, turn_id="event:new-agent")

    assert "nine_question_q3_what_do_i_have" in calls
    assert "nine_question_q4_what_can_i_do" in calls
    assert "nine_question_q5_authorization" in calls
    assert "nine_question_q2_who_am_i" not in calls


def test_manual_role_change_marks_q2_dirty_and_recomputes_only_q2() -> None:
    calls: list[str] = []
    runtime = _build_runtime_with_q2_to_q5(calls=calls)
    session = runtime.create_session("session-intervention")
    session.last_context_snapshot = {
        "identity_kernel_snapshot": {"non_bypassable_constraints": ["no external execution"]},
        "q1_uncertainty_profile": {"uncertainty_intensity": 0.5},
    }

    # Initial compute of Q2.
    state = session.current_nine_question_state
    runtime.nine_question_router.publish(
        state,
        build_event(
            event_type="cold_start",
            reason="initial_q2",
            trace_id="bootstrap:q2",
            dirty_questions=["q2"],
            payload={},
        ),
    )
    runtime.process_nine_question_events(session=session, turn_id="bootstrap:q2")
    assert calls.count("nine_question_q2_who_am_i") == 1

    # Manual role change should enqueue dirty flags; processing should recompute Q2 (not Q3-Q5).
    runtime.request_intervention(
        action="role_change",
        operator_id="op-1",
        reason="change role",
        idempotency_key="k-1",
        trace_id="intervention:k-1",
        phase_name="phase_2_frame",
        manual_context_patch={"role_hint": "operator"},
    )
    runtime.process_nine_question_events(session=session, turn_id="intervention:k-1")

    assert calls.count("nine_question_q2_who_am_i") == 2
    assert "nine_question_q3_what_do_i_have" not in calls
    assert "nine_question_q4_what_can_i_do" not in calls
    assert "nine_question_q5_authorization" not in calls

