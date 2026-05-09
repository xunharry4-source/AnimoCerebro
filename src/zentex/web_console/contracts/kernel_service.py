from __future__ import annotations
"""Core Facade & DTO Definitions

Defines the main dependency contract for web_console, hiding complexity of
kernel.service and providing a stable interface for web_console modules.
"""


from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .session_manager import SessionManager
    from .state_manager import NineQuestionStateManager
    from .event_bus import EventBus


# ========== DTO Classes ==========


class SessionSnapshot(BaseModel):
    """Session snapshot (replaces runtime.active_session)
    
    Represents a single session state at a point in time.
    Persisted to SQLite and cached in memory.
    """

    session_id: str
    state_id: str
    workspace: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    question_drivers: List[str] = []
    last_turn_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "sess-123",
                "state_id": "state-456",
                "workspace": "<workspace-path>",
                "created_at": "2026-04-13T10:30:00Z",
                "question_drivers": ["q1", "q2"],
            }
        }
    )


class NineQuestionStateSnapshot(BaseModel):
    """Nine-question state snapshot (replaces runtime.nine_question_state)
    
    Tracks the computational state of nine-question reasoning about the agent's
    current status, identity, capabilities, etc.
    """

    version: int = 1
    revision: int = 0
    dirty_questions: List[str] = Field(
        default_factory=list,
        description="Question IDs marked as needing recomputation",
    )
    question_snapshots: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    question_snapshots_history: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    last_refresh_reason: Optional[str] = None
    snapshot_version: int = 9  # Legacy field for compatibility
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 1,
                "revision": 5,
                "dirty_questions": ["q3", "q5"],
                "last_refresh_reason": "trajectory_bounded",
                "snapshot_version": 9,
            }
        }
    )


class AppConfig(BaseModel):
    """Application configuration (replaces scattered runtime configs)
    
    Centralizes all configuration needed by web_console and its dependencies.
    """

    default_workspace: str = "."
    cache_ttl_seconds: int = 3600
    log_level: str = "INFO"
    enable_persistence: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "default_workspace": "/work",
                "cache_ttl_seconds": 3600,
                "log_level": "INFO",
            }
        }
    )


# ========== Abstract Facade ==========


