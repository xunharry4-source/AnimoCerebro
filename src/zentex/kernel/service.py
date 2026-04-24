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
import threading
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Union, Optional, Union, Dict, List
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
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
    WorkingMemoryController,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType
from zentex.nine_questions.query import build_question_record

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Internal per-session state container
# ---------------------------------------------------------------------------

class _SessionState:
    """Holds all state-domain objects for a single session."""

    def __init__(self, session_id: str, db_dir: str) -> None:
        self.session_id = session_id
        self.working_memory = WorkingMemoryController(max_slots=WORKING_MEMORY_MAX_SLOTS)
        self.self_model = SelfModelEngine(session_id=session_id)
        self.temporal = CognitiveTemporalEngine(session_id=session_id)
        transcript_enabled = str(os.environ.get("ZENTEX_ENABLE_TRANSCRIPTS", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if transcript_enabled:
            self.transcript = TranscriptStore(session_id=session_id, db_dir=db_dir)
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
    ) -> None:
        # --- infrastructure ---
        self._transcript_db_dir = transcript_db_dir or str(get_storage_paths().transcript_dir)
        self._lock = threading.Lock()

        # --- session management ---
        self._lifecycle = SessionLifecycleManager()
        self._registry = SessionRegistry(self._lifecycle)

        # --- per-session state ---
        self._session_states: dict[str, _SessionState] = {}

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
        self._nq_plugin_service: Any = None
        self._reflection_service: Any = None
        self._learning_service: Any = None

        self._initialized = True

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
                state = _SessionState(default_session_id, self._transcript_db_dir)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        return state.temporal

    @property
    def conflict_engine(self) -> Any:
        """Return the conflict engine (self-model) for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = _SessionState(default_session_id, self._transcript_db_dir)
                self._session_states[default_session_id] = state
            except Exception as e:
                logger.exception(f"Failed to initialize engine state for {default_session_id}")
                raise e
        return state.self_model

    @property
    def simulation_engine(self) -> Any:
        """Return the counterfactual simulation engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = _SessionState(default_session_id, self._transcript_db_dir)
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
                state = _SessionState(default_session_id, self._transcript_db_dir)
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
        reflection_service: Any = None,
        learning_service: Any = None,
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
        if reflection_service is not None:
            self._reflection_service = reflection_service
        if learning_service is not None:
            self._learning_service = learning_service

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
        state = _SessionState(
            session_id=session.session_id,
            db_dir=self._transcript_db_dir,
        )
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
            turn_id=turn_id,
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

    # ------------------------------------------------------------------
    # Nine-question bootstrap (public API)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Nine-question bootstrap (global — no session_id in public API)
    # ------------------------------------------------------------------

    _DEFAULT_SESSION_ID = "zentex-default-session"

    def _get_or_create_default_state(self) -> "_SessionState":
        """Return the default session state, creating it if necessary."""
        state = self._session_states.get(self._DEFAULT_SESSION_ID)
        if state is None:
            state = _SessionState(self._DEFAULT_SESSION_ID, self._transcript_db_dir)
            self._session_states[self._DEFAULT_SESSION_ID] = state
        return state

    def _persist_incremental_nine_question_record(self, response: NineQuestionResponse) -> None:
        return None

    def _persist_incremental_nine_question_module_output(
        self,
        question_id: str,
        module_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

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
        
        runtime_payload = {
            "runtime_id": runtime_id,
            "started_at": start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
            "active_session_ids": self.list_active_sessions(),
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
        session_snapshot = self.get_session_state(session_id) or {}
        
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
            "session": session_snapshot.get("session_meta") or {},
            "working_memory": {"slots": session_snapshot.get("working_memory", [])},
            "metacognition": session_snapshot.get("metacognition", {}),
            "living_self_model": session_snapshot.get("self_model", {}),
            "temporal_agenda": session_snapshot.get("temporal", {}),
            "recent_entries": recent_entries,
            "last_intervention": last_intervention,
            "weights": {
                "active_plugin_id": getattr(weight_snapshot, "active_weight_plugin_id", None),
                "fallback_occurred": getattr(weight_snapshot, "weight_fallback_occurred", False),
                "profile": weight_snapshot.model_dump() if hasattr(weight_snapshot, "model_dump") else {}
            } if weight_snapshot else None
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
        result = self._svc_call(self._safety_service, "detect_conflicts", session_id=session_id, context=context)
        if result is None:
            raise RuntimeError("Conflict detection failed: Safety service unavailable or returned None.")
        return result

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
        state = self._get_state(session_id)
        return {
            "self_model": state.self_model.snapshot() if state else {},
            "metacognitive_notes": [],
        }

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        """Phase 7: CognitiveTools — run registered cognitive tools."""
        result = self._svc_call(self._plugins_service, "invoke_cognitive_tools", session_id=session_id, context=context)
        return result or {"tool_results": []}

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

        nine_question_state_payload = self._nq_shared_state.to_dict()
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
            response.execution_context = snapshot_artifacts.get("execution_context", response.execution_context)
            response.execution_result = snapshot_artifacts.get("execution_result", response.execution_result)
            response.llm_trace_payload = snapshot_artifacts.get("llm_trace_payload", response.llm_trace_payload)
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
            "q1": "我在哪",
            "q2": "我是谁",
            "q3": "我有什么",
            "q4": "我能做什么",
            "q5": "我被允许做什么",
            "q6": "我即使能做也不该做什么",
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
        invoked_payload: dict[str, Any] = {}
        completed_payload: dict[str, Any] = {}
        failed_payload: dict[str, Any] = {}
        for entry in entries:
            entry_type = str(getattr(getattr(entry, "entry_type", None), "value", getattr(entry, "entry_type", "")) or "")
            payload = getattr(entry, "payload", None)
            payload = payload if isinstance(payload, dict) else {}
            if entry_type == "model_provider_invoked":
                invoked_payload = payload
            elif entry_type == "model_provider_completed":
                completed_payload = payload
            elif entry_type == "model_provider_failed":
                failed_payload = payload

        execution_context = invoked_payload.get("context")
        execution_context = execution_context if isinstance(execution_context, dict) else self._sanitize_snapshot_payload(plugin_context)
        execution_result = completed_payload.get("result")
        execution_result = execution_result if isinstance(execution_result, dict) else {}
        token_usage = completed_payload.get("token_usage")
        token_usage = token_usage if isinstance(token_usage, dict) else {}

        llm_trace_payload = {}
        if invoked_payload or completed_payload or failed_payload:
            caller_context = invoked_payload.get("caller_context")
            caller_context = caller_context if isinstance(caller_context, dict) else {}
            llm_trace_payload = {
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
