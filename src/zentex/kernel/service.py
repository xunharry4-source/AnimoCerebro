from __future__ import annotations
"""
Public service boundary for zentex.kernel.

All external modules (launcher, web_console, etc.) MUST interact with the
kernel exclusively through this file. Internal subdomains are not part of
the public API.

External module services are injected via attach_dependencies() — kernel
never imports external service modules directly.
"""


import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Optional, Union, Optional, Union, Dict, List
from uuid import uuid4

logger = logging.getLogger(__name__)

from zentex.common.storage_paths import get_storage_paths
from zentex.foundation.contracts import (
    PhaseResult,
    ServiceResponse,
    TurnRequest,
    TurnResult,
    TurnStatus,
)
from zentex.foundation.meta import (
    NINE_QUESTION_COUNT,
    SESSION_DEFAULT_TIMEOUT_SECONDS,
    WORKING_MEMORY_MAX_SLOTS,
)
from zentex.kernel.cognition_flow import (
    BootstrapStatus,
    DEFAULT_NINE_QUESTIONS,
    NineQuestion,
    NineQuestionExecutor,
    NineQuestionResponse,
    NineQuestionRouter,
    NineQuestionStartupCoordinator,
    NineQuestionState,
    NineQuestionStateManager,
    StartupSnapshotBuilder,
)
from zentex.kernel.flow_domain import (
    KernelServiceBridge,
    PhaseRegistry,
    ThinkLoop,
    TurnProtocol,
    TurnResultBuilder,
)
from zentex.kernel.session_domain import (
    KernelSession,
    SessionLifecycleManager,
    SessionRegistry,
)
from zentex.kernel.state_domain import (
    CognitiveTemporalEngine,
    NullTranscriptStore,
    SelfModelEngine,
    MetaCognitionController,
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
    WorkingMemoryController,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType
from zentex.safety.conflict_engine import CognitiveConflictEngine
from zentex.nine_questions.query import build_question_record

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Internal per-session state container
# ---------------------------------------------------------------------------

class _SessionState:
    """Holds all state-domain objects for a single session."""

    def __init__(
        self,
        session_id: str,
        db_dir: str,
        *,
        entry_listeners: list[Callable[[Any], Optional[None]]] | None = None,
    ) -> None:
        self.session_id = session_id
        self.working_memory = WorkingMemoryController(max_slots=WORKING_MEMORY_MAX_SLOTS)
        self.self_model = SelfModelEngine(session_id=session_id)
        self.meta_cognition = MetaCognitionController(session_id=session_id)
        self.temporal = CognitiveTemporalEngine(session_id=session_id)
        self.conflict_engine = CognitiveConflictEngine(brain_scope=session_id)
        transcript_enabled = str(os.environ.get("ZENTEX_ENABLE_TRANSCRIPTS", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if transcript_enabled:
            self.transcript = TranscriptStore(
                session_id=session_id,
                db_dir=db_dir,
                entry_listeners=entry_listeners or [],
            )
        else:
            self.transcript = NullTranscriptStore(session_id=session_id)


# ---------------------------------------------------------------------------
# KernelService — implements KernelServiceBridge
# ---------------------------------------------------------------------------

class KernelService:
    """Central kernel service. Implements KernelServiceBridge so it can be
    passed directly to ThinkLoop and other internal components."""

    def __init__(
        self,
        transcript_db_dir: Optional[str] = None,
        system_identity_store: Any = None,
    ) -> None:
        # --- infrastructure ---
        self._transcript_db_dir = transcript_db_dir or str(get_storage_paths().transcript_dir)
        self._lock = threading.Lock()

        # --- session management ---
        self._lifecycle = SessionLifecycleManager()
        self._registry = SessionRegistry(self._lifecycle)

        # --- per-session state ---
        self._session_states: dict[str, _SessionState] = {}
        self._transcript_entry_listeners: dict[str, Callable[[Any], Optional[None]]] = {}

        # --- flow components ---
        self._phase_registry = PhaseRegistry()
        self._think_loop = ThinkLoop(bridge=self, registry=self._phase_registry)  # type: ignore[arg-type]
        self._turn_protocol = TurnProtocol(bridge=self, think_loop=self._think_loop)  # type: ignore[arg-type]

        # --- nine-question components (shared baseline) ---
        # NOTE: Cognitive baseline (Nine-Questions) is now GLOBAL and shared across all sessions.
        # Partitioning by Session ID was an architectural error that led to identity fragmentation.
        self._nq_shared_state = NineQuestionStateManager(session_id="zentex-global-baseline")
        self._nq_shared_lock = threading.Lock()
        self._nq_router = NineQuestionRouter()
        self._nq_executor = NineQuestionExecutor(bridge=self)
        self._nq_snapshot_builder = StartupSnapshotBuilder(bridge=self)
        self._nq_coordinator = NineQuestionStartupCoordinator(
            router=self._nq_router,
            executor=self._nq_executor,
            snapshot_builder=self._nq_snapshot_builder,
        )

        # --- injected external services (all optional until attached) ---
        self._environment_service: Any = None
        self._cognition_service: Any = None
        self._safety_service: Any = None
        self._plugins_service: Any = None
        self._memory_service: Any = None
        self._audit_service: Any = None
        self._llm_service: Any = None
        self._foundation_service: Any = None
        self._agent_service: Any = None
        self._cli_service: Any = None
        self._mcp_service: Any = None
        self._external_connector_service: Any = None
        self._nq_plugin_service: Any = None
        self._reflection_service: Any = None
        self._learning_service: Any = None
        self._task_service: Any = None
        self._system_identity_store: Any = system_identity_store
        self._brain_daemon: Any = None

        self._initialized = True

    def _create_session_state(self, session_id: str) -> _SessionState:
        return _SessionState(
            session_id=session_id,
            db_dir=self._transcript_db_dir,
            entry_listeners=list(self._transcript_entry_listeners.values()),
        )

    def add_transcript_entry_listener(
        self,
        key: str,
        listener: Callable[[Any], Optional[None]],
    ) -> None:
        """Attach a transcript projection listener owned by an outer service."""
        if key in self._transcript_entry_listeners:
            return
        self._transcript_entry_listeners[key] = listener
        for state in self._session_states.values():
            store = getattr(state, "transcript", None)
            add_listener = getattr(store, "add_entry_listener", None)
            if callable(add_listener):
                add_listener(listener)

    # ------------------------------------------------------------------
    # Engine accessors (for web console / default session)
    # ------------------------------------------------------------------

    @property
    def temporal_engine(self) -> Any:
        """Return the temporal engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            # Try to force create it if possible, or return None
            try:
                state = self._create_session_state(default_session_id)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        return state.temporal

    @property
    def conflict_engine(self) -> Any:
        """Return the conflict engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = self._create_session_state(default_session_id)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        return state.conflict_engine

    def get_conflict_engine(self, session_id: str = "zentex-default-session") -> Any:
        """Return the conflict engine for a concrete session."""
        state = self._get_state(session_id)
        if state is None and session_id == self._DEFAULT_SESSION_ID:
            state = self._get_or_create_default_state()
        if state is None:
            raise KeyError(f"session state not found: {session_id}")
        return state.conflict_engine

    @property
    def simulation_engine(self) -> Any:
        """Return the counterfactual simulation engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = self._create_session_state(default_session_id)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        # Shim for simulation - in this version, it's provided by cognition_service 
        # but the router expects a stateful domain object. 
        return getattr(self._cognition_service, "simulation_engine", None)

    @property
    def interaction_mind_engine(self) -> Any:
        """Return the interaction mind engine for the default session."""
        return getattr(self._cognition_service, "interaction_mind_engine", None)

    @property
    def consolidation_engine(self) -> Any:
        """Return the memory consolidation engine."""
        return getattr(self._memory_service, "consolidation_engine", None)

    @property
    def transcript_store(self) -> Any:
        """Return the transcript store for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = self._create_session_state(default_session_id)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        return state.transcript

    def get_nine_question_audit_store(self, session_id: str) -> None:
        """Nine-question side audit stores are forbidden; use the canonical session transcript."""
        return None

    # ------------------------------------------------------------------
    # Dependency injection (called by launcher)
    # ------------------------------------------------------------------

    def attach_dependencies(
        self,
        *,
        environment_service: Any = None,
        cognition_service: Any = None,
        safety_service: Any = None,
        plugins_service: Any = None,
        memory_service: Any = None,
        audit_service: Any = None,
        llm_service: Any = None,
        foundation_service: Any = None,
        agent_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        reflection_service: Any = None,
        learning_service: Any = None,
        task_service: Any = None,
        system_identity_store: Any = None,
    ) -> None:
        """Inject all external service references.

        Called by launcher.assembly.assembler after all services are initialised.
        Kernel never imports these services directly — they are always injected.
        """
        if environment_service is not None:
            self._environment_service = environment_service
        if cognition_service is not None:
            self._cognition_service = cognition_service
        if safety_service is not None:
            self._safety_service = safety_service
        if plugins_service is not None:
            self._plugins_service = plugins_service
        if memory_service is not None:
            self._memory_service = memory_service
        if audit_service is not None:
            self._audit_service = audit_service
        if llm_service is not None:
            self._llm_service = llm_service
        if foundation_service is not None:
            self._foundation_service = foundation_service
        if agent_service is not None:
            self._agent_service = agent_service
        if cli_service is not None:
            self._cli_service = cli_service
        if mcp_service is not None:
            self._mcp_service = mcp_service
        if external_connector_service is not None:
            self._external_connector_service = external_connector_service
        if reflection_service is not None:
            self._reflection_service = reflection_service
        if learning_service is not None:
            self._learning_service = learning_service
        if task_service is not None:
            self._task_service = task_service
        if system_identity_store is not None:
            self._system_identity_store = system_identity_store

        # Initialize Nine-Question implementation service
        if plugins_service is not None:
            # Wire up cognitive services for authentic plugin integration
            if callable(getattr(plugins_service, "attach_cognitive_services", None)):
                plugins_service.attach_cognitive_services(
                    audit_service=self._audit_service,
                    memory_service=self._memory_service,
                    reflection_service=self._reflection_service,
                    learning_service=self._learning_service,
                    transcript_store=self.transcript_store,
                    llm_service=self._llm_service,
                    foundation_service=self._foundation_service,
                    environment_service=self._environment_service,
                )

            try:
                from zentex.plugins.service import get_nq_service as get_nq_plugin_service
                self._nq_plugin_service = get_nq_plugin_service(plugins_service=plugins_service)
            except ImportError:
                logger.warning("Could not initialize NineQuestionPluginService: module not found")

    # ------------------------------------------------------------------
    # Session management (public API)
    # ------------------------------------------------------------------

    def create_session(self, user_id: str = "") -> str:
        """Create a new session and return its session_id."""
        session = self._lifecycle.create_session(user_id=user_id)
        state = self._create_session_state(session.session_id)
        with self._lock:
            self._session_states[session.session_id] = state
        return session.session_id

    def get_session_meta(self, session_id: str) -> Optional[dict]:
        """Return session metadata dict, or None if not found."""
        session = self._registry.get(session_id)
        if session is None:
            return None
        return session.to_snapshot()

    def suspend_session(self, session_id: str) -> bool:
        """Suspend a session. Returns False if not found."""
        result = self._lifecycle.suspend_session(session_id)
        if result:
            state = self._get_state(session_id)
            if state:
                state.transcript.append(TranscriptEntry(
                    entry_type=TranscriptEntryType.state_change,
                    session_id=session_id,
                    payload={"action": "suspended"},
                ))
        return result

    def terminate_session(self, session_id: str) -> bool:
        """Terminate and clean up a session. Returns False if not found."""
        result = self._lifecycle.terminate_session(session_id)
        if result:
            state = self._get_state(session_id)
            if state:
                state.transcript.append(TranscriptEntry(
                    entry_type=TranscriptEntryType.state_change,
                    session_id=session_id,
                    payload={"action": "terminated"},
                ))
                state.transcript.close()
            with self._lock:
                self._session_states.pop(session_id, None)
        return result

    def list_active_sessions(self) -> list[str]:
        """Return list of active/idle session IDs."""
        return [s.session_id for s in self._lifecycle.list_active_sessions()]

    def registry_health(self) -> dict:
        """Return session registry health summary."""
        return self._registry.health_summary()

    # ------------------------------------------------------------------
    # Turn execution (public API)
    # ------------------------------------------------------------------

    def start_turn(self, session_id: str, user_input: str, context: Optional[dict] = None) -> TurnResult:
        """Execute a full 9-phase turn for the given session.

        Returns a TurnResult. Raises ValueError if session not found.
        """
        session = self._registry.get(session_id)
        if session is None:
            raise ValueError(f"Session missing for: {session_id}")
        state = self._get_state(session_id)
        if state is None:
            raise ValueError(f"Session state missing for: {session_id}")

        base_context = context or {}
        # AUTHENTIC GROUNDING: Inject Nine-Question baseline into the turn context.
        # This ensures all Turn phases (Drive, Frame, Synthesis) are grounded in 
        # the established cognitive identity and boundaries.
        enriched_context = self._build_grounded_context(
            base_context=base_context,
            nine_question_state_payload=self._nq_shared_state.to_dict(),
            trigger="turn_start"
        )

        request = TurnRequest(
            turn_id=str(uuid4()),
            session_id=session_id,
            user_input=user_input,
            context=enriched_context,
        )

        state.working_memory.clear()

        result = self._turn_protocol.execute(
            request=request,
            session=session,
            transcript=state.transcript,
            working_memory=state.working_memory,
            self_model=state.self_model,
            temporal=state.temporal,
        )
        return result

    def update_working_memory_frame(
        self,
        *,
        session_id: str,
        tick_id: str,
        new_candidates: list[dict[str, Any]],
        attention_budget: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 52 entry point; business rules live in working_memory_runtime."""
        from zentex.kernel.working_memory_runtime import update_working_memory_frame

        return update_working_memory_frame(
            self,
            session_id=session_id,
            tick_id=tick_id,
            new_candidates=new_candidates,
            attention_budget=attention_budget,
            trace_id=trace_id,
        )

    def interrupt_working_memory_focus(
        self,
        *,
        session_id: str,
        tick_id: str,
        high_risk_item: dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 52 interrupt entry point; implementation is outside service.py."""
        from zentex.kernel.working_memory_runtime import interrupt_working_memory_focus

        return interrupt_working_memory_focus(
            self,
            session_id=session_id,
            tick_id=tick_id,
            high_risk_item=high_risk_item,
            trace_id=trace_id,
        )

    def resume_working_memory_focus(
        self,
        *,
        session_id: str,
        tick_id: str,
        focus_id: str,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 52 resume entry point; implementation is outside service.py."""
        from zentex.kernel.working_memory_runtime import resume_working_memory_focus

        return resume_working_memory_focus(
            self,
            session_id=session_id,
            tick_id=tick_id,
            focus_id=focus_id,
            trace_id=trace_id,
        )

    def mark_working_memory_considered(
        self,
        *,
        session_id: str,
        ref_id: str,
        tick_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 52 recently-considered entry point; implementation is outside service.py."""
        from zentex.kernel.working_memory_runtime import mark_working_memory_considered

        return mark_working_memory_considered(
            self,
            session_id=session_id,
            ref_id=ref_id,
            tick_id=tick_id,
            trace_id=trace_id,
        )

    def query_working_memory_frame(self, *, session_id: str) -> dict[str, Any]:
        """Feature 52 query entry point; implementation is outside service.py."""
        from zentex.kernel.working_memory_runtime import query_working_memory_frame

        return query_working_memory_frame(self, session_id=session_id)

    def update_living_self_model(
        self,
        *,
        session_id: str,
        turn_result: dict[str, Any],
        recent_events: Optional[list[dict[str, Any]]] = None,
        working_memory_frame: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 53 entry point; implementation is outside service.py."""
        from zentex.kernel.living_self_model_runtime import update_living_self_model

        return update_living_self_model(
            self,
            session_id=session_id,
            turn_result=turn_result,
            recent_events=recent_events,
            working_memory_frame=working_memory_frame,
            trace_id=trace_id,
        )

    def query_living_self_model(self, *, session_id: str) -> dict[str, Any]:
        """Feature 53 query entry point; implementation is outside service.py."""
        from zentex.kernel.living_self_model_runtime import query_living_self_model

        return query_living_self_model(self, session_id=session_id)

    def detect_living_self_weakness_patterns(
        self,
        *,
        session_id: str,
        recent_events: list[dict[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 53 weakness detection entry point; implementation is outside service.py."""
        from zentex.kernel.living_self_model_runtime import detect_living_self_weakness_patterns

        return detect_living_self_weakness_patterns(
            self,
            session_id=session_id,
            recent_events=recent_events,
            trace_id=trace_id,
        )

    def check_living_self_confidence_drift(
        self,
        *,
        session_id: str,
        statements: list[dict[str, Any]],
        evidence: Optional[Any] = None,
        threshold: float = 0.25,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 53 confidence drift entry point; implementation is outside service.py."""
        from zentex.kernel.living_self_model_runtime import check_living_self_confidence_drift

        return check_living_self_confidence_drift(
            self,
            session_id=session_id,
            statements=statements,
            evidence=evidence,
            threshold=threshold,
            trace_id=trace_id,
        )

    def apply_living_self_load_adjustment(
        self,
        *,
        session_id: str,
        working_memory_frame: dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 53 load adjustment entry point; implementation is outside service.py."""
        from zentex.kernel.living_self_model_runtime import apply_living_self_load_adjustment

        return apply_living_self_load_adjustment(
            self,
            session_id=session_id,
            working_memory_frame=working_memory_frame,
            trace_id=trace_id,
        )

    def decide_meta_cognition(
        self,
        *,
        session_id: str,
        wm_frame: dict[str, Any],
        self_model: dict[str, Any],
        budget: dict[str, Any],
        nine_q_state: dict[str, Any],
        agenda: list[dict[str, Any]] | dict[str, Any],
        tool_registry: list[dict[str, Any]] | dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 54 entry point; implementation is outside service.py."""
        from zentex.kernel.meta_cognition_runtime import decide_meta_cognition

        return decide_meta_cognition(
            self,
            session_id=session_id,
            wm_frame=wm_frame,
            self_model=self_model,
            budget=budget,
            nine_q_state=nine_q_state,
            agenda=agenda,
            tool_registry=tool_registry,
            trace_id=trace_id,
        )

    def query_meta_cognition_decision(self, *, session_id: str) -> dict[str, Any]:
        """Feature 54 query entry point; implementation is outside service.py."""
        from zentex.kernel.meta_cognition_runtime import query_meta_cognition_decision

        return query_meta_cognition_decision(self, session_id=session_id)

    def tick_temporal_agenda(
        self,
        *,
        session_id: str,
        current_time: str,
        agenda_items: list[dict[str, Any]],
        brain_scope: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 55 entry point; implementation is outside service.py."""
        from zentex.kernel.temporal_agenda_runtime import tick_temporal_agenda

        return tick_temporal_agenda(
            self,
            session_id=session_id,
            current_time=current_time,
            agenda_items=agenda_items,
            brain_scope=brain_scope,
            trace_id=trace_id,
        )

    def query_temporal_agenda_state(self, *, session_id: str) -> dict[str, Any]:
        """Feature 55 query entry point; implementation is outside service.py."""
        from zentex.kernel.temporal_agenda_runtime import query_temporal_agenda_state

        return query_temporal_agenda_state(self, session_id=session_id)

    def detect_cognitive_conflicts(
        self,
        *,
        session_id: str,
        working_memory: dict[str, Any],
        goals: Optional[list[dict[str, Any]]] = None,
        nine_q_state: Optional[dict[str, Any]] = None,
        memory_recalls: Optional[list[dict[str, Any]]] = None,
        budget: Optional[dict[str, Any]] = None,
        self_model: Optional[dict[str, Any]] = None,
        agenda: Optional[list[dict[str, Any]]] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Feature 56 entry point; implementation is outside service.py."""
        from zentex.kernel.cognitive_conflict_runtime import detect_cognitive_conflicts

        return detect_cognitive_conflicts(
            self,
            session_id=session_id,
            working_memory=working_memory,
            goals=goals,
            nine_q_state=nine_q_state,
            memory_recalls=memory_recalls,
            budget=budget,
            self_model=self_model,
            agenda=agenda,
            trace_id=trace_id,
        )

    def query_cognitive_conflicts(self, *, session_id: str) -> dict[str, Any]:
        """Feature 56 query entry point; implementation is outside service.py."""
        from zentex.kernel.cognitive_conflict_runtime import query_cognitive_conflicts

        return query_cognitive_conflicts(self, session_id=session_id)

    def consult_external_brain(
        self,
        *,
        session_id: str,
        user_input: str,
        context: Optional[dict] = None,
        turn_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """G1 external-brain consultation entry point.

        The business rules live in kernel.external_brain; this public service
        method only resolves kernel-owned dependencies and delegates.
        """
        from zentex.kernel.external_brain import consult_external_brain

        state = self._get_state(session_id)
        if state is None:
            raise ValueError(f"Session state missing for: {session_id}")
        return consult_external_brain(
            session_id=session_id,
            user_input=user_input,
            context=context,
            llm_service=self._llm_service,
            transcript_store=state.transcript,
            nine_question_state=self._nq_shared_state.to_dict(),
            system_identity=self.get_system_identity(),
            turn_id=turn_id,
            trace_id=trace_id,
        )

    def get_core_architecture_snapshot(self) -> dict[str, Any]:
        """Return the G2 core architecture snapshot; logic lives in kernel.architecture."""
        from zentex.kernel.architecture import build_core_architecture_snapshot

        return build_core_architecture_snapshot(self)

    def control_brain_daemon(
        self,
        *,
        action: str,
        session_id: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        max_consecutive_failures: Optional[int] = None,
        run_background: bool = False,
    ) -> dict[str, Any]:
        """Control the G3 BrainDaemon; state-machine logic lives in kernel.brain_daemon."""
        return self._get_brain_daemon().control(
            action=action,
            session_id=session_id,
            interval_seconds=interval_seconds,
            max_consecutive_failures=max_consecutive_failures,
            run_background=run_background,
        )

    def get_brain_daemon_status(self) -> dict[str, Any]:
        """Return the G3 BrainDaemon status; logic lives in kernel.brain_daemon."""
        return self._get_brain_daemon().status()

    def observe_environment_awareness(
        self,
        *,
        session_id: str,
        turn_id: Optional[str] = None,
        raw_signals: Optional[list[str]] = None,
        source_conflict_field: str = "memory_used_ratio",
        source_conflict_samples: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run G4 environment awareness; logic lives in kernel.environment_awareness."""
        from zentex.kernel.environment_awareness import observe_environment_awareness

        return observe_environment_awareness(
            self,
            session_id=session_id,
            turn_id=turn_id,
            raw_signals=raw_signals,
            source_conflict_field=source_conflict_field,
            source_conflict_samples=source_conflict_samples,
        )

    def query_environment_awareness_snapshots(
        self,
        *,
        session_id: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Query G4 environment snapshots; logic lives in kernel.environment_awareness."""
        from zentex.kernel.environment_awareness import query_environment_awareness_snapshots

        return query_environment_awareness_snapshots(
            self,
            session_id=session_id,
            limit=limit,
        )

    async def create_resource_negotiation_request(
        self,
        *,
        session_id: str,
        task_id: str,
        gap_type: str,
        required_asset: str,
        observed_error: str,
        recovery_conditions: list[str],
        task_context: Optional[dict[str, Any]] = None,
        proposed_tradeoff: Optional[str] = None,
        priority: int = 3,
    ) -> dict[str, Any]:
        """Create a G5 negotiation request; logic lives in kernel.resource_negotiation."""
        from zentex.kernel.resource_negotiation import create_resource_negotiation_request

        return await create_resource_negotiation_request(
            self,
            session_id=session_id,
            task_id=task_id,
            gap_type=gap_type,
            required_asset=required_asset,
            observed_error=observed_error,
            recovery_conditions=recovery_conditions,
            task_context=task_context,
            proposed_tradeoff=proposed_tradeoff,
            priority=priority,
        )

    def query_resource_negotiation_requests(
        self,
        *,
        session_id: str,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Query G5 negotiation requests; logic lives in kernel.resource_negotiation."""
        from zentex.kernel.resource_negotiation import query_resource_negotiation_requests

        return query_resource_negotiation_requests(
            self,
            session_id=session_id,
            task_id=task_id,
            status=status,
        )

    async def resolve_resource_negotiation_request(
        self,
        *,
        session_id: str,
        negotiation_id: str,
        approved: bool,
        resolution_note: str,
        granted_asset: Optional[str] = None,
    ) -> dict[str, Any]:
        """Resolve a G5 negotiation request; logic lives in kernel.resource_negotiation."""
        from zentex.kernel.resource_negotiation import resolve_resource_negotiation_request

        return await resolve_resource_negotiation_request(
            self,
            session_id=session_id,
            negotiation_id=negotiation_id,
            approved=approved,
            resolution_note=resolution_note,
            granted_asset=granted_asset,
        )

    def mount_identity_kernel(
        self,
        *,
        session_id: str,
        topics: Optional[list[str]] = None,
        risk_level: str = "low",
        identity_package: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Mount the G6 identity kernel; logic lives in kernel.identity_kernel."""
        from zentex.kernel.identity_kernel import mount_identity_kernel

        return mount_identity_kernel(
            self,
            session_id=session_id,
            topics=topics,
            risk_level=risk_level,
            identity_package=identity_package,
        )

    def query_identity_anchors(
        self,
        *,
        session_id: str,
        role: Optional[str] = None,
        risk_level: Optional[str] = None,
        topics: Optional[list[str]] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Query G6 identity anchors; logic lives in kernel.identity_kernel."""
        from zentex.kernel.identity_kernel import query_identity_anchors

        return query_identity_anchors(
            self,
            session_id=session_id,
            role=role,
            risk_level=risk_level,
            topics=topics,
            limit=limit,
        )

    def evaluate_identity_change(
        self,
        *,
        session_id: str,
        proposed_changes: dict[str, Any],
        human_confirmed: bool = False,
        reviewer: Optional[str] = None,
        drift_threshold: float = 0.34,
    ) -> dict[str, Any]:
        """Evaluate a G6 identity change; logic lives in kernel.identity_kernel."""
        from zentex.kernel.identity_kernel import evaluate_identity_change

        return evaluate_identity_change(
            self,
            session_id=session_id,
            proposed_changes=proposed_changes,
            human_confirmed=human_confirmed,
            reviewer=reviewer,
            drift_threshold=drift_threshold,
        )

    async def create_inter_agent_conflict(
        self,
        *,
        session_id: str,
        task_id: str,
        task_payload: dict[str, Any],
        required_capabilities: list[str],
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Create a G7 inter-agent conflict; logic lives in kernel.inter_agent."""
        from zentex.kernel.inter_agent import create_inter_agent_conflict

        return await create_inter_agent_conflict(
            self,
            session_id=session_id,
            task_id=task_id,
            task_payload=task_payload,
            required_capabilities=required_capabilities,
            timeout_seconds=timeout_seconds,
        )

    def query_inter_agent_conflict(
        self,
        *,
        session_id: str,
        conflict_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Query a G7 inter-agent conflict; logic lives in kernel.inter_agent."""
        from zentex.kernel.inter_agent import query_inter_agent_conflict

        return query_inter_agent_conflict(
            self,
            session_id=session_id,
            conflict_id=conflict_id,
            task_id=task_id,
        )

    async def reassign_inter_agent_conflict(
        self,
        *,
        session_id: str,
        conflict_id: str,
        task_id: str,
        failed_agent_id: str,
        failure_reason: str,
    ) -> dict[str, Any]:
        """Reassign a G7 failed agent task; logic lives in kernel.inter_agent."""
        from zentex.kernel.inter_agent import reassign_inter_agent_conflict

        return await reassign_inter_agent_conflict(
            self,
            session_id=session_id,
            conflict_id=conflict_id,
            task_id=task_id,
            failed_agent_id=failed_agent_id,
            failure_reason=failure_reason,
        )

    def validate_safety_gate_action(
        self,
        *,
        session_id: str,
        action_type: str,
        action_payload: dict[str, Any],
        risk_level: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        execution_mode: str = "real",
        cloud_audit_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Validate a G8 action; logic lives in kernel.safety_gate."""
        from zentex.kernel.safety_gate import validate_safety_gate_action

        return validate_safety_gate_action(
            self,
            session_id=session_id,
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level,
            context=context,
            execution_mode=execution_mode,
            cloud_audit_config=cloud_audit_config,
        )

    def query_safety_gate_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
    ) -> dict[str, Any]:
        """Query a G8 decision; logic lives in kernel.safety_gate."""
        from zentex.kernel.safety_gate import query_safety_gate_decision

        return query_safety_gate_decision(
            self,
            session_id=session_id,
            decision_id=decision_id,
        )

    def confirm_safety_gate_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
        confirmed_by: str,
        confirmation_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Confirm a G8 decision; logic lives in kernel.safety_gate."""
        from zentex.kernel.safety_gate import confirm_safety_gate_decision

        return confirm_safety_gate_decision(
            self,
            session_id=session_id,
            decision_id=decision_id,
            confirmed_by=confirmed_by,
            confirmation_context=confirmation_context,
        )

    def run_thought_sandbox_simulation(
        self,
        *,
        session_id: str,
        action_type: str,
        action_payload: dict[str, Any],
        risk_level: str = "medium",
        task_type: str = "general",
        domain: str = "general",
        branches: Optional[list[dict[str, Any]]] = None,
        catastrophe_threshold: float = 0.7,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run a G9 thought-sandbox simulation; logic lives in kernel.thought_sandbox."""
        from zentex.kernel.thought_sandbox import run_thought_sandbox_simulation

        return run_thought_sandbox_simulation(
            self,
            session_id=session_id,
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level,
            task_type=task_type,
            domain=domain,
            branches=branches,
            catastrophe_threshold=catastrophe_threshold,
            context=context,
        )

    def query_thought_sandbox_outcome(
        self,
        *,
        session_id: str,
        outcome_id: str,
    ) -> dict[str, Any]:
        """Query a G9 thought-sandbox outcome; logic lives in kernel.thought_sandbox."""
        from zentex.kernel.thought_sandbox import query_thought_sandbox_outcome

        return query_thought_sandbox_outcome(self, session_id=session_id, outcome_id=outcome_id)

    def ingest_sensory_signal(
        self,
        *,
        session_id: str,
        source: str,
        payload: str,
        domain: str = "environment",
        source_observations: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Run the G10 sensory chain; logic lives in kernel.sensory_adapter."""
        from zentex.kernel.sensory_adapter import ingest_sensory_signal

        return ingest_sensory_signal(
            self,
            session_id=session_id,
            source=source,
            payload=payload,
            domain=domain,
            source_observations=source_observations,
        )

    def query_sensory_event(
        self,
        *,
        session_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        """Query a G10 sensory event; logic lives in kernel.sensory_adapter."""
        from zentex.kernel.sensory_adapter import query_sensory_event

        return query_sensory_event(self, session_id=session_id, event_id=event_id)

    def register_experience_expectation(
        self,
        *,
        session_id: str,
        task_id: str,
        expected_outcome: dict[str, Any],
        success_criteria: list[str],
        risk_assessment: Optional[dict[str, Any]] = None,
        source: str = "runtime",
    ) -> dict[str, Any]:
        """Register a G11 pre-action expectation; logic lives in kernel.experience_engine."""
        from zentex.kernel.experience_engine import register_experience_expectation

        return register_experience_expectation(
            self,
            session_id=session_id,
            task_id=task_id,
            expected_outcome=expected_outcome,
            success_criteria=success_criteria,
            risk_assessment=risk_assessment,
            source=source,
        )

    def bind_experience_outcome(
        self,
        *,
        session_id: str,
        expectation_id: str,
        actual_outcome: dict[str, Any],
        benefits: Optional[list[str]] = None,
        losses: Optional[list[str]] = None,
        source_reliability: float = 0.8,
        strategy_patch: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Bind a G11 actual outcome; logic lives in kernel.experience_engine."""
        from zentex.kernel.experience_engine import bind_experience_outcome

        return bind_experience_outcome(
            self,
            session_id=session_id,
            expectation_id=expectation_id,
            actual_outcome=actual_outcome,
            benefits=benefits,
            losses=losses,
            source_reliability=source_reliability,
            strategy_patch=strategy_patch,
        )

    def query_experience_binding(
        self,
        *,
        session_id: str,
        binding_id: str,
    ) -> dict[str, Any]:
        """Query a G11 outcome binding; logic lives in kernel.experience_engine."""
        from zentex.kernel.experience_engine import query_experience_binding

        return query_experience_binding(self, session_id=session_id, binding_id=binding_id)

    def rank_goals_with_experience(
        self,
        *,
        session_id: str,
        candidate_goals: list[dict[str, Any]],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Rank goals with G11 strategy patches; logic lives in kernel.experience_engine."""
        from zentex.kernel.experience_engine import rank_goals_with_experience

        return rank_goals_with_experience(
            self,
            session_id=session_id,
            candidate_goals=candidate_goals,
            context=context,
        )

    def learn_dynamic_tool_capability(
        self,
        *,
        session_id: str,
        documentation_url: str,
        source_kind: str,
        capability_name: Optional[str] = None,
        verification_endpoint: Optional[str] = None,
        verification_cases: Optional[list[dict[str, Any]]] = None,
        timeout_seconds: float = 3.0,
    ) -> dict[str, Any]:
        """Run G12 dynamic tool discovery; logic lives in kernel.dynamic_tool_learning."""
        from zentex.kernel.dynamic_tool_learning import learn_dynamic_tool_capability

        return learn_dynamic_tool_capability(
            self,
            session_id=session_id,
            documentation_url=documentation_url,
            source_kind=source_kind,
            capability_name=capability_name,
            verification_endpoint=verification_endpoint,
            verification_cases=verification_cases,
            timeout_seconds=timeout_seconds,
        )

    def query_tool_knowledge_record(
        self,
        *,
        session_id: str,
        knowledge_id: str,
    ) -> dict[str, Any]:
        """Query a G12 tool knowledge record; logic lives in kernel.dynamic_tool_learning."""
        from zentex.kernel.dynamic_tool_learning import query_tool_knowledge_record

        return query_tool_knowledge_record(self, session_id=session_id, knowledge_id=knowledge_id)

    def query_capability_registration(
        self,
        *,
        session_id: str,
        capability_id: str,
    ) -> dict[str, Any]:
        """Query a G12 capability registration; logic lives in kernel.dynamic_tool_learning."""
        from zentex.kernel.dynamic_tool_learning import query_capability_registration

        return query_capability_registration(self, session_id=session_id, capability_id=capability_id)

    def evaluate_value_engine(
        self,
        *,
        session_id: str,
        candidate_goals: list[dict[str, Any]],
        candidate_plans: Optional[list[dict[str, Any]]] = None,
        resource_state: Optional[dict[str, Any]] = None,
        risk_state: Optional[dict[str, Any]] = None,
        role_state: Optional[dict[str, Any]] = None,
        self_state: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        requested_capabilities: Optional[list[str]] = None,
        weight_profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run G13 budget/value evaluation; logic lives in kernel.value_engine."""
        from zentex.kernel.value_engine import evaluate_value_engine

        return evaluate_value_engine(
            self,
            session_id=session_id,
            candidate_goals=candidate_goals,
            candidate_plans=candidate_plans,
            resource_state=resource_state,
            risk_state=risk_state,
            role_state=role_state,
            self_state=self_state,
            context=context,
            requested_capabilities=requested_capabilities,
            weight_profile=weight_profile,
        )

    def query_value_engine_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
    ) -> dict[str, Any]:
        """Query a G13 value decision; logic lives in kernel.value_engine."""
        from zentex.kernel.value_engine import query_value_engine_decision

        return query_value_engine_decision(self, session_id=session_id, decision_id=decision_id)

    def submit_self_refactor_proposal(
        self,
        *,
        session_id: str,
        workspace_root: str,
        target_path: str,
        bottleneck_evidence: dict[str, Any],
        change_summary: str,
        replacement: dict[str, str],
        sandbox_commands: list[list[str]],
        capability_id: str,
        resource_state: Optional[dict[str, Any]] = None,
        risk_state: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        self_mod_gate_inputs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Submit a G14 self-refactor proposal; logic lives in kernel.self_refactor."""
        from zentex.kernel.self_refactor import submit_self_refactor_proposal

        return submit_self_refactor_proposal(
            self,
            session_id=session_id,
            workspace_root=workspace_root,
            target_path=target_path,
            bottleneck_evidence=bottleneck_evidence,
            change_summary=change_summary,
            replacement=replacement,
            sandbox_commands=sandbox_commands,
            capability_id=capability_id,
            resource_state=resource_state,
            risk_state=risk_state,
            context=context,
            self_mod_gate_inputs=self_mod_gate_inputs,
        )

    def query_self_refactor_proposal(
        self,
        *,
        session_id: str,
        proposal_id: str,
    ) -> dict[str, Any]:
        """Query a G14 self-refactor proposal; logic lives in kernel.self_refactor."""
        from zentex.kernel.self_refactor import query_self_refactor_proposal

        return query_self_refactor_proposal(self, session_id=session_id, proposal_id=proposal_id)

    def run_self_coding_cycle(
        self,
        *,
        session_id: str,
        workspace_root: str,
        candidate_root: str,
        capability_gap: dict[str, Any],
        patch_plan: dict[str, Any],
        verification_commands: list[list[str]],
    ) -> dict[str, Any]:
        """Run a G15 self-coding candidate cycle; logic lives in kernel.self_coding."""
        from zentex.kernel.self_coding import run_self_coding_cycle

        return run_self_coding_cycle(
            self,
            session_id=session_id,
            workspace_root=workspace_root,
            candidate_root=candidate_root,
            capability_gap=capability_gap,
            patch_plan=patch_plan,
            verification_commands=verification_commands,
        )

    def query_self_coding_patch(
        self,
        *,
        session_id: str,
        patch_id: str,
    ) -> dict[str, Any]:
        """Query a G15 self-coding patch; logic lives in kernel.self_coding."""
        from zentex.kernel.self_coding import query_self_coding_patch

        return query_self_coding_patch(self, session_id=session_id, patch_id=patch_id)

    async def run_preference_judgment(
        self,
        *,
        session_id: str,
        detected_state: dict[str, Any],
        detection_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run G16 preference judgment; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import run_preference_judgment

        return await run_preference_judgment(
            self,
            session_id=session_id,
            detected_state=detected_state,
            detection_source=detection_source,
            context=context,
        )

    async def confirm_preference_case(
        self,
        *,
        session_id: str,
        ambiguity_case_id: str,
        user_decision: str,
        user_id: str,
        confirmation_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Confirm a G16 ambiguity case; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import confirm_preference_case

        return await confirm_preference_case(
            self,
            session_id=session_id,
            ambiguity_case_id=ambiguity_case_id,
            user_decision=user_decision,
            user_id=user_id,
            confirmation_context=confirmation_context,
        )

    async def query_preference_record(
        self,
        *,
        session_id: str,
        preference_id: str,
    ) -> dict[str, Any]:
        """Query a G16 preference record; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import query_preference_record

        return await query_preference_record(self, session_id=session_id, preference_id=preference_id)

    async def revoke_preference_record(
        self,
        *,
        session_id: str,
        preference_id: str,
        reason: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Revoke a G16 preference record; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import revoke_preference_record

        return await revoke_preference_record(
            self,
            session_id=session_id,
            preference_id=preference_id,
            reason=reason,
            user_id=user_id,
        )

    async def intercept_extreme_signal(
        self,
        *,
        session_id: str,
        signal_content: str,
        signal_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Intercept a G16 extreme signal; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import intercept_extreme_signal

        return await intercept_extreme_signal(
            self,
            session_id=session_id,
            signal_content=signal_content,
            signal_source=signal_source,
            context=context,
        )

    async def mark_attack_sample(
        self,
        *,
        session_id: str,
        signal_record_id: str,
        attack_type: str,
        confidence: float,
        analyst_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mark a G16 attack sample; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import mark_attack_sample

        return await mark_attack_sample(
            self,
            session_id=session_id,
            signal_record_id=signal_record_id,
            attack_type=attack_type,
            confidence=confidence,
            analyst_id=analyst_id,
        )

    async def detect_similar_attack(
        self,
        *,
        session_id: str,
        signal_content: str,
        similarity_threshold: float = 0.85,
    ) -> dict[str, Any]:
        """Detect a G16 similar attack sample; logic lives in kernel.preference_alignment."""
        from zentex.kernel.preference_alignment import detect_similar_attack

        return await detect_similar_attack(
            self,
            session_id=session_id,
            signal_content=signal_content,
            similarity_threshold=similarity_threshold,
        )

    def _get_brain_daemon(self) -> Any:
        if self._brain_daemon is None:
            from zentex.kernel.brain_daemon import BrainDaemon, build_kernel_daemon_tick_handler

            self._brain_daemon = BrainDaemon(tick_handler=build_kernel_daemon_tick_handler(self))
        return self._brain_daemon

    # ------------------------------------------------------------------
    # Nine-question bootstrap (public API)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Nine-question bootstrap (global — no session_id in public API)
    # ------------------------------------------------------------------

    _DEFAULT_SESSION_ID = "zentex-default-session"
    _NINE_QUESTION_BASELINE_SESSION_ID = "nq-baseline"

    def _get_or_create_default_state(self) -> "_SessionState":
        """Return the default session state, creating it if necessary."""
        state = self._session_states.get(self._DEFAULT_SESSION_ID)
        if state is None:
            state = self._create_session_state(self._DEFAULT_SESSION_ID)
            self._session_states[self._DEFAULT_SESSION_ID] = state
        return state

    def _persist_incremental_nine_question_record(self, response: NineQuestionResponse) -> None:
        question_id = str(getattr(response, "question_id", "") or "").strip().lower()
        if not question_id:
            return
        if question_id in {"q1", "q2", "q3"}:
            return
        context_updates = getattr(response, "context_updates", None)
        if not isinstance(context_updates, dict):
            result_payload = getattr(response, "result_payload", None)
            if isinstance(result_payload, dict):
                context_updates = result_payload.get("context_updates")
        if not isinstance(context_updates, dict):
            return
        diagnosis = context_updates.get(f"{question_id}_execution_diagnosis")
        if not isinstance(diagnosis, dict):
            return
        module_runs = diagnosis.get("module_runs")
        if isinstance(module_runs, list):
            self._persist_incremental_nine_question_module_runs(question_id, module_runs)

    def _persist_incremental_nine_question_module_runs(
        self,
        question_id: str,
        module_runs: list[dict[str, Any]],
    ) -> None:
        if str(question_id or "").strip().lower() in {"q1", "q2", "q3"}:
            return
        session_id = self._NINE_QUESTION_BASELINE_SESSION_ID
        now = datetime.now(UTC).isoformat()
        db_path = get_storage_paths().session_db
        with sqlite3.connect(str(db_path)) as conn:
            for run in module_runs:
                if not isinstance(run, dict):
                    continue
                module_id = str(run.get("module_id") or "").strip()
                if not module_id:
                    continue
                existing = conn.execute(
                    """
                    SELECT run_version, created_at
                    FROM nine_question_module_runs
                    WHERE session_id = ? AND question_id = ? AND module_id = ?
                    """,
                    (session_id, question_id, module_id),
                ).fetchone()
                run_version = int(existing[0]) + 1 if existing else 1
                created_at = str(existing[1]) if existing else now
                conn.execute(
                    """
                    INSERT INTO nine_question_module_runs
                    (session_id, question_id, module_id, schema_version, run_version, status, run_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, question_id, module_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        run_version = excluded.run_version,
                        status = excluded.status,
                        run_json = excluded.run_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        question_id,
                        module_id,
                        1,
                        run_version,
                        str(run.get("status") or ""),
                        json.dumps(run, ensure_ascii=False, separators=(",", ":"), default=str),
                        created_at,
                        now,
                    ),
                )

    def _persist_incremental_nine_question_module_output(
        self,
        question_id: str,
        module_id: str,
        payload: dict[str, Any],
    ) -> None:
        if str(question_id or "").strip().lower() in {"q1", "q2", "q3"}:
            return
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"completed", "ready"}:
            return
        session_id = self._NINE_QUESTION_BASELINE_SESSION_ID
        question_text = str(question_id or "").strip().lower()
        module_text = str(module_id or payload.get("module_id") or "").strip()
        if not question_text or not module_text:
            return
        now = datetime.now(UTC).isoformat()
        db_path = get_storage_paths().session_db
        with sqlite3.connect(str(db_path)) as conn:
            existing = conn.execute(
                """
                SELECT output_version, created_at
                FROM nine_question_module_outputs
                WHERE session_id = ? AND question_id = ? AND module_id = ?
                """,
                (session_id, question_text, module_text),
            ).fetchone()
            output_version = int(existing[0]) + 1 if existing else 1
            created_at = str(existing[1]) if existing else now
            conn.execute(
                """
                INSERT INTO nine_question_module_outputs
                (session_id, question_id, module_id, schema_version, output_version, status,
                 output_kind, output_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, question_id, module_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    output_version = excluded.output_version,
                    status = excluded.status,
                    output_kind = excluded.output_kind,
                    output_json = excluded.output_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    question_text,
                    module_text,
                    1,
                    output_version,
                    status,
                    str(payload.get("output_kind") or ""),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                    created_at,
                    now,
                ),
            )

    def ensure_nine_questions_bootstrap(
        self,
        force: bool = False,
        max_retries: int = 1,
        rollback_on_failure: bool = False,
        merge_on_partial: bool = False,
    ) -> BootstrapStatus:
        """Ensure the shared nine-question baseline is initialized.

        Nine-questions are a global cognitive baseline — not scoped to any
        individual session.  The default session provides the transcript context
        needed by the coordinator.
        """
        default_state = self._get_or_create_default_state()
        with self._nq_shared_lock:
            current_status = self._nq_shared_state.get_state().bootstrap_status
            if not force and current_status in (
                BootstrapStatus.completed,
                BootstrapStatus.partial_failed,
            ):
                logger.debug(
                    f"Skipping Nine-Questions bootstrap; shared baseline already exists (status: {current_status})"
                )
                return current_status

            logger.info("[COGNITIVE BASELINE] Initializing shared nine-question bootstrap")
            self._nq_shared_state.set_bootstrap_status(BootstrapStatus.in_progress)

            try:
                final_status = self._nq_coordinator.coordinate(
                    session_id=self._DEFAULT_SESSION_ID,
                    state_manager=self._nq_shared_state,
                    transcript=default_state.transcript,
                    max_retries=max_retries,
                    rollback_on_failure=rollback_on_failure,
                    merge_on_partial=merge_on_partial,
                    response_updated_callback=self._persist_incremental_nine_question_record,
                )
                return final_status
            except Exception as exc:
                logger.exception(f"[COGNITIVE BASELINE] Shared bootstrap failed: {exc}")
                self._nq_shared_state.set_bootstrap_status(BootstrapStatus.failed)
                raise exc

    def rerun_nine_questions_from(
        self,
        question_id: str,
        max_retries: int = 1,
        rollback_on_failure: bool = False,
        merge_on_partial: bool = False,
    ) -> BootstrapStatus:
        """Rerun specific question and all downstream dependencies in the shared baseline."""
        default_state = self._get_or_create_default_state()
        with self._nq_shared_lock:
            logger.info(f"[COGNITIVE BASELINE] Rerunning shared questions from {question_id}")
            self._nq_shared_state.set_bootstrap_status(BootstrapStatus.in_progress)

            try:
                final_status = self._nq_coordinator.coordinate(
                    session_id=self._DEFAULT_SESSION_ID,
                    state_manager=self._nq_shared_state,
                    transcript=default_state.transcript,
                    max_retries=max_retries,
                    rollback_on_failure=rollback_on_failure,
                    merge_on_partial=merge_on_partial,
                    response_updated_callback=self._persist_incremental_nine_question_record,
                )
                return final_status
            except Exception as exc:
                logger.exception(f"[COGNITIVE BASELINE] Shared rerun failed: {exc}")
                self._nq_shared_state.set_bootstrap_status(BootstrapStatus.failed)
                raise exc

    def get_nine_question_state(self) -> Optional[dict]:
        """Return the shared Nine-Question baseline state."""
        return self._nq_shared_state.to_dict()

    def run_single_nine_question(
        self,
        question_id: str,
        max_retries: int = 1,
        rollback_on_failure: bool = False,
        merge_on_partial: bool = False,
        context_overrides: Optional[dict[str, Any]] = None,
    ) -> BootstrapStatus:
        """Execute a single question in isolation within the shared baseline context."""
        default_state = self._get_or_create_default_state()
        with self._nq_shared_lock:
            logger.info(f"[COGNITIVE BASELINE] Running single shared question {question_id}")
            self._nq_shared_state.set_bootstrap_status(BootstrapStatus.in_progress)

            # Find the specific question
            question = next((q for q in DEFAULT_NINE_QUESTIONS if q.question_id == question_id), None)
            if not question:
                raise ValueError(f"Unknown nine-question ID: {question_id}")

            # Build startup snapshot context
            context: dict = self._nq_coordinator._snapshot_builder.build(self._DEFAULT_SESSION_ID)
            if isinstance(context_overrides, dict):
                context.update(context_overrides)

            # Execute single question via executor directly
            responses = self._nq_coordinator._executor.execute(
                questions=[question],
                context=context,
                state_manager=self._nq_shared_state,
                transcript=default_state.transcript,
                max_retries=max_retries,
            )

            current_state = self._nq_shared_state.get_state()
            for response in responses:
                is_failed = bool(response.error)
                is_partial = bool(response.is_partial)
                existing_resp = current_state.responses.get(response.question_id)

                should_update_state = True
                if is_failed and rollback_on_failure and existing_resp and not existing_resp.error:
                    should_update_state = False

                if should_update_state:
                    # P3-Fix-D: mirror coordinator._commit_response() guard —
                    # a failed re-run must NOT overwrite a previously good answer.
                    existing_has_good_answer = (
                        existing_resp is not None
                        and bool(existing_resp.answer)
                        and not existing_resp.error
                    )
                    if is_failed and existing_has_good_answer:
                        use_merge = True  # preserve existing answer; merge diagnostics only
                    else:
                        use_merge = merge_on_partial and response.is_partial
                    self._nq_shared_state.update_response(response, merge_partial=use_merge)
                    self._persist_incremental_nine_question_record(response)
                    default_state.transcript.append(
                        TranscriptEntry(
                            entry_type=TranscriptEntryType.nine_q_update,
                            session_id=self._DEFAULT_SESSION_ID,
                            payload={
                                "question_id": response.question_id,
                                "status": "failed" if is_failed else "partial_failed" if is_partial else "success",
                            },
                        )
                    )

            failure_count = sum(1 for r in responses if r.error)
            partial_count = sum(1 for r in responses if r.is_partial and not r.error)
            if not responses:
                status = BootstrapStatus.failed
            elif failure_count == len(responses):
                status = BootstrapStatus.failed
            elif failure_count > 0 or partial_count > 0:
                status = BootstrapStatus.partial_failed
            else:
                status = BootstrapStatus.completed

            self._nq_shared_state.set_bootstrap_status(status)
            return status

    # ------------------------------------------------------------------
    # State queries (public API)
    # ------------------------------------------------------------------

    def get_session_state(self, session_id: str) -> Optional[dict]:
        """
        Return comprehensive session state including all domains.

        Combines working memory, self model, and temporal state into one dict.
        Returns None if session not found.
        """
        state = self._get_state(session_id)
        if state is None:
            return None
        return {
            "session_id": session_id,
            "session_meta": self.get_session_meta(session_id),
            "working_memory": state.working_memory.snapshot(),
            "self_model": state.self_model.snapshot(),
            "metacognition": state.meta_cognition.last_decision_snapshot() or {},
            "temporal": state.temporal.snapshot(),
            "nine_question_state": self._nq_shared_state.to_dict(),
        }

    def get_working_memory(self, session_id: str) -> list[Optional[dict]]:
        """
        Return the working memory slots for a session.

        Each slot is a dict with content, type, importance, and ttl.
        Returns None if session not found.
        """
        state = self._get_state(session_id)
        return state.working_memory.snapshot() if state else None

    def get_working_memory_snapshot(self, session_id: str) -> list[Optional[dict]]:
        """Deprecated: use get_working_memory() instead."""
        return self.get_working_memory(session_id)

    def get_self_model_snapshot(self, session_id: str) -> Optional[dict]:
        state = self._get_state(session_id)
        return state.self_model.snapshot() if state else None

    def get_temporal_snapshot(self, session_id: str) -> Optional[dict]:
        state = self._get_state(session_id)
        return state.temporal.snapshot() if state else None

    # ------------------------------------------------------------------
    # Transcript & Audit queries (public API)
    # ------------------------------------------------------------------

    def get_transcript(self, session_id: str, limit: int = 100) -> list[dict]:
        """
        Return the execution transcript (list of entries) for a session.

        Each entry includes type, timestamp, turn_id, and payload.
        Limited to most recent `limit` entries.
        """
        return self.query_transcript(session_id, limit=limit)

    def query_transcript(self, session_id: str, limit: int = 100) -> list[dict]:
        """Deprecated: use get_transcript() instead."""
        state = self._get_state(session_id)
        if state is None:
            return []
        entries = state.transcript.query_by_session(session_id, limit=limit)
        return [
            {
                "entry_id": e.entry_id,
                "entry_type": e.entry_type,
                "session_id": e.session_id,
                "turn_id": e.turn_id,
                "timestamp": e.timestamp,
                "source": getattr(e, "source", "kernel"),
                "trace_id": getattr(e, "trace_id", str(e.entry_id)),
                "payload": e.payload,
            }
            for e in entries
        ]

    def get_audit_log(self, session_id: str) -> dict:
        """
        Return a structured audit log for the session.

        Includes:
        - session_id, creation_time, last_modified
        - total_turns, phase_execution_count
        - error_count, warning_count
        - major_decision_points (list of turn_ids where significant decisions occurred)
        """
        state = self._get_state(session_id)
        if state is None:
            return {
                "session_id": session_id,
                "error": "session_not_found",
            }
        
        session_meta = self.get_session_meta(session_id)
        entries = state.transcript.query_by_session(session_id, limit=10000)
        
        error_count = sum(1 for e in entries if "error" in str(e.payload).lower())
        turn_ids = set(e.turn_id for e in entries if e.turn_id)
        
        return {
            "session_id": session_id,
            "created_at": session_meta.get("created_at") if session_meta else None,
            "last_turn_at": session_meta.get("last_turn_at") if session_meta else None,
            "total_turns": len(turn_ids),
            "total_transcript_entries": len(entries),
            "error_count": error_count,
            "warning_count": sum(1 for e in entries if "warning" in str(e.payload).lower()),
            "entry_types": list(set(e.entry_type for e in entries)),
            "trace_ids": [str(e.entry_id) for e in entries[:20]],  # Recent 20 trace IDs
        }

    def get_turn_summary(self, session_id: str, turn_id: str) -> Optional[dict]:
        state = self._get_state(session_id)
        if state is None:
            return None
        summary = state.transcript.build_turn_summary(turn_id)
        if summary is None:
            return None
        return {
            "turn_id": summary.turn_id,
            "session_id": summary.session_id,
            "phase_count": summary.phase_count,
            "error_count": summary.error_count,
            "started_at": summary.started_at,
            "ended_at": summary.ended_at,
            "duration_ms": summary.duration_ms,
        }

    def get_runtime_overview(
        self,
        session_id: str = "zentex-default-session",
        weight_assembler: Any = None,
    ) -> Dict[str, Any]:
        """
        Produce a comprehensive technical overview of the kernel and session state.
        Consolidated business logic migrated from web_console for zero-logic UI.
        """
        # 1. Runtime Foundation State
        runtime_id = self._svc_call(self._foundation_service, "get_runtime_id") or "zentex-kernel"
        start_time = self._svc_call(self._foundation_service, "get_start_time") or datetime.now(timezone.utc)
        
        active_session_ids = self.list_active_sessions()
        if not active_session_ids and session_id == self._DEFAULT_SESSION_ID:
            self._get_or_create_default_state()

        runtime_payload = {
            "runtime_id": runtime_id,
            "started_at": start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
            "active_session_ids": active_session_ids,
            "default_workspace": getattr(self.get_config(), "default_workspace", "unknown") if hasattr(self, 'get_config') else "unknown",
            "identity_kernel_ref": "v1",
            "tool_registry_version": "v1",
            "transcript_store_status": "connected",
            "memory_store_status": "connected",
            "read_only_mode": False,
            "degraded_mode": False,
            "manual_confirmation_required": True,
            "last_runtime_snapshot_at": datetime.now(timezone.utc).isoformat(),
        }

        # 2. Session Context
        session_snapshot = self.get_session_state(session_id)
        if session_snapshot is None and session_id == self._DEFAULT_SESSION_ID:
            state = self._get_or_create_default_state()
            session_snapshot = self._build_session_state_payload(session_id, state)
        session_snapshot = session_snapshot or {}
        enriched = self._enrich_runtime_overview_state(session_id=session_id, session_snapshot=session_snapshot)
        
        # 3. Transcript Analysis
        all_entries = self.get_transcript(session_id, limit=100)
        recent_entries = all_entries[-20:]
        
        last_intervention = None
        for entry in reversed(all_entries):
            if entry.get("entry_type") == BrainTranscriptEntryType.HUMAN_INTERVENTION_APPLIED.value:
                last_intervention = entry
                break
        
        # 4. Weight Profile
        weight_snapshot = weight_assembler.snapshot() if weight_assembler is not None else None
        
        return {
            "runtime": runtime_payload,
            "session": enriched["session"],
            "working_memory": enriched["working_memory"],
            "metacognition": enriched["metacognition"],
            "living_self_model": enriched["living_self_model"],
            "temporal_agenda": enriched["temporal_agenda"],
            "recent_entries": recent_entries,
            "last_intervention": last_intervention,
            "weights": {
                "active_plugin_id": getattr(weight_snapshot, "active_weight_plugin_id", None),
                "fallback_occurred": getattr(weight_snapshot, "weight_fallback_occurred", False),
                "profile": weight_snapshot.model_dump() if hasattr(weight_snapshot, "model_dump") else {}
            } if weight_snapshot else None
        }

    def _build_session_state_payload(self, session_id: str, state: "_SessionState") -> dict[str, Any]:
        return {
            "session_id": session_id,
            "session_meta": {
                "session_id": session_id,
                "status": "active",
            },
            "working_memory": state.working_memory.snapshot(),
            "self_model": state.self_model.snapshot(),
            "metacognition": state.meta_cognition.last_decision_snapshot() or {},
            "temporal": state.temporal.snapshot(),
            "nine_question_state": self._nq_shared_state.to_dict(),
        }

    def _enrich_runtime_overview_state(self, *, session_id: str, session_snapshot: dict[str, Any]) -> dict[str, Any]:
        state = self._get_state(session_id)
        slots = session_snapshot.get("working_memory", [])
        frame: dict[str, Any] | None = None
        if state is not None:
            try:
                frame = state.working_memory.frame_snapshot()
            except KeyError:
                frame = None

        active_items = frame.get("active_items", []) if isinstance(frame, dict) else []
        active_titles = [
            str(item.get("title")).strip()
            for item in active_items
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        active_summaries = [
            str(item.get("summary")).strip()
            for item in active_items
            if isinstance(item, dict) and str(item.get("summary") or "").strip()
        ]
        context_summary = str(frame.get("context_summary") or "").strip() if isinstance(frame, dict) else ""
        current_focus_summary = context_summary or (active_summaries[0] if active_summaries else None)

        self_model = dict(session_snapshot.get("self_model") or {})
        metacognition = dict(session_snapshot.get("metacognition") or {})
        temporal = dict(session_snapshot.get("temporal") or {})
        temporal_state = temporal.get("temporal_agenda_state") if isinstance(temporal.get("temporal_agenda_state"), dict) else {}
        cognitive_agenda = temporal_state.get("cognitive_agenda") if isinstance(temporal_state.get("cognitive_agenda"), dict) else {}
        agenda_items = cognitive_agenda.get("ordered_items") if isinstance(cognitive_agenda.get("ordered_items"), list) else []

        def _titles_for(ids: list[Any]) -> list[str]:
            wanted = {str(item_id) for item_id in ids}
            titles: list[str] = []
            for item in agenda_items:
                if not isinstance(item, dict) or str(item.get("item_id")) not in wanted:
                    continue
                title = str(item.get("title") or item.get("summary") or item.get("item_id") or "").strip()
                if title:
                    titles.append(title)
            return titles or [str(item_id) for item_id in ids if str(item_id).strip()]

        review_now_ids = temporal_state.get("review_now_item_ids") or temporal.get("review_now_item_ids") or []
        overdue_ids = temporal_state.get("overdue_item_ids") or temporal.get("overdue_item_ids") or []
        temporal["review_now_item_ids"] = list(review_now_ids)
        temporal["overdue_item_ids"] = list(overdue_ids)
        temporal["review_now_item_titles"] = _titles_for(list(review_now_ids))
        temporal["overdue_item_titles"] = _titles_for(list(overdue_ids))

        decision = metacognition.get("decision_bundle") if isinstance(metacognition.get("decision_bundle"), dict) else {}
        reasoning = decision.get("reasoning_mode_decision") if isinstance(decision.get("reasoning_mode_decision"), dict) else {}
        metacognition.setdefault("scheduler_status", "idle")
        if reasoning.get("thought_mode"):
            metacognition.setdefault("current_reasoning_mode", reasoning["thought_mode"])

        session = dict(session_snapshot.get("session_meta") or {})
        session.setdefault("session_id", session_id)
        session.setdefault("active_goal_titles", active_titles)
        session.setdefault("current_focus_summary", current_focus_summary)
        session.setdefault("current_reasoning_mode", metacognition.get("current_reasoning_mode"))
        session.setdefault("turn_count", self_model.get("turn_count") or temporal.get("total_turns") or 0)
        session.setdefault("degraded_flags", [])

        return {
            "session": session,
            "working_memory": {
                "slots": slots,
                "frame": frame,
                "active_focus_titles": active_titles,
                "current_focus_summary": current_focus_summary,
            },
            "metacognition": metacognition,
            "living_self_model": self_model,
            "temporal_agenda": temporal,
        }

    # ------------------------------------------------------------------
    # KernelServiceBridge implementation (called by ThinkLoop internally)
    # ------------------------------------------------------------------

    def observe_environment(self, session_id: str, turn_id: str) -> dict:
        """Phase 1: Observe — gather raw environmental observations.
        
        Policy: Eradicate 'environment: ok' stubs. Observation must be 
        authentic host sampling or sensory ingestion.
        """
        # AUTHENTIC GROUNDING: Pass the cognitive baseline to ensure impact is 
        # interpreted through the lens of identity and existing knowledge.
        identity = self.get_system_identity()
        nine_q_state = self._nq_shared_state.to_dict()

        result = self._svc_call(
            self._environment_service, "sample_and_interpret",
            current_role=identity.get("role_name"),
            identity=identity,
            nine_question_state=nine_q_state
        )
        
        if result is None or not isinstance(result, (list, tuple)) or len(result) < 2:
             raise RuntimeError(f"Environmental Observation failed for session {session_id}: Environment service returned invalid or empty state.")
        
        host_state, impact = result
             
        return {
            "physical_state": host_state.model_dump() if hasattr(host_state, "model_dump") else host_state,
            "situation_impact": impact.model_dump() if hasattr(impact, "model_dump") else impact,
            "observed_at": datetime.now(timezone.utc).isoformat()
        }

    def evaluate_drive(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Phase 1.5: Drive — determine situational motivation.
        
        Policy: Mission-Driven Integrity. If the drive cannot be evaluated,
        the cognitive turn is compromised and must be halted.
        """
        result = self._svc_call(
            self._cognition_service, "evaluate_drive",
            session_id=session_id, turn_id=turn_id, context=context
        )
        if not result or not isinstance(result, dict):
             raise RuntimeError(f"Cognitive Drive failed for session {session_id}: Service returned invalid or empty result.")
             
        return result

    def evaluate_cognition(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Phase 2: Frame — primary cognition and framing pass.
        
        Policy: Eradicate 'framing: default' stubs. Failure to frame context
        is a fatal cognitive error.
        """
        result = self._svc_call(self._cognition_service, "frame", session_id=session_id, context=context)
        if not result or not isinstance(result, dict):
            raise RuntimeError(f"Cognitive Framing failed for session {session_id}: Service returned invalid or empty result.")
        return result

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        """Phase 4: CognitiveRisks — safety and conflict detection.
        
        Policy: Hard failure on conflict detection failure.
        """
        from zentex.kernel.cognitive_conflict_runtime import detect_cognitive_conflicts_phase4

        return detect_cognitive_conflicts_phase4(self, session_id=session_id, context=context)

    def run_simulation(self, session_id: str, context: dict) -> dict:
        """Phase 5: Simulate — counterfactual scenario simulation.
        
        Policy: Simulation failure disables decision synthesis.
        """
        result = self._svc_call(self._cognition_service, "simulate", session_id=session_id, context=context)
        if result is None:
            raise RuntimeError("Counterfactual simulation failed: Decision space remains unexplored.")
        return result

    def run_metacognition(self, session_id: str, context: dict) -> dict:
        """Phase 6: Metacognition — internal reasoning decisions."""
        from zentex.kernel.meta_cognition_runtime import run_phase6_metacognition

        return run_phase6_metacognition(self, session_id=session_id, context=context)

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        """Phase 7: CognitiveTools — run registered cognitive tools."""
        from zentex.kernel.meta_cognition_runtime import invoke_planned_cognitive_tools

        return invoke_planned_cognitive_tools(self, session_id=session_id, context=context)

    def synthesize_decision(self, session_id: str, context: dict) -> dict:
        """Phase 8: DecisionSynthesis — produce the final response.
        
        Policy: Eradicate 'Mock Echo' fallbacks. Failure to generate an authentic
        response must result in a system-wide cognitive halt.
        """
        result = self._svc_call(self._llm_service, "generate_response", session_id=session_id, context=context)
        if result and isinstance(result, dict) and result.get("response"):
            return result
            
        logger.critical(f"Decision Failure for session {session_id}: LLM Service failed to return an authentic solution.")
        # POLICY: Fail-Closed. Never returning the input as an echo.
        raise RuntimeError(f"Cognitive Turn Halt: Decision synthesis failed for session {session_id}. Check upstream framing and simulation logs.")

    def consolidate_memory(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Phase 9: Consolidate — persist important memories.
        
        Policy: Memory loss is unacceptable.
        """
        result = self._svc_call(self._memory_service, "consolidate", session_id=session_id, turn_id=turn_id, context=context)
        if result is None:
            raise RuntimeError("Memory consolidation failed: Cognitive amnesia risk detected.")
        return result

    # ------------------------------------------------------------------
    # Bridge methods used by cognition_flow (snapshot_builder + executor)
    # ------------------------------------------------------------------

    def get_environment_state(self, session_id: str) -> dict:
        return self.observe_environment(session_id, turn_id="bootstrap")

    def get_registered_plugins(self) -> list[dict]:
        result = self._svc_call(
            self._plugins_service,
            "query_plugins_by_operational_status",
            operational_status="enabled",
            limit=500,
        )
        if isinstance(result, list):
            return result

        result = self._svc_call(self._plugins_service, "get_active_inventory")
        if isinstance(result, list):
            return result

        result = self._svc_call(self._plugins_service, "list_plugins")
        return result if isinstance(result, list) else []

    def get_system_identity(self) -> dict:
        if self._system_identity_store is not None:
            get_identity = getattr(self._system_identity_store, "get_identity", None)
            if callable(get_identity):
                stored_identity = get_identity()
                if isinstance(stored_identity, dict) and stored_identity.get("user_configured"):
                    return stored_identity

        if self._foundation_service is None:
            return {"role_name": "Zentex Agent", "mission": ""}

        identity = self._svc_call(self._foundation_service, "get_identity_snapshot")
        if identity is not None:
            # Sync with Q2 plugin expectations: needs identity_kernel_snapshot key
            return {
                "role_name": identity.role_name,
                "mission": identity.mission,
                "core_values": list(identity.core_values) if hasattr(identity, "core_values") else [],
                "identity_kernel_snapshot": {
                    "role_name": identity.role_name,
                    "mission": identity.mission,
                    "meta_motivation": identity.mission,  # Alias for evidence handler
                    "meta_drives": [identity.mission],     # Alias for evidence handler
                    "core_values": list(identity.core_values) if hasattr(identity, "core_values") else [],
                    "values_prohibition": " / ".join(identity.core_values) if hasattr(identity, "core_values") else "",
                    "value_vetoes": list(identity.core_values) if hasattr(identity, "core_values") else [],
                    "non_bypassable_constraints": list(identity.core_values) if hasattr(identity, "core_values") else [],
                }
            }
        return {"role_name": "Zentex Agent", "mission": ""}

    def get_capability_directory(self) -> list[dict]:
        directory = self._svc_call(self._foundation_service, "get_capability_directory")
        if directory is not None:
            return directory.to_dict().get("entries", [])
        return []

    def answer_nine_question(
        self, question: NineQuestion, context: dict
    ) -> NineQuestionResponse:
        """Called by NineQuestionExecutor to answer a single question via plugins.service."""
        from datetime import datetime
        start = datetime.now(UTC)
        session_id = str(context.get("session_id") or "")
        turn_id = str(context.get("turn_id") or "")
        trace_id = str(context.get("trace_id") or f"{session_id}:{question.question_id}")
        state = self._get_state(session_id) if session_id else None
        transcript_store = getattr(state, "transcript", None)
        llm_service = context.get("llm_service") or self._llm_service
        if llm_service is None:
            try:
                from zentex.llm import get_llm_service
                llm_service = get_llm_service()
            except Exception as e:
                logger.exception("Failed to initialize LLM service for nine-question execution")
                raise e

        plugin_audit_store = transcript_store

        nine_question_state_payload = self._build_scoped_nine_question_upstream_state(
            question_id=question.question_id,
            state_payload=self._nq_shared_state.to_dict(),
        )
        base_grounded_context = self._build_grounded_context(
            base_context=context,
            nine_question_state_payload=nine_question_state_payload,
            trigger=f"answer_nine_question:{question.question_id}"
        )
        
        def _persist_module_runs(question_id: str, module_runs: list[dict[str, Any]]) -> None:
            diagnosis_key = f"{question_id}_execution_diagnosis"
            payload_runs = deepcopy(module_runs) if isinstance(module_runs, list) else []
            partial_response = NineQuestionResponse(
                question_id=question_id,
                answer="",
                confidence=0.0,
                tool_id=f"nine_questions.{question_id}",
                trace_id=trace_id,
                timestamp=datetime.now(UTC).isoformat(),
                is_partial=True,
                context_updates={
                    diagnosis_key: {
                        "module_runs": payload_runs,
                    }
                },
                result_payload={
                    "context_updates": {
                        diagnosis_key: {
                            "module_runs": payload_runs,
                        }
                    }
                },
            )
            self._nq_shared_state.update_response(partial_response, merge_partial=True)
            self._persist_incremental_nine_question_record(partial_response)

        def _persist_module_output(question_id: str, module_id: str, payload: dict[str, Any]) -> None:
            self._persist_incremental_nine_question_module_output(question_id, module_id, payload)

        plugin_context = {
            **base_grounded_context,
            "session_id": session_id,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "llm_service": llm_service,
            "audit_store": plugin_audit_store,
            "transcript_store": plugin_audit_store,
            "root_audit_store": transcript_store,
            "root_transcript_store": transcript_store,
            "plugin_service": self._plugins_service,  # ESSENTIAL: needed for sensory chain
            "agent_service": context.get("agent_service") or self._agent_service,
            "cli_service": context.get("cli_service") or self._cli_service,
            "mcp_service": context.get("mcp_service") or self._mcp_service,
            "external_connector_service": context.get("external_connector_service") or self._external_connector_service,
            "environment_service": context.get("environment_service") or self._environment_service,
            "memory_service": context.get("memory_service") or self._memory_service,
            "audit_service": context.get("audit_service") or self._audit_service,
            "reflection_service": context.get("reflection_service") or self._reflection_service,
            "learning_service": context.get("learning_service") or self._learning_service,
            "foundation_service": context.get("foundation_service") or self._foundation_service,
            "module_run_persistor": _persist_module_runs,
            "module_output_persistor": _persist_module_output,
            "nine_question_storage_root": str(get_storage_paths().nine_questions_dir),
        }

        def _write_plugin_audit(payload: dict[str, Any]) -> None:
            if transcript_store is None:
                return
            if hasattr(transcript_store, "write_entry"):
                transcript_store.write_entry(
                    session_id=session_id,
                    turn_id=turn_id or "nine-question-bootstrap",
                    entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
                    trace_id=trace_id,
                    source="kernel.answer_nine_question",
                    payload=payload,
                )
                return
            transcript_store.append(
                TranscriptEntry(
                    entry_type=TranscriptEntryType.nine_q_update,
                    session_id=session_id,
                    turn_id=turn_id or "nine-question-bootstrap",
                    payload=payload,
                )
            )

        _write_plugin_audit(
            {
                "phase": "invoke",
                "question_id": question.question_id,
                "plugin_id": question.plugin_id,
                "trace_id": trace_id,
            }
        )

        # Use the implementation service for executing the nine-question implementation
        # This ensures all implementation-specific context and logic is contained
        # within the plugins module boundary.
        if self._nq_plugin_service is not None:
            response = self._nq_plugin_service.execute_question(
                question=question,
                context=plugin_context,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
            )
            # Re-enrich with snapshot artifacts if they were built locally
            # or if the response needs kernel-side metadata augmentation.
            snapshot_artifacts = self._build_snapshot_artifacts(
                plugin_audit_store=plugin_audit_store,
                session_id=session_id,
                trace_id=str(response.trace_id or trace_id),
                plugin_context=plugin_context,
            )
            response.execution_context = self._prefer_material_dict(
                snapshot_artifacts.get("execution_context"),
                response.execution_context,
            )
            response.execution_result = self._prefer_material_dict(
                snapshot_artifacts.get("execution_result"),
                response.execution_result,
            )
            response.llm_trace_payload = self._prefer_material_dict(
                snapshot_artifacts.get("llm_trace_payload"),
                response.llm_trace_payload,
            )
            _write_plugin_audit(
                {
                    "phase": "completed",
                    "question_id": question.question_id,
                    "plugin_id": question.plugin_id,
                    "status": "failed" if response.error else "ok",
                    "confidence": response.confidence,
                    "error": response.error or "",
                    "trace_id": str(response.trace_id or trace_id),
                }
            )
            return response
        else:
            # Fallback to direct plugin execution if implementation service is missing
            raw = self._svc_call(
                self._plugins_service,
                "execute_cognitive_plugin",
                plugin_id=question.plugin_id,
                context={
                    **plugin_context,
                    "question_id": question.question_id,
                    "question_text": question.text,
                },
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                originator_id=session_id or "kernel",
            )
        duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000

        if isinstance(raw, ServiceResponse):
            snapshot_artifacts = self._build_snapshot_artifacts(
                plugin_audit_store=plugin_audit_store,
                session_id=session_id,
                trace_id=str(raw.trace_id or trace_id),
                plugin_context=plugin_context,
            )
            if raw.is_ok:
                response = self._build_rich_nine_question_response(
                    question=question,
                    trace_id=trace_id,
                    duration_ms=duration_ms,
                    raw=raw,
                    snapshot_artifacts=snapshot_artifacts,
                )
                _write_plugin_audit(
                    {
                        "phase": "completed",
                        "question_id": question.question_id,
                        "plugin_id": question.plugin_id,
                        "status": "ok",
                        "confidence": response.confidence,
                        "trace_id": trace_id,
                    }
                )
                return response
            _write_plugin_audit(
                {
                    "phase": "completed",
                    "question_id": question.question_id,
                    "plugin_id": question.plugin_id,
                    "status": "failed",
                    "error": raw.message or raw.code or "cognitive_plugin_failed",
                    "trace_id": trace_id,
                }
            )
            return NineQuestionResponse(
                question_id=question.question_id,
                answer="",
                confidence=0.0,
                duration_ms=duration_ms,
                error=raw.message or raw.code or "cognitive_plugin_failed",
                tool_id=f"nine_questions.{question.question_id}",
                trace_id=str(raw.trace_id or trace_id),
                timestamp=datetime.now(UTC).isoformat(),
                result_payload=self._coerce_payload_dict(raw.data),
                execution_context=snapshot_artifacts["execution_context"],
                execution_result=snapshot_artifacts["execution_result"],
                llm_trace_payload=snapshot_artifacts["llm_trace_payload"],
            )

        if raw is not None:
            answer = raw.get("answer", "") if isinstance(raw, dict) else str(raw)
            confidence = float(raw.get("confidence", 0.7)) if isinstance(raw, dict) else 0.7
            snapshot_artifacts = self._build_snapshot_artifacts(
                plugin_audit_store=plugin_audit_store,
                session_id=session_id,
                trace_id=trace_id,
                plugin_context=plugin_context,
            )
            _write_plugin_audit(
                {
                    "phase": "completed",
                    "question_id": question.question_id,
                    "plugin_id": question.plugin_id,
                    "status": "ok",
                    "confidence": confidence,
                    "trace_id": trace_id,
                }
            )
            return NineQuestionResponse(
                question_id=question.question_id,
                answer=answer,
                confidence=confidence,
                duration_ms=duration_ms,
                tool_id=f"nine_questions.{question.question_id}",
                trace_id=trace_id,
                timestamp=datetime.now(UTC).isoformat(),
                result_payload=raw if isinstance(raw, dict) else {},
                execution_context=snapshot_artifacts["execution_context"],
                execution_result=snapshot_artifacts["execution_result"],
                llm_trace_payload=snapshot_artifacts["llm_trace_payload"],
            )

        # No real implementation available — return an explicit error
        _write_plugin_audit(
            {
                "phase": "completed",
                "question_id": question.question_id,
                "plugin_id": question.plugin_id,
                "status": "failed",
                "reason": "implementation_missing",
                "trace_id": trace_id,
            }
        )
        return NineQuestionResponse(
            question_id=question.question_id,
            answer="",
            confidence=0.0,
            duration_ms=duration_ms,
            error="implementation_missing",
            tool_id=f"nine_questions.{question.question_id}",
            trace_id=trace_id,
            timestamp=datetime.now(UTC).isoformat(),
            execution_context=self._sanitize_snapshot_payload(plugin_context),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state(self, session_id: str) -> Optional[_SessionState]:
        with self._lock:
            return self._session_states.get(session_id)

    @staticmethod
    def _extract_nine_question_answer(result: Any) -> tuple[str, float]:
        if result is None:
            return "", 0.0

        summary = str(getattr(result, "summary", "") or "").strip()
        confidence = getattr(result, "confidence", 0.7)
        if summary:
            return summary, float(confidence or 0.0)

        if isinstance(result, dict):
            answer = str(result.get("answer") or result.get("summary") or result.get("message") or "").strip()
            return answer, float(result.get("confidence", 0.7) or 0.0)

        return str(result), float(confidence or 0.0)

    @staticmethod
    def _derive_nine_question_summary(
        question_id: str,
        *,
        answer: str,
        result_payload: dict[str, Any],
        context_updates: dict[str, Any],
    ) -> str:
        if str(answer or "").strip():
            return str(answer).strip()

        question_titles = {
            "q1": "我在那",
            "q2": "我有什么",
            "q3": "我是谁",
            "q4": "我能做什么",
            "q5": "我不能干什么",
            "q6": "如果我做了会怎样 / 代价与后果是什么",
            "q7": "我还可以做什么",
            "q8": "我现在应该做什么",
            "q9": "我应该如何行动",
        }
        summary_key = question_titles.get(question_id)
        summary_map = context_updates.get("nine_questions")
        if isinstance(summary_map, dict):
            text = str(summary_map.get(summary_key) or "").strip()
            if text:
                return text

        if question_id == "q8":
            objective_profile = (
                result_payload.get("objective_profile")
                or context_updates.get("q8_objective_profile")
                or {}
            )
            objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
            task_queue = (
                result_payload.get("task_queue")
                or context_updates.get("q8_task_queue")
                or {}
            )
            task_queue = task_queue if isinstance(task_queue, dict) else {}
            objective = str(
                objective_profile.get("current_mission")
                or objective_profile.get("current_primary_objective")
                or ""
            ).strip()
            next_tasks = task_queue.get("next_self_tasks")
            blocked_tasks = task_queue.get("blocked_self_tasks")
            proactive_actions = task_queue.get("proactive_actions")
            next_count = len(next_tasks) if isinstance(next_tasks, list) else 0
            blocked_count = len(blocked_tasks) if isinstance(blocked_tasks, list) else 0
            proactive_count = len(proactive_actions) if isinstance(proactive_actions, list) else 0
            parts = []
            if objective:
                parts.append(f"objective={objective}")
            parts.append(f"next={next_count}")
            parts.append(f"blocked={blocked_count}")
            parts.append(f"proactive={proactive_count}")
            return "; ".join(parts)

        if question_id == "q9":
            evaluation_profile = (
                result_payload.get("evaluation_profile")
                or context_updates.get("q9_evaluation_profile")
                or {}
            )
            evaluation_profile = evaluation_profile if isinstance(evaluation_profile, dict) else {}
            style = str(evaluation_profile.get("evaluation_style") or "").strip()
            risk = str(
                evaluation_profile.get("risk_level")
                or evaluation_profile.get("risk_tolerance")
                or ""
            ).strip()
            conservative = evaluation_profile.get("conservative_mode_triggered")
            parts = []
            if style:
                parts.append(f"style={style}")
            if risk:
                parts.append(f"risk={risk}")
            if conservative not in (None, ""):
                parts.append(f"conservative={conservative}")
            return "; ".join(parts)

        return ""

    @staticmethod
    def _coerce_payload_dict(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            return dict(payload)
        if hasattr(payload, "model_dump"):
            dumped = payload.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(payload, "dict"):
            dumped = payload.dict()
            return dumped if isinstance(dumped, dict) else {}
        return {}

    @staticmethod
    def _sanitize_snapshot_payload(payload: Any) -> dict[str, Any]:
        def _sanitize(value: Any) -> Any:
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, dict):
                sanitized_dict: dict[str, Any] = {}
                for key, item in value.items():
                    sanitized_item = _sanitize(item)
                    if sanitized_item is not None:
                        sanitized_dict[str(key)] = sanitized_item
                return sanitized_dict
            if isinstance(value, (list, tuple, set)):
                return [_sanitize(item) for item in value]
            if hasattr(value, "model_dump"):
                dumped = value.model_dump(mode="json")
                return _sanitize(dumped)
            if hasattr(value, "dict"):
                dumped = value.dict()
                return _sanitize(dumped)
            return None

        sanitized = _sanitize(payload)
        return sanitized if isinstance(sanitized, dict) else {}

    @classmethod
    def _deep_merge_snapshot_dicts(
        cls,
        base: dict[str, Any],
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._deep_merge_snapshot_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _build_grounded_context(
        self,
        *,
        base_context: dict[str, Any],
        nine_question_state_payload: dict[str, Any],
        identity_payload: Optional[dict[str, Any]] = None,
        trigger: str = "current_turn",
    ) -> dict[str, Any]:
        """Construct a grounded context enriched with Nine-Question baseline results."""
        identity = identity_payload or self.get_system_identity()
        return {
            **base_context,
            "nine_question_state": nine_question_state_payload,
            "nine_questions": self._build_nine_question_summaries(
                base_context=base_context,
                nine_question_state_payload=nine_question_state_payload
            ),
            "context_snapshot": self._build_nine_question_context_snapshot(
                base_context=base_context,
                nine_question_state_payload=nine_question_state_payload
            ),
            "identity": identity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context_trigger": trigger,
        }

    @staticmethod
    def _build_scoped_nine_question_upstream_state(
        *,
        question_id: str,
        state_payload: dict[str, Any],
    ) -> dict[str, Any]:
        from zentex.common.nine_questions_shared import build_authoritative_question_llm_snapshot

        qid = str(question_id or "").strip().lower()
        try:
            current_order = int(qid[1:]) if qid.startswith("q") else 0
        except ValueError:
            current_order = 0
        upstream_question_ids = [f"q{i}" for i in range(1, current_order)] if current_order > 1 else []
        question_snapshots = state_payload.get("question_snapshots")
        question_snapshots = question_snapshots if isinstance(question_snapshots, dict) else {}
        scoped_snapshots = {
            upstream_q: build_authoritative_question_llm_snapshot(upstream_q, snapshot)
            for upstream_q in upstream_question_ids
            if isinstance((snapshot := question_snapshots.get(upstream_q)), dict)
        }
        return {
            "session_id": state_payload.get("session_id"),
            "bootstrap_status": state_payload.get("bootstrap_status"),
            "last_updated_at": state_payload.get("last_updated_at"),
            "upstream_for_question": qid,
            "question_snapshots": scoped_snapshots,
        }

    @classmethod
    def _build_nine_question_context_snapshot(
        cls,
        *,
        base_context: dict[str, Any],
        nine_question_state_payload: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = cls._sanitize_snapshot_payload(base_context.get("context_snapshot"))
        question_snapshots = nine_question_state_payload.get("question_snapshots")
        question_snapshots = question_snapshots if isinstance(question_snapshots, dict) else {}
        for item in question_snapshots.values():
            if not isinstance(item, dict):
                continue
            context_updates = item.get("context_updates")
            if not isinstance(context_updates, dict):
                continue
            # Plugins write cross-question profile keys directly at the top level of
            # context_updates (e.g. q4_capability_boundary_profile, q5_*, q6_*, ...).
            # Merge entire context_updates into the snapshot, but exclude the
            # "nine_questions" key which is handled by _build_nine_question_summaries.
            filtered_updates = {k: v for k, v in context_updates.items() if k != "nine_questions"}
            if filtered_updates:
                snapshot = cls._deep_merge_snapshot_dicts(
                    snapshot, cls._sanitize_snapshot_payload(filtered_updates)
                )
        return snapshot

    @classmethod
    def _build_nine_question_summaries(
        cls,
        *,
        base_context: dict[str, Any],
        nine_question_state_payload: dict[str, Any],
    ) -> dict[str, Any]:
        summaries = cls._sanitize_snapshot_payload(base_context.get("nine_questions"))
        question_snapshots = nine_question_state_payload.get("question_snapshots")
        question_snapshots = question_snapshots if isinstance(question_snapshots, dict) else {}
        for item in question_snapshots.values():
            if not isinstance(item, dict):
                continue
            context_updates = item.get("context_updates")
            if isinstance(context_updates, dict) and isinstance(context_updates.get("nine_questions"), dict):
                summaries = cls._deep_merge_snapshot_dicts(
                    summaries,
                    cls._sanitize_snapshot_payload(context_updates.get("nine_questions")),
                )
        if summaries:
            return summaries

        responses = nine_question_state_payload.get("responses")
        responses = responses if isinstance(responses, dict) else {}
        for response in responses.values():
            if not isinstance(response, dict):
                continue
            question_id = str(response.get("question_id") or "").strip()
            answer = str(response.get("answer") or "").strip()
            if question_id and answer:
                summaries[question_id] = answer
        return summaries

    def _read_plugin_audit_entries(
        self,
        *,
        plugin_audit_store: Optional[BrainTranscriptStore],
        session_id: str,
        trace_id: str,
    ) -> list[Any]:
        if plugin_audit_store is None or not session_id or not trace_id:
            return []
        try:
            return [
                entry
                for entry in plugin_audit_store.read_entries(session_id=session_id)
                if str(getattr(entry, "trace_id", "") or "") == trace_id
            ]
        except Exception:
            logger.exception("Failed to read plugin audit entries for session %s, trace %s", session_id, trace_id)
            return []

    def _build_snapshot_artifacts(
        self,
        *,
        plugin_audit_store: Optional[BrainTranscriptStore],
        session_id: str,
        trace_id: str,
        plugin_context: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        entries = self._read_plugin_audit_entries(
            plugin_audit_store=plugin_audit_store,
            session_id=session_id,
            trace_id=trace_id,
        )
        grouped_payloads: list[dict[str, dict[str, Any]]] = []
        group_index: dict[str, dict[str, dict[str, Any]]] = {}

        def _group_key(payload: dict[str, Any], fallback: str) -> str:
            return str(payload.get("request_id") or payload.get("decision_id") or fallback)

        def _get_group(payload: dict[str, Any], fallback: str) -> dict[str, dict[str, Any]]:
            key = _group_key(payload, fallback)
            group = group_index.get(key)
            if group is None:
                group = {}
                group_index[key] = group
                grouped_payloads.append(group)
            return group

        for entry in entries:
            entry_type = str(getattr(getattr(entry, "entry_type", None), "value", getattr(entry, "entry_type", "")) or "")
            payload = getattr(entry, "payload", None)
            payload = payload if isinstance(payload, dict) else {}
            group = _get_group(payload, f"entry-{len(grouped_payloads)}")
            if entry_type == "model_provider_invoked":
                group["invoked"] = payload
            elif entry_type == "model_provider_completed":
                group["completed"] = payload
            elif entry_type == "model_provider_failed":
                group["failed"] = payload

        def _build_llm_payload(group: dict[str, dict[str, Any]]) -> dict[str, Any]:
            invoked_payload = group.get("invoked") or {}
            completed_payload = group.get("completed") or {}
            failed_payload = group.get("failed") or {}
            caller_context = invoked_payload.get("caller_context")
            caller_context = caller_context if isinstance(caller_context, dict) else {}
            execution_context = invoked_payload.get("context")
            execution_context = execution_context if isinstance(execution_context, dict) else {}
            token_usage = completed_payload.get("token_usage")
            token_usage = token_usage if isinstance(token_usage, dict) else {}
            return {
                "request_id": invoked_payload.get("request_id"),
                "decision_id": invoked_payload.get("decision_id"),
                "provider_name": invoked_payload.get("provider_name") or invoked_payload.get("provider_plugin_id"),
                "model": completed_payload.get("model") or failed_payload.get("model"),
                "system_prompt": invoked_payload.get("system_prompt"),
                "prompt": invoked_payload.get("prompt"),
                "source_module": caller_context.get("source_module"),
                "invocation_phase": caller_context.get("invocation_phase"),
                "question_driver_refs": caller_context.get("question_driver_refs") or [],
                "context_data": execution_context,
                "raw_response": completed_payload.get("raw_response") if isinstance(completed_payload.get("raw_response"), dict) else None,
                "token_usage": {
                    "input_tokens": int(token_usage.get("input_tokens") or 0),
                    "output_tokens": int(token_usage.get("output_tokens") or 0),
                    "total_tokens": int(token_usage.get("total_tokens") or 0),
                },
                "elapsed_ms": completed_payload.get("elapsed_ms") or failed_payload.get("elapsed_ms"),
                "error_type": failed_payload.get("error_type"),
                "error_message": failed_payload.get("error_message") or failed_payload.get("error"),
            }

        invocations = [
            self._sanitize_snapshot_payload(_build_llm_payload(group))
            for group in grouped_payloads
            if group.get("invoked") or group.get("completed") or group.get("failed")
        ]
        material_invocations = [
            item for item in invocations
            if any(item.get(key) not in (None, "", [], {}) for key in ("provider_name", "model", "prompt", "raw_response", "error_type"))
        ]

        execution_context: dict[str, Any] = self._sanitize_snapshot_payload(plugin_context)
        execution_result: dict[str, Any] = {}
        llm_trace_payload: dict[str, Any] = {}
        if material_invocations:
            primary = dict(material_invocations[-1])
            aggregate_usage = {
                "input_tokens": sum(int((item.get("token_usage") or {}).get("input_tokens") or 0) for item in material_invocations),
                "output_tokens": sum(int((item.get("token_usage") or {}).get("output_tokens") or 0) for item in material_invocations),
                "total_tokens": sum(int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in material_invocations),
            }
            primary["token_usage"] = aggregate_usage
            primary["elapsed_ms"] = sum(int(item.get("elapsed_ms") or 0) for item in material_invocations)
            primary["invocations"] = material_invocations
            llm_trace_payload = primary
            first_context = material_invocations[0].get("context_data")
            if isinstance(first_context, dict) and first_context:
                execution_context = first_context
            for group in reversed(grouped_payloads):
                completed_result = (group.get("completed") or {}).get("result")
                if isinstance(completed_result, dict):
                    execution_result = completed_result
                    break

        return {
            "execution_context": self._sanitize_snapshot_payload(execution_context),
            "execution_result": self._sanitize_snapshot_payload(execution_result),
            "llm_trace_payload": self._sanitize_snapshot_payload(llm_trace_payload),
        }

    def _persist_nine_question_memory(self, session_id: str, *, trigger: str) -> None:
        """Persist a compact nine-question execution summary into memory."""
        state = self._get_state(session_id)
        if state is None:
            return

        payload = self._nq_shared_state.to_dict()
        snapshots = payload.get("question_snapshots")
        snapshots = snapshots if isinstance(snapshots, dict) else {}
        if not snapshots:
            return

        ordered_question_ids = sorted(snapshots.keys(), key=lambda item: int(item[1:]) if item.startswith("q") and item[1:].isdigit() else 999)
        trace_ids = {
            question_id: str(snapshot.get("trace_id") or "")
            for question_id, snapshot in snapshots.items()
            if isinstance(snapshot, dict) and str(snapshot.get("trace_id") or "").strip()
        }
        latest_trace_id = next(
            (
                trace_ids[question_id]
                for question_id in reversed(ordered_question_ids)
                if trace_ids.get(question_id)
            ),
            f"nine-questions:{session_id}:{trigger}",
        )

        summary_lines: list[str] = []
        for question_id in ordered_question_ids:
            snapshot = snapshots.get(question_id)
            if not isinstance(snapshot, dict):
                continue
            summary = str(snapshot.get("summary") or "").strip()
            confidence = snapshot.get("confidence")
            confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "0.00"
            if summary:
                summary_lines.append(f"{question_id}: {summary} (confidence={confidence_text})")

        memory_payload = {
            "session_id": session_id,
            "trigger": trigger,
            "bootstrap_status": payload.get("bootstrap_status"),
            "updated_at": payload.get("last_updated_at"),
            "question_ids": ordered_question_ids,
            "trace_ids": trace_ids,
            "question_summaries": {
                question_id: str((snapshots.get(question_id) or {}).get("summary") or "")
                for question_id in ordered_question_ids
                if isinstance(snapshots.get(question_id), dict)
            },
            "snapshot_version": len(snapshots),
        }
        content = json.dumps(
            {
                "title": "Nine question execution summary",
                "lines": summary_lines,
                "payload": memory_payload,
            },
            ensure_ascii=False,
            indent=2,
        )

        title = f"Nine Question Bootstrap {session_id}"
        summary = f"九问执行完成，已更新 {len(snapshots)} 个问题快照。"
        remember_result = self._svc_call(
            self._memory_service,
            "remember",
            content=content,
            title=title,
            summary=summary,
            layer="episodic",
            source="nine_questions",
            trace_id=latest_trace_id,
            tags=["nine-questions", "bootstrap", trigger],
            session_id=session_id,
            trigger=trigger,
            bootstrap_status=payload.get("bootstrap_status"),
            question_ids=ordered_question_ids,
            trace_ids=trace_ids,
        )
        if remember_result is None:
            return

        state.transcript.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.nine_q_update,
                session_id=session_id,
                turn_id="nine-question-bootstrap",
                payload={
                    "phase": "memory_write",
                    "trigger": trigger,
                    "question_count": len(snapshots),
                    "trace_id": latest_trace_id,
                    "title": title,
                },
            )
        )

    def _build_rich_nine_question_response(
        self,
        *,
        question: NineQuestion,
        trace_id: str,
        duration_ms: float,
        raw: ServiceResponse,
        snapshot_artifacts: dict[str, dict[str, Any]],
    ) -> NineQuestionResponse:
        result_payload = self._coerce_payload_dict(raw.data)
        answer, confidence = self._extract_nine_question_answer(raw.data)
        context_updates = self._coerce_payload_dict(result_payload.get("context_updates"))
        answer = self._derive_nine_question_summary(
            question.question_id,
            answer=answer,
            result_payload=result_payload,
            context_updates=context_updates,
        )
        return NineQuestionResponse(
            question_id=question.question_id,
            answer=answer,
            confidence=confidence,
            duration_ms=duration_ms,
            tool_id=str(result_payload.get("tool_id") or f"nine_questions.{question.question_id}"),
            trace_id=str(raw.trace_id or trace_id),
            timestamp=datetime.now(UTC).isoformat(),
            result_payload=result_payload,
            context_updates=context_updates,
            execution_context=snapshot_artifacts["execution_context"],
            execution_result=snapshot_artifacts["execution_result"],
            llm_trace_payload=snapshot_artifacts["llm_trace_payload"],
        )

    @staticmethod
    def _prefer_material_dict(primary: Any, secondary: Any) -> dict[str, Any]:
        if isinstance(primary, dict) and primary:
            return primary
        if isinstance(secondary, dict):
            return secondary
        return {}

    @staticmethod
    def _svc_call(service: Any, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call a method on an injected service with Fail-Closed integrity.

        Standard Redline:
        - We no longer suppress exceptions into 'None'.
        - If the service is missing, we raise AttributeError.
        - If the method call fails, we propagate the exception.
        """
        if service is None:
            raise AttributeError(f"Kernel: Attempted to call {method} on a None service.")
        
        fn = getattr(service, method, None)
        if not callable(fn):
            raise AttributeError(f"Kernel: Service {type(service).__name__} does not have a callable method '{method}'.")
        
        # Explicit call without catch-all suppression
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_default_service: Optional[KernelService] = None


def get_service(**kwargs: Any) -> KernelService:
    """Return the module-level KernelService singleton, creating it if necessary."""
    global _default_service
    if _default_service is None:
        _default_service = KernelService(**kwargs)
    return _default_service