class KernelServiceFacade(ABC):
    """Unified dependency entry point for web_console (Facade Pattern)
    
    This interface hides the complexity of kernel.service and exposes only
    what web_console needs. Implementation can be overridden (e.g., for testing).
    
    Design Rationale:
    - Decouples web_console from direct kernel.service imports
    - Provides a stable contract during transition from core/runtime
    - Allows multiple implementations (test mocks, different backends)
    """

    @abstractmethod
    def get_plugin_registry(self) -> Any:
        """Get plugin registry
        
        Returns:
            PluginRegistry: Plugin discovery and management
        """
        pass

    @abstractmethod
    def get_cognitive_tools(self) -> Any:
        """Get cognitive tool registry
        
        Returns:
            CognitiveToolRegistry: Tool discovery and execution
        """
        pass

    @abstractmethod
    def get_session_manager(self) -> SessionManager:
        """Get session lifecycle manager
        
        Returns:
            SessionManager: Create/read/update sessions with persistence
        """
        pass

    @abstractmethod
    def get_nine_question_state_manager(self) -> NineQuestionStateManager:
        """Get nine-question state manager
        
        Returns:
            NineQuestionStateManager: Query/update 9Q state with atomicity
        """
        pass

    @abstractmethod
    def get_event_bus(self) -> EventBus:
        """Get event bus
        
        Returns:
            EventBus: In-process pub/sub for state changes
        """
        pass

    @abstractmethod
    def get_workspace_store(self) -> Any:
        """Get the core workspace metadata store."""
        pass

    @abstractmethod
    def get_system_identity(self) -> dict[str, Any]:
        """Get the single system role used by Q2 and downstream 9Q processing."""
        pass

    @abstractmethod
    def update_system_identity(
        self,
        *,
        role_name: str,
        mission: str = "",
        core_values: list[str] | str | None = None,
    ) -> dict[str, Any]:
        """Create or replace the single user-configured system role."""
        pass

    @abstractmethod
    def reset_system_identity(self) -> dict[str, Any]:
        """Clear the user-configured system role."""
        pass

    @abstractmethod
    def get_config(self) -> AppConfig:
        """Get application configuration
        
        Returns:
            AppConfig: Configuration object with defaults
        """
        pass

    # ========== Session State Queries (Migration Helpers) ==========

    @abstractmethod
    def list_active_sessions(self) -> list[str]:
        """List active session IDs"""
        pass

    @abstractmethod
    def get_session_meta(self, session_id: str) -> Optional[dict]:
        """Get kernel session metadata for a session id."""
        pass

    @abstractmethod
    def create_kernel_session(self, user_id: str = "") -> str:
        """Create a kernel-backed session and return its session id."""
        pass

    @abstractmethod
    def ensure_nine_questions_bootstrap(self, *, force: bool = False) -> Any:
        """Run the kernel nine-question bootstrap (global — not session-scoped)."""
        pass

    @abstractmethod
    def run_single_nine_question(
        self,
        question_id: str,
        max_retries: int = 1,
        context_overrides: dict[str, Any] | None = None,
    ) -> Any:
        """Run exactly one nine-question in isolation without forcing downstream rerun."""
        pass

    @abstractmethod
    def get_session_state(self, session_id: str) -> Optional[dict]:
        """Get comprehensive session state (Working Memory, Self Model, Temporal)"""
        pass

    @abstractmethod
    def get_working_memory(self, session_id: str) -> list[Optional[dict]]:
        """Get working memory snapshot"""
        pass

    @abstractmethod
    def update_working_memory_frame(
        self,
        *,
        session_id: str,
        tick_id: str,
        new_candidates: list[dict[str, Any]],
        attention_budget: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Update Feature 52 working memory frame."""
        pass

    @abstractmethod
    def interrupt_working_memory_focus(
        self,
        *,
        session_id: str,
        tick_id: str,
        high_risk_item: dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict:
        """Interrupt active attention with a high-risk Feature 52 focus item."""
        pass

    @abstractmethod
    def resume_working_memory_focus(
        self,
        *,
        session_id: str,
        tick_id: str,
        focus_id: str,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Resume a suspended Feature 52 focus item."""
        pass

    @abstractmethod
    def mark_working_memory_considered(
        self,
        *,
        session_id: str,
        ref_id: str,
        tick_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Mark a Feature 52 source reference as recently considered."""
        pass

    @abstractmethod
    def query_working_memory_frame(self, *, session_id: str) -> dict:
        """Query the Feature 52 working memory frame."""
        pass

    @abstractmethod
    def update_living_self_model(
        self,
        *,
        session_id: str,
        turn_result: dict,
        recent_events: Optional[list[dict]] = None,
        working_memory_frame: Optional[dict] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Update the Feature 53 living self-model."""
        pass

    @abstractmethod
    def query_living_self_model(self, *, session_id: str) -> dict:
        """Query the Feature 53 living self-model."""
        pass

    @abstractmethod
    def detect_living_self_weakness_patterns(
        self,
        *,
        session_id: str,
        recent_events: list[dict],
        trace_id: Optional[str] = None,
    ) -> dict:
        """Detect Feature 53 weakness patterns from real evidence-bearing events."""
        pass

    @abstractmethod
    def check_living_self_confidence_drift(
        self,
        *,
        session_id: str,
        statements: list[dict],
        evidence: Optional[object] = None,
        threshold: float = 0.25,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Check Feature 53 confidence drift."""
        pass

    @abstractmethod
    def apply_living_self_load_adjustment(
        self,
        *,
        session_id: str,
        working_memory_frame: dict,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Apply Feature 53 load adjustment from a working-memory frame."""
        pass

    @abstractmethod
    def decide_meta_cognition(
        self,
        *,
        session_id: str,
        wm_frame: dict,
        self_model: dict,
        budget: dict,
        nine_q_state: dict,
        agenda: list[dict] | dict,
        tool_registry: list[dict] | dict,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Run the Feature 54 meta-cognition scheduler."""
        pass

    @abstractmethod
    def query_meta_cognition_decision(self, *, session_id: str) -> dict:
        """Query the latest Feature 54 meta-cognition decision."""
        pass

    @abstractmethod
    def tick_temporal_agenda(
        self,
        *,
        session_id: str,
        current_time: str,
        agenda_items: list[dict],
        brain_scope: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Run the Feature 55 temporal agenda tick."""
        pass

    @abstractmethod
    def query_temporal_agenda_state(self, *, session_id: str) -> dict:
        """Query the latest Feature 55 temporal agenda state."""
        pass

    @abstractmethod
    def detect_cognitive_conflicts(
        self,
        *,
        session_id: str,
        working_memory: dict,
        goals: Optional[list[dict]] = None,
        nine_q_state: Optional[dict] = None,
        memory_recalls: Optional[list[dict]] = None,
        budget: Optional[dict] = None,
        self_model: Optional[dict] = None,
        agenda: Optional[list[dict]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Run the Feature 56 cognitive conflict detector."""
        pass

    @abstractmethod
    def query_cognitive_conflicts(self, *, session_id: str) -> dict:
        """Query the latest Feature 56 cognitive conflicts."""
        pass

    @abstractmethod
    def get_self_model_snapshot(self, session_id: str) -> Optional[dict]:
        """Get self model snapshot"""
        pass

    @abstractmethod
    def get_temporal_snapshot(self, session_id: str) -> Optional[dict]:
        """Get temporal agenda snapshot"""
        pass

    @abstractmethod
    def get_nine_question_state(self) -> Optional[dict]:
        """Return the shared nine-question baseline state."""
        pass

    @abstractmethod
    def consult_external_brain(
        self,
        *,
        session_id: str,
        user_input: str,
        context: Optional[dict] = None,
        turn_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Run the G1 external-brain consultation flow and return advice only."""
        pass

    @abstractmethod
    def get_core_architecture_snapshot(self) -> dict:
        """Return the G2 core architecture snapshot."""
        pass

    @abstractmethod
    def control_brain_daemon(
        self,
        *,
        action: str,
        session_id: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        max_consecutive_failures: Optional[int] = None,
        run_background: bool = False,
    ) -> dict:
        """Control the G3 BrainDaemon."""
        pass

    @abstractmethod
    def get_brain_daemon_status(self) -> dict:
        """Return the G3 BrainDaemon status."""
        pass

    @abstractmethod
    def observe_environment_awareness(
        self,
        *,
        session_id: str,
        turn_id: Optional[str] = None,
        raw_signals: Optional[list[str]] = None,
        source_conflict_field: str = "memory_used_ratio",
        source_conflict_samples: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Run the G4 environment-awareness observation chain."""
        pass

    @abstractmethod
    def query_environment_awareness_snapshots(
        self,
        *,
        session_id: str,
        limit: int = 10,
    ) -> dict:
        """Query persisted G4 environment-awareness snapshots."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Create a G5 resource negotiation request and suspend the task."""
        pass

    @abstractmethod
    def query_resource_negotiation_requests(
        self,
        *,
        session_id: str,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Query G5 resource negotiation requests."""
        pass

    @abstractmethod
    async def resolve_resource_negotiation_request(
        self,
        *,
        session_id: str,
        negotiation_id: str,
        approved: bool,
        resolution_note: str,
        granted_asset: Optional[str] = None,
    ) -> dict:
        """Resolve a G5 resource negotiation request."""
        pass

    @abstractmethod
    def mount_identity_kernel(
        self,
        *,
        session_id: str,
        topics: Optional[list[str]] = None,
        risk_level: str = "low",
        identity_package: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Mount the G6 identity kernel."""
        pass

    @abstractmethod
    def query_identity_anchors(
        self,
        *,
        session_id: str,
        role: Optional[str] = None,
        risk_level: Optional[str] = None,
        topics: Optional[list[str]] = None,
        limit: int = 20,
    ) -> dict:
        """Query G6 identity anchors."""
        pass

    @abstractmethod
    def evaluate_identity_change(
        self,
        *,
        session_id: str,
        proposed_changes: dict[str, Any],
        human_confirmed: bool = False,
        reviewer: Optional[str] = None,
        drift_threshold: float = 0.34,
    ) -> dict:
        """Evaluate a G6 identity change."""
        pass

    @abstractmethod
    async def create_inter_agent_conflict(
        self,
        *,
        session_id: str,
        task_id: str,
        task_payload: dict[str, Any],
        required_capabilities: list[str],
        timeout_seconds: float = 5.0,
    ) -> dict:
        """Create a G7 inter-agent conflict and adjudicate real bids."""
        pass

    @abstractmethod
    def query_inter_agent_conflict(
        self,
        *,
        session_id: str,
        conflict_id: str,
        task_id: str,
    ) -> dict:
        """Query a persisted G7 inter-agent conflict."""
        pass

    @abstractmethod
    async def reassign_inter_agent_conflict(
        self,
        *,
        session_id: str,
        conflict_id: str,
        task_id: str,
        failed_agent_id: str,
        failure_reason: str,
    ) -> dict:
        """Reassign a G7 conflict after selected agent failure."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Validate a G8 SafetyGate action."""
        pass

    @abstractmethod
    def query_safety_gate_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
    ) -> dict:
        """Query a G8 SafetyGate decision."""
        pass

    @abstractmethod
    def confirm_safety_gate_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
        confirmed_by: str,
        confirmation_context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Confirm a G8 SafetyGate decision."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Run a G9 ThoughtSandbox simulation."""
        pass

    @abstractmethod
    def query_thought_sandbox_outcome(
        self,
        *,
        session_id: str,
        outcome_id: str,
    ) -> dict:
        """Query a G9 ThoughtSandbox outcome."""
        pass

    @abstractmethod
    def ingest_sensory_signal(
        self,
        *,
        session_id: str,
        source: str,
        payload: str,
        domain: str = "environment",
        source_observations: Optional[list[dict[str, Any]]] = None,
    ) -> dict:
        """Run the G10 sensory adapter chain."""
        pass

    @abstractmethod
    def query_sensory_event(
        self,
        *,
        session_id: str,
        event_id: str,
    ) -> dict:
        """Query a G10 sensory event."""
        pass

    @abstractmethod
    def register_experience_expectation(
        self,
        *,
        session_id: str,
        task_id: str,
        expected_outcome: dict[str, Any],
        success_criteria: list[str],
        risk_assessment: Optional[dict[str, Any]] = None,
        source: str = "runtime",
    ) -> dict:
        """Register a G11 action expectation."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Bind a G11 actual outcome."""
        pass

    @abstractmethod
    def query_experience_binding(
        self,
        *,
        session_id: str,
        binding_id: str,
    ) -> dict:
        """Query a G11 outcome binding."""
        pass

    @abstractmethod
    def rank_goals_with_experience(
        self,
        *,
        session_id: str,
        candidate_goals: list[dict[str, Any]],
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Rank candidate goals using G11 strategy patches."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Run G12 dynamic tool discovery and registration."""
        pass

    @abstractmethod
    def query_tool_knowledge_record(
        self,
        *,
        session_id: str,
        knowledge_id: str,
    ) -> dict:
        """Query a G12 tool knowledge record."""
        pass

    @abstractmethod
    def query_capability_registration(
        self,
        *,
        session_id: str,
        capability_id: str,
    ) -> dict:
        """Query a G12 capability registration."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Run G13 budget and value ranking."""
        pass

    @abstractmethod
    def query_value_engine_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
    ) -> dict:
        """Query a G13 value decision."""
        pass

    @abstractmethod
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
    ) -> dict:
        """Submit and verify a G14 self-refactor proposal."""
        pass

    @abstractmethod
    def query_self_refactor_proposal(
        self,
        *,
        session_id: str,
        proposal_id: str,
    ) -> dict:
        """Query a G14 self-refactor proposal."""
        pass

    @abstractmethod
    def run_self_coding_cycle(
        self,
        *,
        session_id: str,
        workspace_root: str,
        candidate_root: str,
        capability_gap: dict[str, Any],
        patch_plan: dict[str, Any],
        verification_commands: list[list[str]],
    ) -> dict:
        """Run a G15 isolated self-coding candidate patch cycle."""
        pass

    @abstractmethod
    def query_self_coding_patch(
        self,
        *,
        session_id: str,
        patch_id: str,
    ) -> dict:
        """Query a G15 self-coding candidate patch."""
        pass

    @abstractmethod
    async def run_preference_judgment(
        self,
        *,
        session_id: str,
        detected_state: dict[str, Any],
        detection_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Run a G16 user preference and intent judgment."""
        pass

    @abstractmethod
    async def confirm_preference_case(
        self,
        *,
        session_id: str,
        ambiguity_case_id: str,
        user_decision: str,
        user_id: str,
        confirmation_context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Confirm a G16 ambiguity case."""
        pass

    @abstractmethod
    async def query_preference_record(
        self,
        *,
        session_id: str,
        preference_id: str,
    ) -> dict:
        """Query a G16 preference record."""
        pass

    @abstractmethod
    async def revoke_preference_record(
        self,
        *,
        session_id: str,
        preference_id: str,
        reason: str,
        user_id: str,
    ) -> dict:
        """Revoke a G16 preference record."""
        pass

    @abstractmethod
    async def intercept_extreme_signal(
        self,
        *,
        session_id: str,
        signal_content: str,
        signal_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Intercept a G16 extreme signal."""
        pass

    @abstractmethod
    async def mark_attack_sample(
        self,
        *,
        session_id: str,
        signal_record_id: str,
        attack_type: str,
        confidence: float,
        analyst_id: Optional[str] = None,
    ) -> dict:
        """Mark a G16 attack sample."""
        pass

    @abstractmethod
    async def detect_similar_attack(
        self,
        *,
        session_id: str,
        signal_content: str,
        similarity_threshold: float = 0.85,
    ) -> dict:
        """Detect a G16 similar attack."""
        pass

    @abstractmethod
    def get_runtime_overview(
        self,
        session_id: str = "zentex-default-session",
        weight_assembler: Any = None,
    ) -> dict:
        """Get runtime overview snapshot
        
        This method delegates to kernel.service.KernelService.get_runtime_overview()
        which contains all business logic for aggregating runtime state.
        
        Args:
            session_id: Session identifier (default: "zentex-default-session")
            weight_assembler: Optional weight assembler for scoring calculations
            
        Returns:
            dict containing:
                - runtime: Runtime foundation state (runtime_id, active_sessions, etc.)
                - session: Current session context and state
                - working_memory: Working memory slots and contents
                - metacognition: Metacognitive state and reflection status
                - living_self_model: Self model snapshot
                - temporal_agenda: Temporal planning and scheduling state
                - recent_entries: Recent transcript entries (last N events)
                - last_intervention: Last human intervention event
                - weights: Weight plugin configuration and fallback status
                
        Architecture Note:
            web_console layer only calls this method and splices results.
            All aggregation logic resides in kernel.service.KernelService.
        """
        pass


# Resolve deferred ForwardRefs for Pydantic v2
SessionSnapshot.model_rebuild()
NineQuestionStateSnapshot.model_rebuild()
