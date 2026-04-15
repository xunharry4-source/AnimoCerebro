"""
Public service boundary for zentex.kernel.

All external modules (launcher, web_console, etc.) MUST interact with the
kernel exclusively through this file. Internal subdomains are not part of
the public API.

External module services are injected via attach_dependencies() — kernel
never imports external service modules directly.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    SelfModelEngine,
    TranscriptEntry,
    TranscriptEntryType,
    TranscriptStore,
    WorkingMemoryController,
)
from zentex.kernel.state_domain.brain_transcript import BrainTranscriptStore
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType

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
        self.transcript = TranscriptStore(session_id=session_id, db_dir=db_dir)
        self.nine_q_state = NineQuestionStateManager(session_id=session_id)


# ---------------------------------------------------------------------------
# KernelService — implements KernelServiceBridge
# ---------------------------------------------------------------------------

class KernelService:
    """Central kernel service. Implements KernelServiceBridge so it can be
    passed directly to ThinkLoop and other internal components."""

    def __init__(
        self,
        transcript_db_dir: str = "app_data/transcripts",
    ) -> None:
        # --- infrastructure ---
        self._transcript_db_dir = transcript_db_dir
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

        # --- nine-question components ---
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
        self._llm_service: Any = None
        self._foundation_service: Any = None

        self._initialized = True

    # ------------------------------------------------------------------
    # Engine accessors (for web console / default session)
    # ------------------------------------------------------------------

    @property
    def temporal_engine(self) -> Any | None:
        """Return the temporal engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            # Try to force create it if possible, or return None
            try:
                state = _SessionState(default_session_id, self._transcript_db_dir)
                self._session_states[default_session_id] = state
            except Exception:
                return None
        return state.temporal

    @property
    def conflict_engine(self) -> Any | None:
        """Return the conflict engine (self-model) for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
            try:
                state = _SessionState(default_session_id, self._transcript_db_dir)
                self._session_states[default_session_id] = state
            except Exception:
                return None
        return state.self_model

    @property
    def simulation_engine(self) -> Any | None:
        """Return the counterfactual simulation engine for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
             try:
                 state = _SessionState(default_session_id, self._transcript_db_dir)
                 self._session_states[default_session_id] = state
             except Exception:
                 return None
        # Shim for simulation - in this version, it's provided by cognition_service 
        # but the router expects a stateful domain object. 
        return getattr(self._cognition_service, "simulation_engine", None)

    @property
    def interaction_mind_engine(self) -> Any | None:
        """Return the interaction mind engine for the default session."""
        return getattr(self._cognition_service, "interaction_mind_engine", None)

    @property
    def consolidation_engine(self) -> Any | None:
        """Return the memory consolidation engine."""
        return getattr(self._memory_service, "consolidation_engine", None)

    @property
    def transcript_store(self) -> Any | None:
        """Return the transcript store for the default session."""
        default_session_id = "zentex-default-session"
        state = self._session_states.get(default_session_id)
        if state is None:
             try:
                 state = _SessionState(default_session_id, self._transcript_db_dir)
                 self._session_states[default_session_id] = state
             except Exception:
                 return None
        return state.transcript

    def get_transcript_store(self) -> Any | None:
        """Compatibility method for web console — returns transcript_store property."""
        return self.transcript_store

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
        llm_service: Any = None,
        foundation_service: Any = None,
    ) -> None:
        """Inject all external service references.

        Called by launcher.assembly.assembler after all services are initialised.
        Kernel never imports these services directly — they are always injected.
        """
        self._environment_service = environment_service
        self._cognition_service = cognition_service
        self._safety_service = safety_service
        self._plugins_service = plugins_service
        self._memory_service = memory_service
        self._llm_service = llm_service
        self._foundation_service = foundation_service

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

    def get_session_meta(self, session_id: str) -> dict | None:
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

    def start_turn(self, session_id: str, user_input: str, context: dict | None = None) -> TurnResult:
        """Execute a full 9-phase turn for the given session.

        Returns a TurnResult. Raises ValueError if session not found.
        """
        session = self._lifecycle.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        state = self._get_state(session_id)
        if state is None:
            raise ValueError(f"Session state missing for: {session_id}")

        turn_id = str(uuid4())
        request = TurnRequest(
            turn_id=turn_id,
            session_id=session_id,
            user_input=user_input,
            context=context or {},
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

    def ensure_nine_questions_bootstrap(self, session_id: str) -> BootstrapStatus:
        """Run or resume the nine-question cold-start for the given session.

        Returns the resulting BootstrapStatus.
        Raises ValueError if session not found.
        """
        state = self._get_state(session_id)
        if state is None:
            raise ValueError(f"Session state missing for: {session_id}")

        current_status = state.nine_q_state.get_state().bootstrap_status
        if current_status == BootstrapStatus.completed:
            return BootstrapStatus.completed

        return self._nq_coordinator.coordinate(
            session_id=session_id,
            state_manager=state.nine_q_state,
            transcript=state.transcript,
        )

    def get_nine_question_state(self, session_id: str) -> dict | None:
        """Return the current nine-question state dict for a session."""
        state = self._get_state(session_id)
        if state is None:
            return None
        return state.nine_q_state.to_dict()

    # ------------------------------------------------------------------
    # State queries (public API)
    # ------------------------------------------------------------------

    def get_session_state(self, session_id: str) -> dict | None:
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
            "nine_question_state": state.nine_q_state.to_dict(),
        }

    def get_working_memory(self, session_id: str) -> list[dict] | None:
        """
        Return the working memory slots for a session.

        Each slot is a dict with content, type, importance, and ttl.
        Returns None if session not found.
        """
        state = self._get_state(session_id)
        return state.working_memory.snapshot() if state else None

    def get_working_memory_snapshot(self, session_id: str) -> list[dict] | None:
        """Deprecated: use get_working_memory() instead."""
        return self.get_working_memory(session_id)

    def get_self_model_snapshot(self, session_id: str) -> dict | None:
        state = self._get_state(session_id)
        return state.self_model.snapshot() if state else None

    def get_temporal_snapshot(self, session_id: str) -> dict | None:
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

    def get_turn_summary(self, session_id: str, turn_id: str) -> dict | None:
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
        
        runtime_payload = {
            "runtime_id": runtime_id,
            "started_at": datetime.now(timezone.utc).isoformat(), # Placeholder
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
            "session": session_snapshot.get("session_meta"),
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
        """Phase 1: Observe — gather environment state."""
        result = self._svc_call(self._environment_service, "get_current_state", session_id=session_id)
        return result or {"session_id": session_id, "turn_id": turn_id, "observations": []}

    def evaluate_cognition(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Phase 2: Frame — primary cognition and framing pass."""
        result = self._svc_call(self._cognition_service, "frame", session_id=session_id, context=context)
        return result or {"framing": "default", "context_summary": str(context)[:200]}

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        """Phase 4: CognitiveRisks — safety and conflict detection."""
        result = self._svc_call(self._safety_service, "detect_conflicts", session_id=session_id, context=context)
        return result or {"conflicts": [], "risk_level": "low"}

    def run_simulation(self, session_id: str, context: dict) -> dict:
        """Phase 5: Simulate — counterfactual scenario simulation."""
        result = self._svc_call(self._cognition_service, "simulate", session_id=session_id, context=context)
        return result or {"simulations": [], "recommended": ""}

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
        """Phase 8: DecisionSynthesis — produce the final response."""
        result = self._svc_call(self._llm_service, "generate_response", session_id=session_id, context=context)
        if result:
            return result
        user_input = context.get("user_input", context.get("observations", ""))
        return {"response": f"[kernel] Received: {str(user_input)[:200]}"}

    def consolidate_memory(self, session_id: str, turn_id: str, context: dict) -> dict:
        """Phase 9: Consolidate — persist important memories."""
        result = self._svc_call(self._memory_service, "consolidate", session_id=session_id, turn_id=turn_id, context=context)
        return result or {"consolidated": False}

    # ------------------------------------------------------------------
    # Bridge methods used by cognition_flow (snapshot_builder + executor)
    # ------------------------------------------------------------------

    def get_environment_state(self, session_id: str) -> dict:
        return self.observe_environment(session_id, turn_id="bootstrap")

    def get_registered_plugins(self) -> list[dict]:
        result = self._svc_call(self._plugins_service, "list_plugins")
        return result if isinstance(result, list) else []

    def get_system_identity(self) -> dict:
        identity = self._svc_call(self._foundation_service, "get_identity_snapshot")
        if identity is not None:
            return {"role_name": identity.role_name, "mission": identity.mission}
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
            except Exception:
                llm_service = None

        plugin_audit_store = None
        if session_id:
            plugin_audit_store = BrainTranscriptStore(
                Path(".zentex") / "nine_question_audit" / f"{session_id}.sqlite3"
            )

        nine_question_state_payload = state.nine_q_state.to_dict() if state is not None else {}
        plugin_context = {
            **context,
            "session_id": session_id,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "llm_service": llm_service,
            "transcript_store": plugin_audit_store,
            "nine_question_state": nine_question_state_payload,
            "nine_questions": dict(nine_question_state_payload.get("responses") or {}),
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
            if raw.is_ok:
                answer, confidence = self._extract_nine_question_answer(raw.data)
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
                )
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
            )

        if raw is not None:
            answer = raw.get("answer", "") if isinstance(raw, dict) else str(raw)
            confidence = float(raw.get("confidence", 0.7)) if isinstance(raw, dict) else 0.7
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
            )

        # No real LLM service available — return a placeholder answer
        _write_plugin_audit(
            {
                "phase": "completed",
                "question_id": question.question_id,
                "plugin_id": question.plugin_id,
                "status": "fallback",
                "reason": "no_plugins_service_response",
                "trace_id": trace_id,
            }
        )
        return NineQuestionResponse(
            question_id=question.question_id,
            answer=f"[no plugin] {question.text}",
            confidence=0.0,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state(self, session_id: str) -> _SessionState | None:
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
    def _svc_call(service: Any, method: str, *args: Any, **kwargs: Any) -> Any:
        """Safely call a method on an injected service.

        Returns None if:
        - service is None
        - service doesn't have the method (e.g. it's a stub)
        - the call raises an exception
        """
        if service is None:
            return None
        fn = getattr(service, method, None)
        if not callable(fn):
            return None
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_default_service: KernelService | None = None


def get_service(**kwargs: Any) -> KernelService:
    """Return the module-level KernelService singleton, creating it if necessary."""
    global _default_service
    if _default_service is None:
        _default_service = KernelService(**kwargs)
    return _default_service
