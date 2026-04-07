from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.common.plugin_registry import PluginNotBoundError  # noqa: E402
from zentex.core.model_provider_spec import ModelProviderRemoteError  # noqa: E402
from zentex.core.models import CognitiveToolSpec  # noqa: E402
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus  # noqa: E402
from zentex.core.plugin_family import (  # noqa: E402
    AlternativeSpec,
    IdentityPackageSpec,
    ObjectiveSpec,
    PostureSpec,
    RedlinePluginSpec,
    SensoryPluginSpec,
    SubjectiveWeightSpec,
)
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry  # noqa: E402
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.models import BrainTurnResult  # noqa: E402
from zentex.runtime.session import BrainSessionSnapshot  # noqa: E402
from zentex.runtime.think_loop import ManualInterventionRequiredError, ThinkLoop  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore  # noqa: E402
from plugins.nine_questions import (  # noqa: E402
    build_q1_where_am_i_plugin,
    build_q2_who_am_i_plugin,
    build_q3_what_do_i_have_plugin,
    build_q4_what_can_i_do_plugin,
    build_q5_what_am_i_allowed_to_do_plugin,
    build_q6_what_should_i_not_do_plugin,
    build_q7_what_else_can_i_do_plugin,
    build_q8_what_should_i_do_now_plugin,
    build_q9_how_should_i_act_plugin,
)


@dataclass
class ManagedRecord:
    plugin: object
    feature_key: str

    @property
    def feature_code(self) -> str:
        return self.feature_key


@dataclass
class FakeToolRegistration:
    plugin_id: str
    spec: object
    status: PluginLifecycleStatus


class FakeNineQuestionRegistry:
    def __init__(self, plugins: list[object]) -> None:
        self._registrations = [
            FakeToolRegistration(
                plugin_id=str(getattr(plugin, "plugin_id")),
                spec=plugin,
                status=PluginLifecycleStatus.ACTIVE,
            )
            for plugin in plugins
        ]

    def list_registrations(self) -> list[FakeToolRegistration]:
        return list(self._registrations)


class FakePlugin:
    def __init__(
        self,
        *,
        plugin_id: str,
        kind: str,
        status: PluginLifecycleStatus,
        version: str = "1.0.0",
        **attrs: object,
    ) -> None:
        self.plugin_id = plugin_id
        self.version = version
        self.status = status
        self._kind = kind
        for key, value in attrs.items():
            setattr(self, key, value)

    def plugin_kind(self) -> str:
        return self._kind


class FakeCognitiveToolPlugin(CognitiveToolSpec):
    def run_tool(self, context: dict[str, object]) -> dict[str, object]:
        return {
            "tool_id": self.plugin_id,
            "summary": "risk compared",
            "ranked_options": [{"option_id": "a", "risk_score": 10}],
            "context_updates": {"risk_ranking": [{"option_id": "a", "risk_score": 10}]},
            "confidence": 0.8,
        }


class FakeIdentityPack(IdentityPackageSpec):
    pack_type: str
    payload: dict[str, object]

    def get_payload(self) -> dict[str, object]:
        return dict(self.payload)


class FakeWeightPlugin(SubjectiveWeightSpec):
    target_metric: str = "risk"

    def calculate_weight(self, task_context: dict[str, object]) -> float:
        return 0.4


class FakeRedlinePlugin(RedlinePluginSpec):
    rule_domain: str = "safety"

    def get_forbidden_zones(self) -> list[str]:
        return ["no hidden writes"]


class FakeAlternativePlugin(AlternativeSpec):
    strategy_class: str = "fallback"

    def get_downgrade_options(self, block_context: dict[str, object]) -> list[object]:
        return ["read-only fallback"]


class FakeObjectivePlugin(ObjectiveSpec):
    def refine_task_queue(self, task_queue: list[object], context: dict[str, object]) -> list[object]:
        return list(task_queue)


class FakePosturePlugin(PostureSpec):
    def apply_posture(self, decision_trace: dict[str, object]) -> dict[str, object]:
        return {"confirmation_strategy": "confirm_on_write"}


