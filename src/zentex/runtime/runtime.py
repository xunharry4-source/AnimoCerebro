from __future__ import annotations

"""
BrainRuntime / 运行时大管家

EN:
BrainRuntime is the process-level dependency injection and assembly container.
It is responsible for mounting shared tools and shared stores.

ZH:
BrainRuntime（运行时大管家）：纯进程级的依赖注入与装配容器，负责挂载工具和
存储。
"""

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from plugins.provider_tools import build_default_provider_tools
from zentex.core.models import BrainRuntimeState
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.runtime.nine_questions.router import NineQuestionRouter, build_event
from zentex.runtime.nine_questions.state import NineQuestionState
from zentex.runtime.nine_questions.executor import NineQuestionExecutor
from zentex.common.state import SharedStateStore
from zentex.common.locking import get_lock_for_resource


class BrainRuntime:
    """
    Process-level container for shared stores, tools, and cognitive organs.

    Responsibilities:
    - assemble shared runtime-wide objects
    - manage lifecycle of active BrainSession instances
    - expose a unified runtime state projection

    Explicitly out of scope:
    - single-turn reasoning
    - model invocation
    - tool execution planning
    """

    @classmethod
    def build_runtime_with_default_llm(
        cls,
        *,
        runtime_id: str | None = None,
        default_workspace: str | None = None,
        llm_tool_name: str = "openai_compat",
        **kwargs: Any,
    ) -> "BrainRuntime":
        """
        Build a runtime pre-wired with the default LLM tool from provider config.

        This is the default assembly entrypoint for environments that want a
        ready-to-run runtime without manually threading the LLM dependency
        through each layer.
        """

        llm_tool = build_default_provider_tools()[llm_tool_name]
        return cls(
            runtime_id=runtime_id,
            default_workspace=default_workspace,
            llm_tool=llm_tool,
            **kwargs,
        )

    def __init__(
        self,
        *,
        runtime_id: str | None = None,
        default_workspace: str | None = None,
        transcript_store: BrainTranscriptStore | None = None,
        reflection_store: Any = None,
        runtime_memory_store: Any = None,
        identity_store: Any = None,
        tool_registry: Any = None,
        llm_tool: Any = None,
        identity_kernel_ref: str | None = None,
        tool_registry_version: str | None = None,
        read_only_mode: bool = False,
        degraded_mode: bool = False,
        manual_confirmation_required: bool = False,
        working_memory_controller: Any = None,
        temporal_engine: Any = None,
        living_self_model_engine: Any = None,
        metacognition_controller: Any = None,
        conflict_engine: Any = None,
        counterfactual_engine: Any = None,
        simulation_engine: Any = None,
        interaction_mind_engine: Any = None,
        consolidation_engine: Any = None,
    ) -> None:
        self.runtime_id = runtime_id or f"runtime-{uuid4()}"
        self.started_at = datetime.now(timezone.utc)
        self.default_workspace = default_workspace
        self.identity_kernel_ref = identity_kernel_ref
        self.tool_registry_version = tool_registry_version
        self.read_only_mode = read_only_mode
        self.degraded_mode = degraded_mode
        self.manual_confirmation_required = manual_confirmation_required
        self.last_runtime_snapshot_at: datetime | None = None

        self.runtime_memory_store = runtime_memory_store
        self.transcript_store = transcript_store or self._build_default_transcript_store()
        self.reflection_store = reflection_store
        self.identity_store = identity_store
        self._attach_runtime_memory_listener()

        self.tool_registry = tool_registry
        self.llm_tool = llm_tool

        self.working_memory_controller = working_memory_controller
        self.temporal_engine = temporal_engine
        self.living_self_model_engine = living_self_model_engine
        self.metacognition_controller = metacognition_controller
        self.conflict_engine = conflict_engine
        self.counterfactual_engine = counterfactual_engine
        self.simulation_engine = simulation_engine
        self.interaction_mind_engine = interaction_mind_engine
        self.consolidation_engine = consolidation_engine

        # Cluster-friendly shared state
        self._shared_sessions = SharedStateStore(f"{self.runtime_id}:sessions")
        # Keep local _sessions for object-level reference (caching), 
        # but source from shared state.
        self._sessions: dict[str, BrainSession] = {}
        self.active_session: BrainSession | None = None

        # Manual intervention control-plane state (used by ThinkLoop gating).
        self.intervention_state: dict[str, Any] | None = None
        self._priority_intervention_memory: dict[str, Any] | None = None
        self._shared_intervention_receipts = SharedStateStore(f"{self.runtime_id}:interventions")

        # Session-local nine-question snapshot cache (shared by default session).
        # Note: In a real cluster, the NineQuestionState itself needs a centralized version/sync.
        self.nine_question_state = NineQuestionState()
        self.nine_question_router = NineQuestionRouter()
        self.nine_question_bootstrap_status = "idle"
        self.nine_question_bootstrap_trace_id: str | None = None
        self.nine_question_bootstrap_error: str | None = None
        self._nine_question_bootstrap_lock = get_lock_for_resource(f"{self.runtime_id}:nq_bootstrap")

    def create_session(self, session_id: str) -> Any:
        from zentex.runtime.session import BrainSession

        session = BrainSession(
            session_id=session_id,
            store=self.transcript_store,
            runtime=self,
        )
        # Ensure session reads the canonical cache instance (hot-path read-only).
        session.current_nine_question_state = self.nine_question_state
        
        self._sessions[session_id] = session
        # Persist session metadata to shared store
        self._shared_sessions.set(session_id, {"session_id": session_id, "created_at": datetime.now(timezone.utc).isoformat()})
        
        if self.active_session is None:
            self.active_session = session
        return session

    def get_session(self, session_id: str) -> Any:
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        # Check if it exists in shared state (maybe created by another node)
        metadata = self._shared_sessions.get(session_id)
        if metadata:
            # Reconstruct session shell on this node
            return self.create_session(session_id)
            
        raise KeyError(f"Unknown session_id: {session_id}")

    def get_runtime_state(self) -> BrainRuntimeState:
        snapshot_at = datetime.now(timezone.utc)
        self.last_runtime_snapshot_at = snapshot_at
        
        # Get session IDs from shared store for cluster-wide visibility
        all_sessions = self._shared_sessions.list_all()
        
        return BrainRuntimeState(
            runtime_id=self.runtime_id,
            started_at=self.started_at,
            active_session_ids=sorted(all_sessions.keys()),
            default_workspace=self.default_workspace,
            identity_kernel_ref=self.identity_kernel_ref,
            tool_registry_version=self.tool_registry_version,
            transcript_store_status=self._derive_transcript_store_status(),
            memory_store_status=self._derive_memory_store_status(),
            read_only_mode=self.read_only_mode,
            degraded_mode=self.degraded_mode,
            manual_confirmation_required=self.manual_confirmation_required,
            last_runtime_snapshot_at=snapshot_at,
        )

    def set_nine_question_bootstrap_status(
        self,
        status: str,
        *,
        trace_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._nine_question_bootstrap_lock:
            self.nine_question_bootstrap_status = str(status)
            self.nine_question_bootstrap_trace_id = trace_id
            self.nine_question_bootstrap_error = error

    def get_nine_question_bootstrap_status(self) -> dict[str, str | None]:
        with self._nine_question_bootstrap_lock:
            return {
                "status": self.nine_question_bootstrap_status,
                "trace_id": self.nine_question_bootstrap_trace_id,
                "error": self.nine_question_bootstrap_error,
            }

    def _build_default_transcript_store(self) -> BrainTranscriptStore:
        runtime_root = Path(self.default_workspace or ".")
        transcript_path = runtime_root / ".zentex" / "runtime" / "brain_transcript.jsonl"
        return BrainTranscriptStore(transcript_path)

    def _attach_runtime_memory_listener(self) -> None:
        """
        Wire enhanced memory projection onto the canonical transcript stream.

        The transcript remains the source of truth. Enhanced memory receives a
        best-effort projection only when the runtime memory store explicitly
        exposes an `ingest_transcript_entry` method.
        """
        listener = getattr(self.runtime_memory_store, "ingest_transcript_entry", None)
        if callable(listener):
            self.transcript_store.register_entry_listener(listener)

    def _derive_transcript_store_status(self) -> str:
        if self.transcript_store is None:
            return "missing"
        if self.read_only_mode:
            return "attached_read_only"
        return "ready"

    def _derive_memory_store_status(self) -> str:
        if self.runtime_memory_store is None:
            return "not_configured"
        if self.degraded_mode:
            return "degraded"
        return "ready"

    def refresh_nine_question_state(
        self,
        *,
        question_driver_refs: list[str],
        refresh_reason: str,
        context_snapshot: dict[str, Any],
        active_constraints: list[Any],
    ) -> None:
        self.nine_question_state.question_driver_refs = list(question_driver_refs)
        self.nine_question_state.revision += 1
        self.nine_question_state.last_refresh_reason = str(refresh_reason)
        self.nine_question_state.refreshed_at = datetime.now(timezone.utc)
        if isinstance(context_snapshot, dict):
            self.nine_question_state.current_context.update(context_snapshot)
            role = context_snapshot.get("role_hypothesis")
            if isinstance(role, str) and role.strip():
                self.nine_question_state.current_role_hypothesis = role
        self.nine_question_state.active_constraints = list(active_constraints)

    def request_intervention(
        self,
        *,
        action: str,
        operator_id: str,
        reason: str,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        phase_name: str,
        manual_context_patch: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not action or not action.strip():
            raise ValueError("intervention action must not be empty")
        if not operator_id or not operator_id.strip():
            raise ValueError("operator_id must not be empty")
        if not reason or not reason.strip():
            raise ValueError("reason must not be empty")
        if not phase_name or not phase_name.strip():
            raise ValueError("phase_name must not be empty")

        patch = manual_context_patch or {}
        timestamp = datetime.now(timezone.utc).isoformat()

        state = {
            "mode": "manual",
            "paused": action == "pause",
            "target_phase": phase_name,
            "operator_id": operator_id,
            "reason": reason,
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
            "manual_context_patch": patch,
            "last_action": action,
            "updated_at": timestamp,
        }
        self.intervention_state = dict(state)

        # Highest priority intervention memory is consumed by the next guarded model call.
        must_apply = action in {"role_change", "reject_action", "manual_confirm"}
        self._priority_intervention_memory = {
            "trace_id": str(trace_id or f"intervention:{action}"),
            "idempotency_key": idempotency_key,
            "action": action,
            "operator_id": operator_id,
            "reason": reason,
            "manual_context_patch": patch,
            "priority": "highest",
            "must_apply_to_next_model_call": must_apply,
            "target_phase": phase_name,
            "nine_question_state": {
                "question_driver_refs": list(self.nine_question_state.question_driver_refs),
                "revision": self.nine_question_state.revision,
                "last_refresh_reason": self.nine_question_state.last_refresh_reason,
                "refreshed_at": self.nine_question_state.refreshed_at.isoformat(),
                "current_role_hypothesis": self.nine_question_state.current_role_hypothesis,
                "operator_patch": dict(self.nine_question_state.operator_patch),
            },
        }

        # Apply the patch to the runtime nine-question state immediately (fail-closed: no silent merge).
        self.nine_question_state.revision += 1
        self.nine_question_state.last_refresh_reason = f"manual_intervention:{action}"
        self.nine_question_state.refreshed_at = datetime.now(timezone.utc)
        if "role_hint" in patch and isinstance(patch.get("role_hint"), str) and patch["role_hint"].strip():
            self.nine_question_state.current_role_hypothesis = str(patch["role_hint"])
        self.nine_question_state.operator_patch.update(patch)
        if phase_name == "phase_2_frame":
            self.nine_question_state.question_driver_refs = [
                "我是谁",
                "我现在在哪个情境里",
                "我受到哪些约束",
                "我现在应该优先想什么",
            ]

        # Update the intervention snapshot copy with the post-apply nine-question state.
        if self._priority_intervention_memory is not None:
            self._priority_intervention_memory["nine_question_state"] = {
                "question_driver_refs": list(self.nine_question_state.question_driver_refs),
                "revision": self.nine_question_state.revision,
                "last_refresh_reason": self.nine_question_state.last_refresh_reason,
                "refreshed_at": self.nine_question_state.refreshed_at.isoformat(),
                "current_role_hypothesis": self.nine_question_state.current_role_hypothesis,
                "operator_patch": dict(self.nine_question_state.operator_patch),
            }

        # Mark impacted questions dirty and enqueue for independent recomputation.
        dirty_questions = self.nine_question_router.derive_dirty_questions_for_event(
            "manual_intervention",
            action=action,
        )
        self.nine_question_router.publish(
            self.nine_question_state,
            build_event(
                event_type="manual_intervention",
                reason=f"manual_intervention:{action}",
                trace_id=str(trace_id or f"intervention:{action}"),
                dirty_questions=dirty_questions,
                payload={
                    "action": action,
                    "operator_id": operator_id,
                    "reason": reason,
                    "phase_name": phase_name,
                    "idempotency_key": idempotency_key,
                },
            ),
        )

        return state

    def get_intervention_receipt(self, idempotency_key: str) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        receipt = self._shared_intervention_receipts.get(idempotency_key)
        if receipt is None:
            return None
        return dict(receipt)

    def store_intervention_receipt(self, idempotency_key: str, receipt: dict[str, Any]) -> None:
        if not idempotency_key:
            raise ValueError("idempotency_key must not be empty")
        self._shared_intervention_receipts.set(idempotency_key, dict(receipt))

    def build_priority_intervention_working_memory(self) -> dict[str, Any]:
        memory = self.peek_priority_intervention_memory()
        if not isinstance(memory, dict):
            return {"must_apply_to_next_model_call": False}
        return {
            "must_apply_to_next_model_call": bool(memory.get("must_apply_to_next_model_call")),
            "action": memory.get("action"),
            "reason": memory.get("reason"),
            "operator_id": memory.get("operator_id"),
            "manual_context_patch": memory.get("manual_context_patch"),
            "target_phase": memory.get("target_phase"),
            "trace_id": memory.get("trace_id"),
        }

    def peek_priority_intervention_memory(self) -> dict[str, Any]:
        if self._priority_intervention_memory is None:
            return {"must_apply_to_next_model_call": False}
        return dict(self._priority_intervention_memory)

    def mark_priority_intervention_applied(self) -> None:
        if self._priority_intervention_memory is None:
            return
        self._priority_intervention_memory["must_apply_to_next_model_call"] = False

    def process_nine_question_events(
        self,
        *,
        session: Any | None = None,
        turn_id: str | None = None,
    ) -> None:
        """
        Execute queued nine-question events (deep path).

        Hot paths should only publish events / mark dirty; they must NOT call this.
        """
        target_session = session or self.active_session
        if target_session is None:
            raise RuntimeError("No active session is attached to the runtime")
        registry = getattr(self, "cognitive_tool_registry", None)
        if registry is None:
            raise RuntimeError("cognitive_tool_registry is not attached to the runtime")
        executor = NineQuestionExecutor(registry=registry, transcript_store=self.transcript_store)
        state = getattr(target_session, "current_nine_question_state", self.nine_question_state)
        for event in self.nine_question_router.drain():
            pending = [qid for qid in event.dirty_questions if state.is_dirty(qid)]
            if not pending:
                continue
            executor.run_questions(
                runtime=self,
                session=target_session,
                state=state,
                question_ids=pending,
                trace_id=event.trace_id,
                refresh_reason=event.reason,
                driver_refs=[event.reason],
                turn_id=turn_id or f"nine-question:{event.trace_id}",
            )
