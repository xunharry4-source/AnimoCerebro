from __future__ import annotations

"""
ThinkLoop / 九阶段认知执行器

该模块负责编排单轮 ThinkLoop 的九个固定阶段，并把需要调用外部能力的步骤
接到受控插件体系上。这里同时承担大模型调用溯源的第一责任：在发起模型请求前，
必须补齐调用方身份、所处阶段以及九问驱动来源。
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any
from uuid import uuid4

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.core.simulation_spec import SimulationIntent
from zentex.runtime.cognitive_tools import CognitiveToolOrchestrator
from zentex.runtime.models import BrainTurnResult
from zentex.runtime.nine_questions.executor import NineQuestionExecutor
from zentex.runtime.session import BrainSession
from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot
from zentex.runtime.transcript import BrainTranscriptEntryType
from zentex.runtime.nine_questions.engine import NineQDrivenObjectiveEngine
from zentex.runtime.nine_questions.router import build_event


logger = logging.getLogger(__name__)


class ManualInterventionRequiredError(RuntimeError):
    """Raised when ThinkLoop must halt until a human intervention is resolved."""


class ThinkLoop:
    """
    Stateless single-turn cognitive executor.

    The nine-stage order is fixed protocol and must not change.
    All stage-internal capability access must resolve active bound plugins.
    """

    def __init__(self):
        self._evolution_engine = NineQDrivenObjectiveEngine()

    def _fetch_turn_history(self, session: BrainSession, limit: int = 3) -> list[dict[str, Any]]:
        """Fetch status of recent turns from transcript (Sub-function 3.4)."""
        entries = session.store.read_entries(session_id=session.session_id)
        finish_events = [e for e in entries if e.entry_type == BrainTranscriptEntryType.TURN_FINISHED]
        history = []
        for e in finish_events[-limit:]:
            if isinstance(e.payload, dict):
                history.append({
                    "turn_id": e.turn_id,
                    "status": e.payload.get("status", "unknown"),
                    "finished_at": e.timestamp.isoformat()
                })
        return history


    def run(self, session: BrainSession) -> BrainTurnResult:
        """
        执行一轮完整的九阶段认知循环。

        Args:
            session: 当前会话容器，提供工作状态、Transcript 写盘能力与运行时依赖。

        Returns:
            BrainTurnResult: 单轮认知的完整产物，供 `BrainSession` 后续持久化。

        Raises:
            PluginNotBoundError: 当必需插件未绑定或未激活时抛出。
            RuntimeError: 当运行时缺少 Transcript 等强依赖时抛出。
        """
        started_at = datetime.now(timezone.utc)
        turn_id = self._next_turn_id(session)
        phase_trace_ids: dict[str, str] = self._build_phase_trace_ids(turn_id)

        observed = self._phase_1_observe(session=session, turn_id=turn_id, started_at=started_at)
        cold_start_protocol_applied = self._maybe_run_cold_start_protocol(
            session=session,
            observed=observed,
            turn_id=turn_id,
        )
        framed = self._phase_2_frame(
            session=session,
            turn_id=turn_id,
            observed=observed,
            phase_trace_id=phase_trace_ids["context_snapshot"],
        )
        working_state = self._phase_3_update_working_state(session=session, framed=framed)
        cognitive_risks = self._phase_4_detect_cognitive_risks(
            session=session,
            working_state=working_state,
        )
        simulation = self._phase_5_simulate(
            session=session,
            framed=framed,
            cognitive_risks=cognitive_risks,
        )
        metacognition = self._phase_6_metacognition(
            session=session,
            working_state=working_state,
            cognitive_risks=cognitive_risks,
            simulation=simulation,
        )
        tool_invocations = (
            {"invocations": [], "merged_result": {}}
            if cold_start_protocol_applied
            else self._phase_7_orchestrate_cognitive_tools(
                session=session,
                turn_id=turn_id,
                metacognition=metacognition,
            )
        )
        decision_summary = self._phase_8_synthesize_decision(
            session=session,
            turn_id=turn_id,
            metacognition=metacognition,
            tool_invocations=tool_invocations,
            simulation=simulation,
            phase_trace_id=phase_trace_ids["decision"],
            cold_start_protocol_applied=cold_start_protocol_applied,
        )

        # Update Evolution Profiles after decision synthesis
        evolution_result_v8 = None
        if hasattr(session, "current_nine_question_state") and session.current_nine_question_state:
             history = self._fetch_turn_history(session)
             evolution_result_v8 = self._evolution_engine.derive_all_profiles(
                 session.current_nine_question_state,
                 resource_state=observed.get("workspace"), # Proxy for resource state
                 history=history
             )
             session.active_evolution_result = evolution_result_v8.model_dump(mode="json")
        consolidation = self._phase_9_consolidate(
            session=session,
            decision_summary=decision_summary,
            working_state=working_state,
        )

        finished_at = datetime.now(timezone.utc)
        return BrainTurnResult(
            session_id=session.session_id,
            turn_id=turn_id,
            started_at=started_at,
            finished_at=finished_at,
            context_snapshot=framed["context_snapshot"],
            nine_question_state=getattr(session, "current_nine_question_state", None),
            working_memory=working_state["working_memory"],
            temporal_agenda=working_state["temporal_agenda"],
            living_self_model=working_state["living_self_model"],
            metacognition=metacognition,
            conflict_snapshot=cognitive_risks["conflict_snapshot"],
            counterfactual_simulation=simulation["counterfactual_simulation"],
            interaction_mind=simulation["interaction_mind"],
            tool_invocations=tool_invocations["invocations"],
            cognitive_tool_context=tool_invocations["merged_result"],
            decision_summary=decision_summary,
            reflection_record=consolidation["reflection_record"],
            consolidation=consolidation["consolidation"],
            trace_id=turn_id,
            phase_trace_ids=phase_trace_ids,
            evolution_result=getattr(session, "active_evolution_result", None),
        )

    def _maybe_run_cold_start_protocol(
        self,
        *,
        session: BrainSession,
        observed: dict[str, Any],
        turn_id: str,
    ) -> bool:
        runtime = self._require_runtime(session)
        state = getattr(session, "current_nine_question_state", None)
        if state is None:
            state = getattr(runtime, "nine_question_state", None)
        if state is None:
            return False
        if not self._is_cold_start_session(session=session, state=state):
            if hasattr(runtime, "set_nine_question_bootstrap_status") and state.question_snapshots:
                runtime.set_nine_question_bootstrap_status("ready")
            return False

        registry = getattr(runtime, "cognitive_tool_registry", None)
        if registry is None:
            raise PluginNotBoundError("cognitive_tool_registry is not attached to the runtime")

        workspace_root = self._resolve_workspace_root(session=session, runtime=runtime)
        startup_context = build_runtime_workspace_snapshot(
            workspace_root=workspace_root,
            cognitive_registry=registry,
            execution_registry=getattr(runtime, "execution_registry", None),
            task_service=getattr(runtime, "task_service", None),
            environment_summary="cold-start onboarding protocol running full nine-question inference",
            host_telemetry_plugin=next(
                (
                    getattr(record, "plugin", None)
                    for record in getattr(runtime, "managed_plugin_records", {}).values()
                    if getattr(record, "feature_code", None) == "host.telemetry"
                    and getattr(getattr(record, "plugin", None), "status", None)
                    == PluginLifecycleStatus.ACTIVE
                ),
                None,
            ),
        )
        environment_event = observed.get("environment_event")
        if isinstance(environment_event, dict):
            startup_context["environment_event"] = dict(environment_event)
            structured = environment_event.get("structured_payload")
            if isinstance(structured, dict) and structured.get("raw_fingerprint"):
                state.environment_fingerprint = str(structured["raw_fingerprint"])

        session.last_context_snapshot = dict(startup_context)
        runtime.nine_question_state = state
        session.current_nine_question_state = state

        trace_id = f"{turn_id}:cold-start-nine-questions"
        if hasattr(runtime, "set_nine_question_bootstrap_status"):
            runtime.set_nine_question_bootstrap_status("initializing", trace_id=trace_id)

        event = build_event(
            event_type="cold_start",
            reason="think_loop_cold_start_onboarding",
            trace_id=trace_id,
            dirty_questions=runtime.nine_question_router.derive_dirty_questions_for_event("cold_start"),
            payload={"workspace_root": workspace_root},
        )
        runtime.nine_question_router.publish(state, event)
        runtime.refresh_nine_question_state(
            question_driver_refs=["cold_start:onboarding", "q1->q9"],
            refresh_reason="think_loop_cold_start_onboarding",
            context_snapshot=startup_context,
            active_constraints=[],
        )

        executor = NineQuestionExecutor(
            registry=registry,
            transcript_store=runtime.transcript_store,
        )
        try:
            for queued_event in runtime.nine_question_router.drain():
                executor.run_questions(
                    runtime=runtime,
                    session=session,
                    state=state,
                    question_ids=queued_event.dirty_questions,
                    trace_id=queued_event.trace_id,
                    refresh_reason=queued_event.reason,
                    driver_refs=["cold_start:onboarding", queued_event.event_type],
                    turn_id=turn_id,
                )
        except Exception as exc:
            if hasattr(runtime, "set_nine_question_bootstrap_status"):
                runtime.set_nine_question_bootstrap_status(
                    "failed",
                    trace_id=trace_id,
                    error=str(exc),
                )
            raise

        if hasattr(runtime, "set_nine_question_bootstrap_status"):
            runtime.set_nine_question_bootstrap_status("ready", trace_id=trace_id)
        return True

    def _is_cold_start_session(self, *, session: BrainSession, state: Any) -> bool:
        if getattr(state, "question_snapshots", {}):
            return False
        store = getattr(session, "store", None)
        if store is None or not callable(getattr(store, "read_by_session_id", None)):
            return True
        entries = store.read_by_session_id(session.session_id)
        if not entries:
            return True
        return not any(
            getattr(entry.entry_type, "value", entry.entry_type) == BrainTranscriptEntryType.NINE_QUESTION_STATE_UPDATED.value
            for entry in entries
        )

    def _resolve_workspace_root(self, *, session: BrainSession, runtime: Any) -> str:
        current_workspace = getattr(session, "current_workspace", None)
        if isinstance(current_workspace, dict):
            cwd = current_workspace.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                return cwd
        if isinstance(current_workspace, str) and current_workspace.strip():
            return current_workspace
        workspace = getattr(runtime, "default_workspace", None)
        if isinstance(workspace, str) and workspace.strip():
            return workspace
        return os.getcwd()

    def _phase_1_observe(
        self,
        *,
        session: BrainSession,
        turn_id: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        """阶段 1：摄取并解释环境信号，形成后续 framing 的输入。"""
        logger.debug("ThinkLoop phase 1 observe session=%s", session.session_id)
        ingest_plugin = self._resolve_active_managed_plugin(
            session,
            feature_key="sensory.ingest",
            plugin_kind="signal_ingest",
        )
        sanitize_plugin = self._resolve_active_managed_plugin(
            session,
            feature_key="sensory.sanitize",
            plugin_kind="signal_sanitize",
        )
        interpret_plugin = self._resolve_active_managed_plugin(
            session,
            feature_key="sensory.interpret",
            plugin_kind="signal_interpret",
        )

        raw_signal = ingest_plugin.ingest_signal()
        sanitized_signal = sanitize_plugin.sanitize_signal(raw_signal)
        environment_event = interpret_plugin.interpret_signal(sanitized_signal)
        return {
            "turn_id": turn_id,
            "started_at": started_at,
            "workspace": session.current_workspace,
            "session_snapshot": session.get_snapshot(),
            "environment_event": environment_event.model_dump(mode="json"),
            "previous_snapshots": {
                "working_memory": session.last_working_memory,
                "metacognition": session.last_metacognition,
                "conflict_snapshot": session.last_conflict_snapshot,
            },
        }

    def _phase_2_frame(
        self,
        *,
        session: BrainSession,
        turn_id: str,
        observed: dict[str, Any],
        phase_trace_id: str,
    ) -> dict[str, Any]:
        """
        阶段 2：构建当前情境框架，并发起第一类强制 LLM 调用。

        Args:
            session: 当前会话。
            turn_id: 当前轮次标识。
            observed: 阶段 1 产物。
            phase_trace_id: 当前阶段的统一 trace 标识。
        """
        logger.debug("ThinkLoop phase 2 frame session=%s", session.session_id)
        runtime = self._require_runtime(session)

        # Manual intervention guardrail (fail-closed): if a human intervention is queued
        # for this phase, we either halt or inject it into the next model call.
        priority_intervention = (
            runtime.peek_priority_intervention_memory()
            if hasattr(runtime, "peek_priority_intervention_memory")
            else {"must_apply_to_next_model_call": False}
        )
        if (
            isinstance(priority_intervention, dict)
            and priority_intervention.get("must_apply_to_next_model_call") is True
            and priority_intervention.get("target_phase") == "phase_2_frame"
        ):
            action = priority_intervention.get("action")
            if action not in {"manual_confirm", "role_change"}:
                raise ManualInterventionRequiredError(
                    "Manual intervention pending for guarded phase: phase_2_frame"
                )
        elif (
            isinstance(getattr(runtime, "intervention_state", None), dict)
            and runtime.intervention_state.get("paused") is True
            and runtime.intervention_state.get("target_phase") == "phase_2_frame"
        ):
            raise ManualInterventionRequiredError(
                "Manual pause engaged for guarded phase: phase_2_frame"
            )

        state = getattr(session, "current_nine_question_state", None)
        if state is None:
            # If the session does not carry the cache, we still keep legacy behavior.
            state = getattr(runtime, "nine_question_state", None)

        fingerprint = None
        if isinstance(observed.get("environment_event"), dict):
            structured = observed["environment_event"].get("structured_payload")
            if isinstance(structured, dict) and structured.get("raw_fingerprint"):
                fingerprint = str(structured["raw_fingerprint"])

        needs_refresh = False
        if state is None:
            needs_refresh = True
        else:
            # Cold start: session cache never built.
            snapshot_ver = getattr(state, "snapshot_version", 0)
            if not isinstance(snapshot_ver, int) or snapshot_ver <= 0:
                needs_refresh = True
            # Dirty flags: only allow refresh when explicitly marked.
            if any(getattr(state, "is_dirty")(qid) for qid in ("q1", "q2", "q3")):  # type: ignore[misc]
                needs_refresh = True
            # Major environment change: fingerprint drift.
            if fingerprint and getattr(state, "environment_fingerprint", None) != fingerprint:
                state.environment_fingerprint = fingerprint
                if hasattr(state, "mark_dirty"):
                    state.mark_dirty(["q1", "q2", "q3"], reason="environment_fingerprint_changed")
                needs_refresh = True
            # Human intervention should pierce cache and force refresh.
            if (
                isinstance(priority_intervention, dict)
                and priority_intervention.get("must_apply_to_next_model_call") is True
                and priority_intervention.get("target_phase") == "phase_2_frame"
                and priority_intervention.get("action") in {"manual_confirm", "role_change"}
            ):
                if hasattr(state, "mark_dirty"):
                    state.mark_dirty(["q2"], reason="manual_intervention")
                needs_refresh = True

        if not needs_refresh and state is not None:
            context_snapshot = {
                "workspace": observed["workspace"],
                "active_goal_frame": session.active_goal_frame,
                "role_hypothesis": getattr(state, "current_role_hypothesis", None) or "unknown_role",
                "nine_question_frame": getattr(state, "question_snapshots", {}),
                "constraints": list(getattr(state, "active_constraints", []) or []),
                "immediate_priorities": [],
                "nine_question_state": state.to_payload() if hasattr(state, "to_payload") else {},
            }
            # Derive evolution profiles from existing state
            history = self._fetch_turn_history(session)
            evolution_result = self._evolution_engine.derive_all_profiles(
                state,
                resource_state=observed.get("workspace"),
                history=history
            )
            session.active_evolution_result = evolution_result.model_dump(mode="json")

            return {"observed": observed, "context_snapshot": context_snapshot, "evolution_result": evolution_result}

        # Refresh path (allowed only when cold start / dirty / environment change / intervention).
        provider = self._resolve_active_model_provider(session)
        prompt = (
            "Generate Zentex turn framing. Return JSON with keys "
            "role_hypothesis, nine_question_frame, constraints, immediate_priorities."
        )
        context: dict[str, Any] = {
            "session_id": session.session_id,
            "workspace": observed["workspace"],
            "session_snapshot": self._session_snapshot_to_dict(observed["session_snapshot"]),
            "environment_event": observed["environment_event"],
            "previous_snapshots": observed["previous_snapshots"],
        }
        if (
            isinstance(priority_intervention, dict)
            and priority_intervention.get("must_apply_to_next_model_call") is True
            and priority_intervention.get("target_phase") == "phase_2_frame"
            and priority_intervention.get("action") in {"manual_confirm", "role_change"}
        ):
            context["operator supplied adjustment"] = priority_intervention.get("manual_context_patch", {})
            context["highest_priority_human_intervention"] = priority_intervention
            if hasattr(runtime, "mark_priority_intervention_applied"):
                runtime.mark_priority_intervention_applied()
        frame_payload = self._invoke_model_provider(
            session=session,
            turn_id=turn_id,
            phase_name="phase_2_frame",
            provider=provider,
            prompt=prompt,
            context=context,
            phase_trace_id=phase_trace_id,
            request_driver={
                "nine_question_inputs": [
                    "workspace",
                    "session_snapshot",
                    "environment_event",
                    "previous_snapshots",
                ],
                "question_driver_refs": [
                    "我是谁",
                    "我现在在哪个情境里",
                    "我受到哪些约束",
                    "我现在应该优先想什么",
                ],
                "assembly_reason": "role inference and nine-question framing",
            },
        )
        context_snapshot = {
            "workspace": observed["workspace"],
            "active_goal_frame": session.active_goal_frame,
            "role_hypothesis": frame_payload["role_hypothesis"],
            "nine_question_frame": frame_payload["nine_question_frame"],
            "constraints": frame_payload.get("constraints", []),
            "immediate_priorities": frame_payload.get("immediate_priorities", []),
        }
        if state is not None and hasattr(state, "apply_question_result"):
            # Update the cache without forcing individual Q1/Q2/Q3 plugins (fast path: reuse legacy framing).
            now = datetime.now(timezone.utc)
            if isinstance(getattr(state, "revision", None), int):
                state.revision += 1
            if isinstance(getattr(state, "snapshot_version", None), int):
                state.snapshot_version += 1
            state.last_refresh_reason = "think_loop:phase_2_frame"
            state.refreshed_at = now
            state.current_role_hypothesis = frame_payload.get("role_hypothesis")
            if isinstance(context_snapshot, dict):
                state.current_context.update(context_snapshot)
            state.active_constraints = list(context_snapshot.get("constraints", []) or [])
            if fingerprint:
                state.environment_fingerprint = fingerprint
            if hasattr(state, "mark_clean"):
                for qid in ("q1", "q2", "q3"):
                    state.mark_clean(qid)
            # Store minimal per-question snapshots for UI/readers.
            if hasattr(state, "question_snapshots"):
                frame = frame_payload.get("nine_question_frame")
                if isinstance(frame, dict):
                    state.question_snapshots.update(frame)
            context_snapshot["nine_question_state"] = state.to_payload()
        elif hasattr(runtime, "refresh_nine_question_state"):
            runtime.refresh_nine_question_state(
                question_driver_refs=[
                    "我是谁",
                    "我现在在哪个情境里",
                    "我受到哪些约束",
                    "我现在应该优先想什么",
                ],
                refresh_reason="think_loop:phase_2_frame",
                context_snapshot=context_snapshot,
                active_constraints=context_snapshot.get("constraints", []) or [],
            )
            context_snapshot["nine_question_state"] = runtime.nine_question_state.to_payload()

        return {
            "observed": observed,
            "context_snapshot": context_snapshot,
        }

    def _phase_3_update_working_state(
        self,
        *,
        session: BrainSession,
        framed: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段 3：把 framing 结果规整为工作记忆、时间议程和自我模型。"""
        logger.debug("ThinkLoop phase 3 update_working_state session=%s", session.session_id)
        snapshot = session.get_snapshot()
        runtime = self._require_runtime(session)

        if hasattr(runtime, "working_memory_controller") and runtime.working_memory_controller:
            from zentex.runtime.working_memory import AttentionItem
            wm_frame = runtime.working_memory_controller.upsert_focus(
                AttentionItem(
                    focus_id=f"focus-{session.session_id}",
                    focus_type="exploratory",
                    title=framed["context_snapshot"].get("role_hypothesis") or "no_focus_declared",
                    priority=5,
                    urgency=3,
                    blocked=False,
                    interruptible=True,
                    resume_hint="continue exploration"
                )
            )
            working_memory = wm_frame.__dict__
        else:
            working_memory = {
                "current_focus_summary": (
                    snapshot.current_focus_summary
                    or framed["context_snapshot"].get("role_hypothesis")
                    or "no_focus_declared"
                ),
                "active_goal_titles": snapshot.active_goal_titles,
                "role_hypothesis": framed["context_snapshot"].get("role_hypothesis"),
            }

        if hasattr(runtime, "temporal_engine") and runtime.temporal_engine:
            from datetime import datetime, timezone
            temp_state = runtime.temporal_engine.evaluate(datetime.now(timezone.utc))
            temporal_agenda = temp_state.__dict__
        else:
            temporal_agenda = {
                "overdue_items": snapshot.overdue_items,
                "next_actions": framed["context_snapshot"].get("immediate_priorities", []),
            }

        if hasattr(runtime, "living_self_model_engine") and runtime.living_self_model_engine:
            from zentex.runtime.self_model import CognitiveStateProfile
            current_state = CognitiveStateProfile(
                load_level="medium", stability_level="stable", exploration_mode="medium", 
                reasoning_posture="balanced", evidence_posture="normal"
            )
            sm_model, sm_drift, sm_recs = runtime.living_self_model_engine.update_self_model(
                current_state=current_state,
                failure_signals={},
                confidence_signals={}
            )
            living_self_model = sm_model.__dict__
        else:
            living_self_model = {
                "current_reasoning_mode": snapshot.current_reasoning_mode or "baseline",
                "degraded_flags": snapshot.degraded_flags,
                "continuity_anchor": session.session_id,
            }

        return {
            "working_memory": working_memory,
            "temporal_agenda": temporal_agenda,
            "living_self_model": living_self_model,
        }

    def _phase_4_detect_cognitive_risks(
        self,
        *,
        session: BrainSession,
        working_state: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段 4：识别当前回合的认知风险与置信度漂移。"""
        logger.debug("ThinkLoop phase 4 detect_cognitive_risks session=%s", session.session_id)
        runtime = self._require_runtime(session)
        degraded_flags: list[str] = working_state["living_self_model"].get("degraded_flags", [])

        if hasattr(runtime, "conflict_engine") and runtime.conflict_engine:
            conflicts = runtime.conflict_engine.detect(
                working_memory=working_state["working_memory"],
                self_model=working_state["living_self_model"],
                agenda=working_state["temporal_agenda"],
            )
            triggers = runtime.conflict_engine.generate_triggers()
            conflict_snapshot = {
                "conflicts": [c.__dict__ for c in conflicts],
                "triggers": [t.__dict__ for t in triggers],
                "confidence_drift": "elevated" if degraded_flags else "stable",
                "degraded_flags": degraded_flags,
                "uncertainty_hotspots": [],
            }
        else:
            conflict_snapshot = {
                "conflicts": [],
                "uncertainty_hotspots": [],
                "confidence_drift": "elevated" if degraded_flags else "stable",
                "degraded_flags": degraded_flags,
            }
        
        return {
            "conflict_snapshot": conflict_snapshot
        }

    def _phase_5_simulate(
        self,
        *,
        session: BrainSession,
        framed: dict[str, Any],
        cognitive_risks: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段 5：调用思维沙盒完成反事实模拟。"""
        logger.debug("ThinkLoop phase 5 simulate session=%s", session.session_id)
        plugin = self._resolve_simulation_plugin(session, target_domain="general")
        result = plugin.simulate_action(
            SimulationIntent(
                intent_name="internal_reasoning_turn",
                target_domain="general",
                intent_payload={
                    "context_snapshot": framed["context_snapshot"],
                    "conflict_snapshot": cognitive_risks["conflict_snapshot"],
                },
                risk_level="medium",
            ),
            {
                "context_snapshot": framed["context_snapshot"],
                "conflict_snapshot": cognitive_risks["conflict_snapshot"],
            },
        )
        return {
            "counterfactual_simulation": result.model_dump(mode="json"),
            "interaction_mind": {
                "stakeholders": [],
                "predicted_reactions": [],
            },
        }

    def _phase_6_metacognition(
        self,
        *,
        session: BrainSession,
        working_state: dict[str, Any],
        cognitive_risks: dict[str, Any],
        simulation: dict[str, Any],
    ) -> dict[str, Any]:
        """
        阶段 6：产出当前轮的元认知调度结果。
        """
        logger.debug("ThinkLoop phase 6 metacognition session=%s", session.session_id)
        runtime = self._require_runtime(session)

        if hasattr(runtime, "metacognition_controller") and runtime.metacognition_controller:
            reasoning, tool_plan, esc = runtime.metacognition_controller.generate_decisions(
                working_memory=working_state["working_memory"],
                living_self_model=working_state["living_self_model"],
                budget={"remaining": 1.0}, # Mock budget format
                agenda=working_state["temporal_agenda"],
                tool_registry=getattr(runtime, "cognitive_tool_registry", None),
            )
            
            structured_tool_plan = [
                {"plugin_id": tid, "behavior_key": tid}
                for tid in tool_plan.selected_tools
            ]

            return {
                "current_reasoning_mode": reasoning.thought_mode,
                "degraded_flags": cognitive_risks["conflict_snapshot"].get("degraded_flags", []),
                "tool_plan": structured_tool_plan,
                "escalation_required": esc.decision_type != "continue",
                "reasoning_depth": reasoning.reasoning_depth,
                "interaction_posture": reasoning.interaction_posture,
            }

        return {
            "current_reasoning_mode": "deliberate",
            "degraded_flags": cognitive_risks["conflict_snapshot"].get("degraded_flags", []),
            "tool_plan": [],
            "escalation_required": False,
        }

    def _phase_7_orchestrate_cognitive_tools(
        self,
        *,
        session: BrainSession,
        turn_id: str,
        metacognition: dict[str, Any],
    ) -> dict[str, Any]:
        """
        阶段 7：按元认知计划编排认知工具执行。

        Raises:
            PluginNotBoundError: 当认知工具注册中心缺失时抛出。
            RuntimeError: 当运行时未附着 Transcript 存储时抛出。
        """
        logger.debug("ThinkLoop phase 7 orchestrate_cognitive_tools session=%s", session.session_id)
        runtime = self._require_runtime(session)
        registry = getattr(runtime, "cognitive_tool_registry", None)
        if registry is None:
            raise PluginNotBoundError("Cognitive tool registry is not attached to the runtime")
        transcript_store = getattr(runtime, "transcript_store", None)
        if transcript_store is None:
            raise RuntimeError("transcript_store must be attached to runtime")

        tool_plan: list[dict[str, Any]] = metacognition.get("tool_plan", [])
        orchestrator = CognitiveToolOrchestrator(
            registry=registry,
            transcript_store=transcript_store,
            session_id=session.session_id,
            turn_id=turn_id,
        )
        context: dict[str, Any] = {
            "reasoning_mode": metacognition.get("current_reasoning_mode"),
            "task_description": metacognition.get("task_description"),
            "goal_stages": metacognition.get("goal_stages"),
            "candidate_paths": metacognition.get("candidate_paths", []),
            "state_flags": metacognition.get("state_flags", []),
            "requested_tool_ids": [
                item["plugin_id"]
                for item in tool_plan
                if isinstance(item, dict) and isinstance(item.get("plugin_id"), str)
            ],
            "requested_behavior_keys": [
                item["behavior_key"]
                for item in tool_plan
                if isinstance(item, dict) and isinstance(item.get("behavior_key"), str)
            ],
        }
        report = orchestrator.run(context)
        return {
            "selected_tools": report.selected_tools,
            "skipped_tools": report.skipped_tools,
            "parallel_groups": report.parallel_groups,
            "serial_groups": report.serial_groups,
            "invocations": [
                {
                    "invocation_id": invocation.invocation_id,
                    "tool_id": invocation.tool_id,
                    "phase": invocation.phase,
                    "status": invocation.status,
                    "trigger_matches": invocation.trigger_matches,
                    "started_at": invocation.started_at.isoformat(),
                    "finished_at": invocation.finished_at.isoformat(),
                }
                for invocation in report.invocations
            ],
            "merged_result": report.merged_result.model_dump(mode="json"),
        }

    def _phase_8_synthesize_decision(
        self,
        *,
        session: BrainSession,
        turn_id: str,
        metacognition: dict[str, Any],
        tool_invocations: list[dict[str, Any]],
        simulation: dict[str, Any],
        phase_trace_id: str,
        cold_start_protocol_applied: bool = False,
    ) -> dict[str, Any]:
        """
        阶段 8：汇总工具结果与模拟结果，发起决策合成类 LLM 调用。

        Args:
            phase_trace_id: 当前决策合成阶段的统一 trace 标识。
        """
        logger.debug("ThinkLoop phase 8 synthesize_decision session=%s", session.session_id)
        if cold_start_protocol_applied:
            return {
                "status": "ready",
                "summary": "cold-start onboarding completed from full nine-question inference",
                "action_intent": "stabilize_and_wait",
                "blockers": [],
                "confirmation_required": False,
            }
        provider = self._resolve_active_model_provider(session)
        prompt = (
                "Synthesize Zentex decision. Return JSON with keys status, summary, "
                "action_intent, blockers, confirmation_required."
            )
        context: dict[str, Any] = {
            "session_id": session.session_id,
            "reasoning_mode": metacognition.get("current_reasoning_mode"),
            "tool_invocations": tool_invocations.get("invocations", []),
            "cognitive_tool_context": tool_invocations.get("merged_result", {}),
            "simulation": simulation,
        }
        return self._invoke_model_provider(
            session=session,
            turn_id=turn_id,
            phase_name="phase_8_synthesize_decision",
            provider=provider,
            prompt=prompt,
            context=context,
            phase_trace_id=phase_trace_id,
            request_driver={
                "nine_question_inputs": [
                    "reasoning_mode",
                    "tool_invocations",
                    "simulation",
                ],
                "question_driver_refs": [
                    "我现在应该做什么",
                    "这样做会带来什么后果",
                    "我是否需要确认或重规划",
                ],
                "assembly_reason": "goal synthesis and current-turn decision generation",
            },
        )

    def _phase_9_consolidate(
        self,
        *,
        session: BrainSession,
        decision_summary: dict[str, Any],
        working_state: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段 9：整理反思记录与固化摘要，等待 Session 统一写盘。"""
        logger.debug("ThinkLoop phase 9 consolidate session=%s", session.session_id)
        return {
            "reflection_record": {
                "summary": "turn_ready_for_transcript",
                "decision_status": decision_summary.get("status"),
            },
            "consolidation": {
                "ready_for_transcript": True,
                "working_state_digest": {
                    "focus": working_state["working_memory"].get("current_focus_summary"),
                },
            },
        }

    def _resolve_active_model_provider(self, session: BrainSession) -> ModelProviderSpec | Any:
        """解析当前可用的激活态模型提供商插件。"""
        provider = self._resolve_active_managed_plugin(
            session,
            plugin_kind="model_provider",
        )
        if not hasattr(provider, "generate_json"):
            raise PluginNotBoundError("Resolved model provider does not implement generate_json")
        return provider

    def _resolve_active_managed_plugin(
        self,
        session: BrainSession,
        *,
        feature_key: str | None = None,
        plugin_kind: str | None = None,
    ) -> Any:
        """
        按功能键或插件类型解析当前激活版本。

        Raises:
            PluginNotBoundError: 当没有可用激活插件时抛出。
        """
        runtime = self._require_runtime(session)
        records = getattr(runtime, "managed_plugin_records", None)
        if not isinstance(records, dict):
            raise PluginNotBoundError("Managed plugin records are not attached to the runtime")

        candidates: list[Any] = []
        for record in records.values():
            plugin = getattr(record, "plugin", None)
            record_feature_key = getattr(record, "feature_code", None)
            if feature_key is not None and record_feature_key != feature_key:
                continue
            if plugin is None:
                continue
            if plugin_kind is not None and plugin.plugin_kind() != plugin_kind:
                continue
            if plugin.status != PluginLifecycleStatus.ACTIVE:
                continue
            # 为什么这里只接受 ACTIVE：溯源数据必须来自真实接管链路，不能混入候选态或
            # 已降级实例，否则“谁在调用”会和生产行为不一致。
            candidates.append(record)

        if not candidates:
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: {feature_key or plugin_kind or 'unknown'}"
            )
        candidates.sort(
            key=lambda record: (
                self._version_key(record.plugin.version),
                record.plugin.plugin_id,
            ),
            reverse=True,
        )
        return candidates[0].plugin

    def _resolve_simulation_plugin(self, session: BrainSession, *, target_domain: str) -> Any:
        """解析支持指定 domain 的激活态 simulation 插件。"""
        runtime = self._require_runtime(session)
        records = getattr(runtime, "managed_plugin_records", None)
        if not isinstance(records, dict):
            raise PluginNotBoundError("Managed plugin records are not attached to the runtime")

        candidates: list[Any] = []
        for record in records.values():
            plugin = getattr(record, "plugin", None)
            if plugin is None or plugin.plugin_kind() != "simulation_domain":
                continue
            if plugin.status != PluginLifecycleStatus.ACTIVE:
                continue
            supported_domains = getattr(plugin, "supported_domains", [])
            if target_domain not in supported_domains:
                continue
            candidates.append(record)

        if not candidates:
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: simulation:{target_domain}"
            )
        candidates.sort(
            key=lambda record: (
                self._version_key(record.plugin.version),
                record.plugin.plugin_id,
            ),
            reverse=True,
        )
        return candidates[0].plugin

    def _require_runtime(self, session: BrainSession) -> Any:
        """获取绑定在 session 上的运行时容器。"""
        runtime = getattr(session, "runtime", None)
        if runtime is None:
            raise PluginNotBoundError("BrainSession is not attached to a runtime container")
        return runtime

    def _next_turn_id(self, session: BrainSession) -> str:
        """生成单调递增的 turn 标识，便于审计与回放定位。"""
        return f"{session.session_id}-turn-{session.turn_counter + 1:04d}"

    def _session_snapshot_to_dict(self, snapshot: Any) -> dict[str, Any]:
        """把 session 快照转换为模型调用上下文所需的 dict。"""
        if hasattr(snapshot, "__dict__"):
            return self._json_safe(dict(vars(snapshot)))
        return {
            "session_id": getattr(snapshot, "session_id", None),
            "turn_count": getattr(snapshot, "turn_count", 0),
            "active_goal_titles": getattr(snapshot, "active_goal_titles", []),
            "current_focus_summary": getattr(snapshot, "current_focus_summary", None),
            "overdue_items": getattr(snapshot, "overdue_items", []),
            "current_reasoning_mode": getattr(snapshot, "current_reasoning_mode", None),
            "degraded_flags": getattr(snapshot, "degraded_flags", []),
            "last_turn_at": self._json_safe(getattr(snapshot, "last_turn_at", None)),
        }

    def _version_key(self, version: str) -> tuple[int, ...]:
        """把语义化版本字符串转换为可排序的整数元组。"""
        parts: list[int] = []
        for chunk in version.split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    def _invoke_model_provider(
        self,
        *,
        session: BrainSession,
        turn_id: str,
        phase_name: str,
        phase_trace_id: str,
        provider: ModelProviderSpec | Any,
        prompt: str,
        context: dict[str, Any],
        request_driver: dict[str, Any],
    ) -> dict[str, Any]:
        """
        统一执行模型提供商调用，并写入完整的溯源 Transcript 事件。

        Args:
            session: 当前会话。
            turn_id: 当前轮次标识。
            phase_name: 触发调用的 ThinkLoop 阶段名。
            phase_trace_id: 当前阶段的统一追踪标识。
            provider: 已解析的模型提供商插件。
            prompt: 发送给模型的提示词。
            context: 发送给模型的业务上下文。
            request_driver: 当前调用由哪些九问输入与问题驱动。

        Returns:
            dict[str, Any]: 结构化模型返回结果。

        Raises:
            Exception: 透传底层 provider 的原始异常，保持 fail-closed。
        """
        request_id = str(uuid4())
        decision_id = f"{turn_id}:{phase_name}"
        transcript_store = getattr(self._require_runtime(session), "transcript_store", None)
        timestamp = datetime.now(timezone.utc)
        provider_model = getattr(provider, "default_model", None)
        translated_context: dict[str, Any] = self._translate_model_context(context)
        translated_request_driver: dict[str, Any] = self._translate_request_driver(request_driver)
        humanized_phase_name: str = self._humanize_phase_name(phase_name)
        caller_context = ModelProviderCallerContext(
            source_module="Main reasoning loop",
            invocation_phase=humanized_phase_name,
            question_driver_refs=list(request_driver.get("question_driver_refs", [])),
            decision_id=decision_id,
        )
        trace_chain: dict[str, Any] = {
            "trace_id": phase_trace_id,
            "source_module": "Main reasoning loop",
            "phase_name": humanized_phase_name,
            "raw_phase_name": phase_name,
            "decision_id": decision_id,
            "question_driver_refs": list(request_driver.get("question_driver_refs", [])),
            "request_id": request_id,
        }

        if transcript_store is not None:
            # 为什么这里把模型请求事件写成 phase_trace_id：前端需要从 phase 事件直接跳到
            # 模型调用，不允许再额外猜测 request_id 和阶段之间的关系。
            transcript_store.write_entry(
                session_id=session.session_id,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
                timestamp=timestamp,
                source="think_loop.model_provider",
                trace_id=phase_trace_id,
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "phase_name": phase_name,
                    "provider_plugin_id": getattr(provider, "plugin_id", "unknown"),
                    "provider_name": getattr(provider, "provider_name", "unknown"),
                    "model": provider_model,
                    "prompt": prompt,
                    "context": self._json_safe(translated_context),
                    "caller_context": caller_context.model_dump(mode="json"),
                    "request_driver": self._json_safe(translated_request_driver),
                    "trace_chain": trace_chain,
                },
            )
        try:
            response = provider.generate_json(
                prompt=prompt,
                context=translated_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            if transcript_store is not None:
                transcript_store.write_entry(
                    session_id=session.session_id,
                    turn_id=turn_id,
                    entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_FAILED,
                    timestamp=datetime.now(timezone.utc),
                    source="think_loop.model_provider",
                    trace_id=phase_trace_id,
                    payload={
                        "request_id": request_id,
                        "decision_id": decision_id,
                        "phase_name": phase_name,
                        "provider_plugin_id": getattr(provider, "plugin_id", "unknown"),
                        "provider_name": getattr(provider, "provider_name", "unknown"),
                        "model": provider_model,
                        "caller_context": caller_context.model_dump(mode="json"),
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                        "request_driver": self._json_safe(translated_request_driver),
                        "trace_chain": trace_chain,
                        "thought_trace": {
                            "phase_name": humanized_phase_name,
                            "failed_after_request_write": True,
                        },
                    },
                )
            raise

        if transcript_store is not None:
            transcript_store.write_entry(
                session_id=session.session_id,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
                timestamp=datetime.now(timezone.utc),
                source="think_loop.model_provider",
                trace_id=phase_trace_id,
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "phase_name": phase_name,
                    "provider_plugin_id": getattr(provider, "plugin_id", "unknown"),
                    "provider_name": getattr(provider, "provider_name", "unknown"),
                    "model": provider_model,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": self._json_safe(response),
                    "request_driver": self._json_safe(translated_request_driver),
                    "trace_chain": trace_chain,
                },
            )
        return response

    def _build_phase_trace_ids(self, turn_id: str) -> dict[str, str]:
        """为需要单独溯源的关键 phase 生成稳定 trace。"""
        return {
            "context_snapshot": f"{turn_id}:phase_2_frame",
            "decision": f"{turn_id}:phase_8_synthesize_decision",
        }

    def _translate_model_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        把内部运行时上下文翻译为面向模型的稳定语义键。

        为什么要做这一层：Zentex 内部字段名带有大量工程约束和实现细节，
        直接暴露给模型既降低理解质量，也会把内部抽象穿透到外部语义层。
        """
        translated: dict[str, Any] = {}
        key_map: dict[str, str] = {
            "session_id": "conversation_reference",
            "workspace": "current_workspace",
            "session_snapshot": "current_conversation_state",
            "environment_event": "observed_environment_signal",
            "previous_snapshots": "recent_internal_state",
            "reasoning_mode": "current_reasoning_style",
            "tool_invocations": "internal_tool_findings",
            "cognitive_tool_context": "merged_tool_observations",
            "simulation": "counterfactual_review",
            "context_snapshot": "current_situation_summary",
            "conflict_snapshot": "current_conflict_observations",
        }
        for key, value in context.items():
            translated_key = key_map.get(key, self._humanize_token(key))
            translated[translated_key] = self._translate_model_value(key, value)
        return translated

    def _translate_request_driver(self, request_driver: dict[str, Any]) -> dict[str, Any]:
        """
        把九问驱动信息规整为可落盘、可展示的结构。

        这里保留“由哪几问驱动”的业务语义，但不把内部组装字段原样送给模型。
        """
        return {
            "question_inputs": [
                self._humanize_token(str(item))
                for item in request_driver.get("nine_question_inputs", [])
            ],
            "question_driver_refs": [
                str(item) for item in request_driver.get("question_driver_refs", [])
            ],
            "assembly_reason": self._humanize_token(
                str(request_driver.get("assembly_reason", "reasoning support"))
            ),
        }

    def _translate_model_value(self, key: str, value: Any) -> Any:
        """
        对特殊上下文字段做语义化翻译，避免直接暴露内部命名。

        Args:
            key: 原始上下文字段名。
            value: 原始上下文字段值。
        """
        if key == "reasoning_mode" and isinstance(value, str):
            return self._humanize_token(value)
        if key == "previous_snapshots" and isinstance(value, dict):
            return {
                "working memory": self._json_safe(value.get("working_memory")),
                "metacognition": self._json_safe(value.get("metacognition")),
                "conflict awareness": self._json_safe(value.get("conflict_snapshot")),
            }
        if key == "simulation" and isinstance(value, dict):
            return {
                "simulated consequences": self._json_safe(value.get("counterfactual_simulation")),
                "stakeholder expectations": self._json_safe(value.get("interaction_mind")),
            }
        return self._json_safe(value)

    def _humanize_phase_name(self, phase_name: str) -> str:
        """把 phase 标识转换为更易读的自然语言描述。"""
        mapping = {
            "phase_2_frame": "framing the situation",
            "phase_8_synthesize_decision": "synthesizing the current decision",
        }
        return mapping.get(phase_name, self._humanize_token(phase_name))

    def _humanize_token(self, token: str) -> str:
        """将下划线/短横线命名转为可读文本。"""
        return token.replace("_", " ").replace("-", " ").strip()

    def _json_safe(self, value: Any) -> Any:
        """把运行时对象转换为可安全序列化的 JSON 结构。"""
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        # Skip unit test Mocks to avoid infinite recursion through __dict__
        if "mock" in type(value).__name__.lower():
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return self._json_safe(value.model_dump(mode="json"))
        if hasattr(value, "__dict__"):
            return self._json_safe(vars(value))
        return str(value)


__all__ = ["BrainTurnResult", "ThinkLoop"]