class FakeWorkspaceSensoryPlugin(SensoryPluginSpec):
    signal_type: str = "workspace_snapshot"

    def ingest(self, source: object) -> object:
        return source

    def sanitize(self, raw_signal: object) -> object:
        return raw_signal

    def interpret(self, clean_signal: object) -> dict[str, object]:
        snapshot = clean_signal if isinstance(clean_signal, dict) else {}
        return {
            "structure": snapshot.get("workspace_structure_analysis", {}),
            "samples": snapshot.get("workspace_content_samples", {}) or {},
            "environment_event": snapshot.get("environment_event", {}),
            "physical_host_state": snapshot.get("physical_host_state", {}),
            "interpretation_markers": ["test-sensory"],
            "risk_markers": [],
        }


class FakeGeneralPluginRegistry:
    def __init__(self) -> None:
        self._plugins = [
            FakeIdentityPack(
                plugin_id="identity-role-pack",
                version="1.0.0",
                feature_code="identity.role",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
                pack_type="role_pack",
                payload={"identity_role": "operator", "active_role": "operator", "task_role": "operator"},
            ),
            FakeIdentityPack(
                plugin_id="identity-constraint-pack",
                version="1.0.0",
                feature_code="identity.constraint",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
                pack_type="constraint_pack",
                payload={"non_bypassable_constraints": ["no hidden writes"]},
            ),
            FakeWeightPlugin(
                plugin_id="weight-risk",
                version="1.0.0",
                feature_code="weights.risk",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
            FakeWorkspaceSensoryPlugin(
                plugin_id="workspace-sensory",
                version="1.0.0",
                feature_code="sensory.workspace",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
            FakeRedlinePlugin(
                plugin_id="redline-core",
                version="1.0.0",
                feature_code="redline.core",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
            FakeAlternativePlugin(
                plugin_id="alternative-core",
                version="1.0.0",
                feature_code="alternative.core",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
            FakeObjectivePlugin(
                plugin_id="objective-core",
                version="1.0.0",
                feature_code="objective.core",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
            FakePosturePlugin(
                plugin_id="posture-core",
                version="1.0.0",
                feature_code="posture.core",
                is_concurrency_safe=True,
                status=PluginLifecycleStatus.ACTIVE,
                health_status=PluginHealthStatus.HEALTHY,
                rollback_conditions=["test rollback"],
                revocation_reasons=[],
            ),
        ]

    def get_active_plugins(self) -> list[object]:
        return list(self._plugins)

    def get_bound_plugin(self, plugin_type: type[object]) -> object:
        for plugin in self._plugins:
            if isinstance(plugin, plugin_type):
                return plugin
        raise RuntimeError(f"missing plugin binding: {plugin_type}")


def _build_runtime(
    *,
    model_provider_status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
    simulation_status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
    candidate_cognitive_only: bool = False,
) -> mock.Mock:
    transcript_path = PROJECT_ROOT / "tmp_test_think_loop_transcript.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()

    ingest_plugin = FakePlugin(
        plugin_id="sensory-ingest-webhook",
        kind="signal_ingest",
        status=PluginLifecycleStatus.ACTIVE,
        ingest_signal=mock.Mock(return_value="system telemetry"),
    )
    sanitize_plugin = FakePlugin(
        plugin_id="sensory-sanitize-basic",
        kind="signal_sanitize",
        status=PluginLifecycleStatus.ACTIVE,
        sanitize_signal=mock.Mock(
            return_value=mock.Mock(
                sanitized_text="system telemetry",
                raw_fingerprint="fingerprint",
                injection_risk=False,
                redaction_evidence=[],
            )
        ),
    )
    interpret_plugin = FakePlugin(
        plugin_id="sensory-interpret-generic",
        kind="signal_interpret",
        status=PluginLifecycleStatus.ACTIVE,
        interpret_signal=mock.Mock(
            return_value=mock.Mock(
                model_dump=mock.Mock(
                    return_value={
                        "event_type": "environment.observed",
                        "summary": "Observed external signal",
                    }
                )
            )
        ),
    )
    model_provider = FakePlugin(
        plugin_id="model-provider-gemini",
        kind="model_provider",
        status=model_provider_status,
        generate_json=mock.Mock(
            side_effect=[
                {
                    "role_hypothesis": "operator",
                    "nine_question_frame": {"frame": "ok"},
                    "constraints": [],
                    "immediate_priorities": [],
                },
                {
                    "status": "ready",
                    "summary": "hold",
                    "action_intent": "hold",
                    "blockers": [],
                    "confirmation_required": False,
                },
            ]
        ),
    )
    simulation_plugin = FakePlugin(
        plugin_id="simulation-thought-sandbox",
        kind="simulation_domain",
        status=simulation_status,
        supported_domains=["general"],
        simulate_action=mock.Mock(
            return_value=mock.Mock(
                model_dump=mock.Mock(
                    return_value={
                        "is_safe": True,
                        "predicted_impacts": [],
                        "veto_reason": None,
                        "replan_required": False,
                    }
                )
            )
        ),
    )

    runtime = BrainRuntime(transcript_store=BrainTranscriptStore(transcript_path))
    runtime.managed_plugin_records = {
        "sensory-ingest-webhook": ManagedRecord(
            plugin=ingest_plugin,
            feature_key="sensory.ingest",
        ),
        "sensory-sanitize-basic": ManagedRecord(
            plugin=sanitize_plugin,
            feature_key="sensory.sanitize",
        ),
        "sensory-interpret-generic": ManagedRecord(
            plugin=interpret_plugin,
            feature_key="sensory.interpret",
        ),
        "model-provider-gemini": ManagedRecord(
            plugin=model_provider,
            feature_key="core.model_provider",
        ),
        "simulation-thought-sandbox": ManagedRecord(
            plugin=simulation_plugin,
            feature_key="simulation.bundle",
        ),
    }

    registry = CognitiveToolRegistry(audit_logger=mock.Mock())
    tool_payload: dict[str, object] = {
        "plugin_id": "risk-comparator",
        "version": "1.0.0",
        "is_concurrency_safe": True,
        "status": (
            PluginLifecycleStatus.CANDIDATE
            if candidate_cognitive_only
            else PluginLifecycleStatus.ACTIVE
        ),
        "health_status": "healthy",
        "rollback_conditions": ["ranking_regression_detected"],
        "revocation_reasons": ["reserved_for_runtime_audit"],
        "tool_type": "risk_comparator",
        "purpose": "Compare candidate options.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "required_context": ["candidate_paths"],
        "trigger_conditions": ["multiple_candidate_paths"],
        "behavior_key": "risk_assessment",
        "do_not_use_when": ["execution_requested"],
    }
    plugin = FakeCognitiveToolPlugin.model_validate(tool_payload)
    registry.register(plugin)
    registry.promote_plugin(
        "risk-comparator",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox ready",
    )
    if not candidate_cognitive_only:
        registry.promote_plugin(
            "risk-comparator",
            PluginLifecycleStatus.ACTIVE,
            audit_reason="active for think loop phase 7",
        )
    runtime.cognitive_tool_registry = registry
    return runtime


def _build_session(runtime: mock.Mock) -> mock.Mock:
    session = mock.Mock()
    session.session_id = "session-think-loop"
    session.turn_counter = 2
    session.current_workspace = {"cwd": "/workspace/zentex"}
    session.active_goal_frame = {"goals": [{"title": "Protect continuity"}]}
    session.last_working_memory = {"current_focus_summary": "Stabilize runtime replay"}
    session.last_metacognition = {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": [],
    }
    session.last_conflict_snapshot = {"confidence_drift": "stable"}
    session.runtime = runtime
    session.get_snapshot.return_value = BrainSessionSnapshot(
        session_id="session-think-loop",
        turn_count=2,
        active_goal_titles=["Protect continuity"],
        current_focus_summary="Stabilize runtime replay",
        overdue_items=["refresh working state"],
        current_reasoning_mode="deliberate",
        degraded_flags=[],
        last_turn_at=datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
    )
    return session


def test_think_loop_run_calls_9_phases_in_strict_order() -> None:
    runtime = _build_runtime()
    session = _build_session(runtime)
    think_loop = ThinkLoop()
    call_order: list[str] = []

    observed = {"workspace": session.current_workspace, "session_snapshot": session.get_snapshot.return_value}
    framed = {"context_snapshot": {"role_hypothesis": "operator"}, "observed": observed}
    working_state = {
        "working_memory": {"current_focus_summary": "focus"},
        "temporal_agenda": {"overdue_items": []},
        "living_self_model": {"current_reasoning_mode": "baseline", "degraded_flags": []},
    }
    risks = {"conflict_snapshot": {"conflicts": [], "confidence_drift": "stable"}}
    simulation = {
        "counterfactual_simulation": {"is_safe": True},
        "interaction_mind": {"stakeholders": []},
    }
    metacognition = {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": [],
        "tool_plan": [],
        "escalation_required": False,
    }
    tool_invocations = {"invocations": [], "merged_result": {}}
    decision_summary = {"status": "ready", "summary": "hold"}
    consolidation = {
        "reflection_record": {"summary": "reflection"},
        "consolidation": {"ready_for_transcript": True},
    }

    def record(name: str, payload: object):
        def _side_effect(*args, **kwargs):
            call_order.append(name)
            return payload

        return _side_effect

    with (
        mock.patch.object(think_loop, "_phase_1_observe", side_effect=record("phase_1", observed)),
        mock.patch.object(think_loop, "_phase_2_frame", side_effect=record("phase_2", framed)),
        mock.patch.object(think_loop, "_phase_3_update_working_state", side_effect=record("phase_3", working_state)),
        mock.patch.object(think_loop, "_phase_4_detect_cognitive_risks", side_effect=record("phase_4", risks)),
        mock.patch.object(think_loop, "_phase_5_simulate", side_effect=record("phase_5", simulation)),
        mock.patch.object(think_loop, "_phase_6_metacognition", side_effect=record("phase_6", metacognition)),
        mock.patch.object(think_loop, "_phase_7_orchestrate_cognitive_tools", side_effect=record("phase_7", tool_invocations)),
        mock.patch.object(think_loop, "_phase_8_synthesize_decision", side_effect=record("phase_8", decision_summary)),
        mock.patch.object(think_loop, "_phase_9_consolidate", side_effect=record("phase_9", consolidation)),
    ):
        result = think_loop.run(session)

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
    assert isinstance(result, BrainTurnResult)
    assert result.turn_id == "session-think-loop-turn-0003"


def test_phase_7_blocks_candidate_cognitive_tool_before_execution() -> None:
    runtime = _build_runtime(candidate_cognitive_only=True)
    session = _build_session(runtime)
    think_loop = ThinkLoop()

    with pytest.raises(PluginNotBoundError, match="No active bound plugin"):
        think_loop._phase_7_orchestrate_cognitive_tools(
            session=session,
            turn_id="session-think-loop-turn-0003",
            metacognition={
                "current_reasoning_mode": "deliberate",
                "candidate_paths": [{"option_id": "a"}, {"option_id": "b"}],
                "tool_plan": [{"behavior_key": "risk_assessment"}],
            },
        )


def test_phase_2_fail_closed_when_model_provider_is_inactive_or_remote_fails() -> None:
    inactive_runtime = _build_runtime(model_provider_status=PluginLifecycleStatus.CANDIDATE)
    inactive_session = _build_session(inactive_runtime)
    think_loop = ThinkLoop()
    observed = {
        "workspace": inactive_session.current_workspace,
        "session_snapshot": inactive_session.get_snapshot.return_value,
        "environment_event": {},
        "previous_snapshots": {},
    }

    with pytest.raises(PluginNotBoundError, match="model_provider"):
        think_loop._phase_2_frame(
            session=inactive_session,
            turn_id="session-think-loop-turn-0003",
            observed=observed,
            phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
        )

    failing_runtime = _build_runtime()
    failing_runtime.managed_plugin_records["model-provider-gemini"].plugin.generate_json.side_effect = (
        ModelProviderRemoteError("network unreachable")
    )
    failing_session = _build_session(failing_runtime)

    with pytest.raises(ModelProviderRemoteError, match="network unreachable"):
        think_loop._phase_2_frame(
            session=failing_session,
            turn_id="session-think-loop-turn-0003",
            observed=observed,
            phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
        )


def test_phase_2_injects_complete_nine_question_refs_into_model_caller_context() -> None:
    runtime = _build_runtime()
    session = _build_session(runtime)
    think_loop = ThinkLoop()
    observed = {
        "workspace": session.current_workspace,
        "session_snapshot": session.get_snapshot.return_value,
        "environment_event": {"event_type": "environment.observed"},
        "previous_snapshots": {"working_memory": {"current_focus_summary": "focus"}},
    }

    think_loop._phase_2_frame(
        session=session,
        turn_id="session-think-loop-turn-0003",
        observed=observed,
        phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
    )

    _, kwargs = runtime.managed_plugin_records["model-provider-gemini"].plugin.generate_json.call_args
    context = kwargs["context"]
    caller_context = kwargs["caller_context"]
    assert "context_snapshot" not in context
    assert "current_conversation_state" in context
    assert "observed_environment_signal" in context
    assert caller_context.source_module == "Main reasoning loop"
    assert caller_context.invocation_phase == "framing the situation"
    assert caller_context.question_driver_refs == [
        "我是谁",
        "我现在在哪个情境里",
        "我受到哪些约束",
        "我现在应该优先想什么",
    ]

    entries = runtime.transcript_store.read_by_turn_id("session-think-loop-turn-0003")
    llm_entries = [entry for entry in entries if "model_provider" in entry.entry_type.value]
    assert llm_entries
    assert all(entry.trace_id == "session-think-loop-turn-0003:phase_2_frame" for entry in llm_entries)


def test_phase_2_halts_when_manual_pause_targets_guarded_phase() -> None:
    runtime = _build_runtime()
    runtime.intervention_state = {
        "mode": "manual",
        "paused": True,
        "target_phase": "phase_2_frame",
        "operator_id": "tester-operator",
        "reason": "review role inference before continuing",
        "manual_context_patch": {},
        "last_action": "pause",
        "updated_at": "2026-04-04T00:00:00+00:00",
    }
    session = _build_session(runtime)
    think_loop = ThinkLoop()
    observed = {
        "workspace": session.current_workspace,
        "session_snapshot": session.get_snapshot.return_value,
        "environment_event": {},
        "previous_snapshots": {},
    }

    with pytest.raises(ManualInterventionRequiredError, match="phase_2_frame"):
        think_loop._phase_2_frame(
            session=session,
            turn_id="session-think-loop-turn-0003",
            observed=observed,
            phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
        )


def test_think_loop_cold_start_forces_real_q1_to_q9_on_empty_session() -> None:
    transcript_path = PROJECT_ROOT / "tmp_test_cold_start_think_loop_transcript.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()

    provider_calls: list[dict[str, object]] = []

    class ColdStartProvider(FakePlugin):
        def generate_json(self, **kwargs):  # type: ignore[no-untyped-def]
            caller_context = kwargs["caller_context"]
            provider_calls.append(
                {
                    "phase": caller_context.invocation_phase,
                    "context": kwargs["context"],
                    "refs": list(caller_context.question_driver_refs or []),
                }
            )
            phase = caller_context.invocation_phase
            if phase == "nine_question_q1_where_am_i":
                return {
                    "primary_domain": "web_console",
                    "secondary_domains": ["runtime"],
                    "confidence": 0.9,
                    "reasoning_summary": "cold start workspace snapshot",
                    "uncertainties": ["limited initial context"],
                    "suggested_first_step": "inspect startup evidence",
                }
            if phase == "nine_question_q2_who_am_i":
                return {
                    "role_profile": {
                        "identity_role": "operator",
                        "active_role": "operator",
                        "task_role": "runtime_guard",
                    },
                    "mission_boundary": {
                        "current_mission": "initialize the runtime truthfully",
                        "priority_duties": ["complete nine questions"],
                        "continuity_boundaries": ["no fabricated state"],
                    },
                }
            if phase == "nine_question_q3_what_do_i_have":
                return {
                    "unified_asset_inventory": {
                        "available_cognitive_tools": [],
                        "available_execution_tools": [],
                        "connected_agents": [],
                        "activated_strategy_patches": [],
                        "accessible_workspace_zones": ["/workspace"],
                    },
                    "resource_evaluation": {
                        "resource_status": "sufficient",
                        "missing_critical_assets": [],
                        "bottleneck_node": "none",
                    },
                }
            if phase == "nine_question_q4_what_can_i_do":
                return {
                    "capability_boundary_profile": {
                        "capability_upper_limits": ["inspect"],
                        "actionable_space": ["inspect evidence"],
                        "executable_strategies": ["read-only triage"],
                    }
                }
            if phase == "nine_question_q5_authorization":
                return {
                    "authorization_boundary_profile": {
                        "allowed_action_space": ["inspect evidence"],
                        "forbidden_action_space": [{"action": "write files", "reason": "needs confirmation"}],
                        "contact_and_org_boundaries": {"allowed_contacts": ["operator"]},
                        "requires_escalation_actions": ["write files"],
                    }
                }
            if phase == "nine_question_q6_redline":
                return {
                    "forbidden_zone_profile": {
                        "absolute_red_lines": ["no fabricated runtime state"],
                        "performance_tradeoff_bans": ["no skip audit"],
                        "prohibited_strategies": ["pretend initialization finished"],
                        "contamination_risks": ["stale transcript replay"],
                    }
                }
            if phase == "nine_question_q7_alternatives":
                return {
                    "alternative_strategy_profile": {
                        "fallback_plans": ["render initializing state"],
                        "degradation_strategies": ["delay non-essential panels"],
                        "collaboration_switches": ["ask operator for confirmation"],
                        "exploratory_actions": ["poll initialization progress"],
                    }
                }
            if phase == "nine_question_q8_decision":
                return {
                    "objective_profile": {
                        "current_primary_objective": "finish cold start onboarding",
                        "current_phase_tasks": ["run q1-q9", "persist state"],
                        "priority_order": ["run q1-q9", "persist state"],
                    },
                    "task_queue": {
                        "next_self_tasks": [{"task": "persist_state"}],
                        "blocked_self_tasks": [],
                        "proactive_actions": [{"task": "refresh_ui"}],
                    },
                }
            if phase == "nine_question_q9_posture":
                return {
                    "evaluation_style": "evidence_first",
                    "risk_tolerance": "low",
                    "action_rhythm": "steady and auditable",
                    "confirmation_strategy": "confirm before mutation",
                    "evolution_direction": "build trustworthy startup state",
                }
            raise AssertionError(f"unexpected phase: {phase}")

    ingest_plugin = FakePlugin(
        plugin_id="sensory-ingest-webhook",
        kind="signal_ingest",
        status=PluginLifecycleStatus.ACTIVE,
        ingest_signal=mock.Mock(return_value="system telemetry"),
    )
    sanitize_plugin = FakePlugin(
        plugin_id="sensory-sanitize-basic",
        kind="signal_sanitize",
        status=PluginLifecycleStatus.ACTIVE,
        sanitize_signal=mock.Mock(
            return_value=mock.Mock(
                sanitized_text="system telemetry",
                raw_fingerprint="fingerprint",
                injection_risk=False,
                redaction_evidence=[],
            )
        ),
    )
    interpret_plugin = FakePlugin(
        plugin_id="sensory-interpret-generic",
        kind="signal_interpret",
        status=PluginLifecycleStatus.ACTIVE,
        interpret_signal=mock.Mock(
            return_value=mock.Mock(
                model_dump=mock.Mock(
                    return_value={
                        "event_type": "environment.observed",
                        "summary": "Observed external signal",
                        "structured_payload": {"raw_fingerprint": "fingerprint"},
                    }
                )
            )
        ),
    )
    simulation_plugin = FakePlugin(
        plugin_id="simulation-thought-sandbox",
        kind="simulation_domain",
        status=PluginLifecycleStatus.ACTIVE,
        supported_domains=["general"],
        simulate_action=mock.Mock(
            return_value=mock.Mock(
                model_dump=mock.Mock(
                    return_value={
                        "is_safe": True,
                        "predicted_impacts": [],
                        "veto_reason": None,
                        "replan_required": False,
                    }
                )
            )
        ),
    )
    provider = ColdStartProvider(
        plugin_id="model-provider-cold-start",
        kind="model_provider",
        status=PluginLifecycleStatus.ACTIVE,
    )

    runtime = BrainRuntime(default_workspace=str(PROJECT_ROOT), transcript_store=BrainTranscriptStore(transcript_path))
    runtime.managed_plugin_records = {
        "sensory-ingest-webhook": ManagedRecord(plugin=ingest_plugin, feature_key="sensory.ingest"),
        "sensory-sanitize-basic": ManagedRecord(plugin=sanitize_plugin, feature_key="sensory.sanitize"),
        "sensory-interpret-generic": ManagedRecord(plugin=interpret_plugin, feature_key="sensory.interpret"),
        "model-provider-cold-start": ManagedRecord(plugin=provider, feature_key="core.model_provider"),
        "simulation-thought-sandbox": ManagedRecord(plugin=simulation_plugin, feature_key="simulation.bundle"),
    }
    runtime.plugin_registry = FakeGeneralPluginRegistry()

    runtime.cognitive_tool_registry = FakeNineQuestionRegistry(
        [
            build_q1_where_am_i_plugin(),
            build_q2_who_am_i_plugin(),
            build_q3_what_do_i_have_plugin(),
            build_q4_what_can_i_do_plugin(),
            build_q5_what_am_i_allowed_to_do_plugin(),
            build_q6_what_should_i_not_do_plugin(),
            build_q7_what_else_can_i_do_plugin(),
            build_q8_what_should_i_do_now_plugin(),
            build_q9_how_should_i_act_plugin(),
        ]
    )

    session = runtime.create_session("cold-start-session")
    session.current_workspace = {"cwd": str(PROJECT_ROOT)}
    session.active_goal_frame = {"goals": [{"title": "Cold-start onboarding"}]}

    result = ThinkLoop().run(session)

    assert isinstance(result, BrainTurnResult)
    assert len(provider_calls) == 9
    assert [call["phase"] for call in provider_calls] == [
        "nine_question_q1_where_am_i",
        "nine_question_q2_who_am_i",
        "nine_question_q3_what_do_i_have",
        "nine_question_q4_what_can_i_do",
        "nine_question_q5_authorization",
        "nine_question_q6_redline",
        "nine_question_q7_alternatives",
        "nine_question_q8_decision",
        "nine_question_q9_posture",
    ]
    assert provider_calls[0]["context"].get("environment_event") is not None
    assert provider_calls[1]["refs"] == ["cold_start:onboarding", "cold_start", "我是谁"]
    assert provider_calls[7]["context"].get("persistent_task_state") == []
    assert result.nine_question_state.snapshot_version >= 9


def test_manual_role_change_intervention_writes_audit_and_refreshes_nine_question_state() -> None:
    transcript_path = PROJECT_ROOT / "tmp_test_intervention_transcript.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()

    runtime = BrainRuntime(transcript_store=BrainTranscriptStore(transcript_path))
    session = runtime.create_session("session-intervention")

    previous_revision = runtime.nine_question_state.revision
    control_state = runtime.request_intervention(
        action="role_change",
        operator_id="tester-operator",
        reason="human rejected the old role framing",
        phase_name="phase_2_frame",
        manual_context_patch={
            "role_hint": "人工审核者",
            "current_focus": "先核对证据",
        },
    )
    session.advance_turn(
        {
            "turn_id": "intervention-turn-0001",
            "trace_id": "intervention-role_change",
            "timestamp": datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc),
            "status": "completed",
            "context_snapshot": {
                "nine_question_state": {
                    "question_driver_refs": runtime.nine_question_state.question_driver_refs,
                    "revision": runtime.nine_question_state.revision,
                    "last_refresh_reason": runtime.nine_question_state.last_refresh_reason,
                    "current_role_hypothesis": runtime.nine_question_state.current_role_hypothesis,
                    "operator_patch": runtime.nine_question_state.operator_patch,
                }
            },
            "human_intervention": {
                "action": "role_change",
                "reason": "human rejected the old role framing",
                "operator_id": "tester-operator",
                "phase_name": "phase_2_frame",
                "manual_context_patch": {
                    "role_hint": "人工审核者",
                    "current_focus": "先核对证据",
                },
                "control_state": control_state,
            },
        }
    )

    entries = runtime.transcript_store.read_by_session_id("session-intervention")
    intervention_entries = [
        entry for entry in entries if entry.entry_type == BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED
    ]
    assert intervention_entries
    assert intervention_entries[-1].payload["operator_id"] == "tester-operator"
    assert intervention_entries[-1].payload["manual_context_patch"]["role_hint"] == "人工审核者"

    assert runtime.nine_question_state.revision == previous_revision + 1
    assert runtime.nine_question_state.last_refresh_reason == "manual_intervention:role_change"
    assert runtime.nine_question_state.current_role_hypothesis == "人工审核者"
    assert runtime.nine_question_state.operator_patch["current_focus"] == "先核对证据"
    assert runtime.nine_question_state.question_driver_refs == [
        "我是谁",
        "我现在在哪个情境里",
        "我受到哪些约束",
        "我现在应该优先想什么",
    ]


def test_next_phase_2_consumes_manual_intervention_and_revalidates_nine_question_boundary() -> None:
    base_runtime = _build_runtime()
    transcript_path = PROJECT_ROOT / "tmp_test_phase2_revalidation_transcript.jsonl"
    if transcript_path.exists():
        transcript_path.unlink()

    runtime = BrainRuntime(transcript_store=BrainTranscriptStore(transcript_path))
    runtime.managed_plugin_records = base_runtime.managed_plugin_records
    runtime.cognitive_tool_registry = base_runtime.cognitive_tool_registry

    runtime.request_intervention(
        action="reject_action",
        operator_id="tester-operator",
        reason="human rejected the proposed action",
        phase_name="phase_2_frame",
        manual_context_patch={
            "role_hint": "人工审核者",
            "current_focus": "先核对证据",
            "rejected_action": "auto_execute",
        },
    )
    session = _build_session(runtime)
    think_loop = ThinkLoop()
    observed = {
        "workspace": session.current_workspace,
        "session_snapshot": session.get_snapshot.return_value,
        "environment_event": {"event_type": "environment.observed"},
        "previous_snapshots": {"working_memory": {"current_focus_summary": "focus"}},
    }

    with pytest.raises(ManualInterventionRequiredError):
        think_loop._phase_2_frame(
            session=session,
            turn_id="session-think-loop-turn-0003",
            observed=observed,
            phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
        )

    runtime.request_intervention(
        action="manual_confirm",
        operator_id="tester-operator",
        reason="apply the human-reviewed role patch",
        phase_name="phase_2_frame",
        manual_context_patch={
            "role_hint": "人工审核者",
            "current_focus": "先核对证据",
            "rejected_action": "auto_execute",
        },
    )

    result = think_loop._phase_2_frame(
        session=session,
        turn_id="session-think-loop-turn-0003",
        observed=observed,
        phase_trace_id="session-think-loop-turn-0003:phase_2_frame",
    )

    _, kwargs = runtime.managed_plugin_records["model-provider-gemini"].plugin.generate_json.call_args
    assert kwargs["caller_context"].question_driver_refs == [
        "我是谁",
        "我现在在哪个情境里",
        "我受到哪些约束",
        "我现在应该优先想什么",
    ]
    assert kwargs["context"]["operator supplied adjustment"] == {
        "role_hint": "人工审核者",
        "current_focus": "先核对证据",
        "rejected_action": "auto_execute",
    }
    highest_priority_intervention = kwargs["context"]["highest_priority_human_intervention"]
    assert highest_priority_intervention["trace_id"] == "intervention:manual_confirm"
    assert highest_priority_intervention["action"] == "manual_confirm"
    assert highest_priority_intervention["operator_id"] == "tester-operator"
    assert highest_priority_intervention["reason"] == "apply the human-reviewed role patch"
    assert highest_priority_intervention["manual_context_patch"] == {
        "role_hint": "人工审核者",
        "current_focus": "先核对证据",
        "rejected_action": "auto_execute",
    }
    assert highest_priority_intervention["priority"] == "highest"
    assert highest_priority_intervention["must_apply_to_next_model_call"] is True
    assert highest_priority_intervention["nine_question_state"]["last_refresh_reason"] == (
        "manual_intervention:manual_confirm"
    )
    assert result["context_snapshot"]["nine_question_state"]["operator_patch"]["rejected_action"] == "auto_execute"
    assert runtime.nine_question_state.last_refresh_reason == "think_loop:phase_2_frame"
    assert runtime.peek_priority_intervention_memory()["must_apply_to_next_model_call"] is False
