from __future__ import annotations
"""Default Kernel Service Facade Implementation

Adapter pattern connecting web_console to kernel.service.
Gradually replaces direct kernel/runtime dependencies.
"""


import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .contracts.kernel_service import (
    KernelServiceFacade,
    AppConfig,
)
from .cache_manager import WebConsoleCacheManager
from .contracts.session_manager import SessionManager
from .contracts.state_manager import NineQuestionStateManager
from .contracts.event_bus import EventBus

if TYPE_CHECKING:
    from zentex.kernel.service import KernelService

logger = logging.getLogger(__name__)


class DefaultKernelServiceFacade(KernelServiceFacade):
    """Default implementation using adapter pattern
    
    Strategy:
    - WebConsole owns only facade calls.
    - Core assembles persistence-backed state services.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
    ):
        """Initialize facade with core-owned storage backends.

        Args:
            config: Optional custom config (defaults to AppConfig)
        """
        from zentex.kernel.console_state_services import build_console_state_services

        # Backend: old runtime service (lazy loaded on first use)
        self._runtime_service: Any = None  # Will be loaded on demand
        self._runtime_service_loaded = False
        self._runtime_service_load_error: Optional[Exception] = None

        self._config = config or AppConfig(default_workspace=".")

        state_services = build_console_state_services(
            cache_ttl_seconds=self._config.cache_ttl_seconds
        )
        self._session_manager: SessionManager = state_services.session_manager
        self._state_manager: NineQuestionStateManager = state_services.state_manager
        self._event_bus = state_services.event_bus
        self._cache_manager = state_services.cache_manager
        self._workspace_store = state_services.workspace_store

    def _load_kernel_service(self) -> Any:
        """Load kernel.service lazily so failure semantics are testable."""
        from zentex.kernel.service import get_service as get_kernel_service

        return get_kernel_service()

    def _get_kernel_service(self) -> Any:
        """Lazily load kernel service on first access.
        
        Standard Redline:
        - Fail-Closed: If the kernel service cannot be loaded, this method must
          propagate the exception to prevent the system from operating in a 
          functionally amputated state.
        """
        if not self._runtime_service_loaded:
            try:
                self._runtime_service = self._load_kernel_service()
                self._runtime_service_load_error = None
            except Exception as exc:
                # Standard redline: never swallow kernel assembly failure and pretend
                # the compatibility facade merely has "no data". That fake-normal
                # path hides backend breakage and destroys operator visibility.
                logger.exception("Could not load kernel service")
                self._runtime_service = None
                self._runtime_service_load_error = exc
            self._runtime_service_loaded = True
        return self._runtime_service

    def _require_kernel_service(self, operation: str) -> Any:
        """Return the kernel service or fail closed with the real backend cause."""
        kernel_service = self._get_kernel_service()
        if kernel_service is not None:
            return kernel_service

        if self._runtime_service_load_error is not None:
            raise RuntimeError(
                f"Kernel service unavailable during {operation}; refusing to fake a normal empty result: "
                f"{self._runtime_service_load_error}"
            ) from self._runtime_service_load_error

        # Standard redline: if the facade cannot provide a backend here, returning
        # None or {} would be a fake implementation that lies to monitoring pages.
        raise RuntimeError(
            f"Kernel service unavailable during {operation}; refusing to fake backend availability"
        )

    @staticmethod
    def _require_kernel_method(kernel_service: Any, method_name: str, operation: str) -> Any:
        method = getattr(kernel_service, method_name, None)
        if method is None:
            # Standard redline: do not pretend an unimplemented kernel bridge method
            # is the same as "no data right now". That is a fake completed feature.
            raise RuntimeError(
                f"Kernel service does not implement {method_name} for {operation}; refusing to fake success"
            )
        return method

    def get_nine_question_audit_store(self, session_id: str) -> Any:
        """Get the session-scoped nine-question audit transcript store."""
        kernel_service = self._require_kernel_service("get_nine_question_audit_store")
        return self._require_kernel_method(
            kernel_service,
            "get_nine_question_audit_store",
            "get_nine_question_audit_store",
        )(session_id)

    def get_plugin_registry(self) -> Any:
        """Get plugin registry from plugins.service"""
        raise NotImplementedError(
            "get_plugin_registry is deprecated. "
            "Use plugins.service.SystemPluginService directly or inject it via app.state.plugin_service"
        )

    def get_cognitive_tools(self) -> Any:
        """Get cognitive tool registry from plugins.service"""
        raise NotImplementedError(
            "get_cognitive_tools is deprecated. "
            "Use plugins.service.SystemPluginService.query_cognitive_tools() instead"
        )

    def get_session_manager(self) -> SessionManager:
        """Get session lifecycle manager"""
        return self._session_manager

    def get_nine_question_state_manager(self) -> NineQuestionStateManager:
        """Get nine-question state manager"""
        return self._state_manager

    def get_event_bus(self) -> EventBus:
        """Get event bus"""
        return self._event_bus

    def get_workspace_store(self) -> Any:
        """Get the core workspace metadata store."""
        return self._workspace_store

    def get_config(self) -> AppConfig:
        """Get application configuration"""
        return self._config

    # ========== Session State Queries (Migration Helpers) ==========

    def list_active_sessions(self) -> list[str]:
        """List active session IDs"""
        kernel = self._require_kernel_service("list_active_sessions")
        return self._require_kernel_method(kernel, "list_active_sessions", "list_active_sessions")()

    def get_session_meta(self, session_id: str) -> Optional[dict]:
        """Get kernel session metadata."""
        kernel = self._require_kernel_service("get_session_meta")
        return self._require_kernel_method(kernel, "get_session_meta", "get_session_meta")(session_id)

    def create_kernel_session(self, user_id: str = "") -> str:
        """Create a kernel-backed session."""
        kernel = self._require_kernel_service("create_kernel_session")
        return str(self._require_kernel_method(kernel, "create_session", "create_kernel_session")(user_id=user_id))

    def ensure_nine_questions_bootstrap(self, *, force: bool = False) -> Any:
        """Run kernel nine-question bootstrap (global — no session scoping)."""
        kernel = self._require_kernel_service("ensure_nine_questions_bootstrap")
        return self._require_kernel_method(
            kernel,
            "ensure_nine_questions_bootstrap",
            "ensure_nine_questions_bootstrap",
        )(force=force)

    def rerun_nine_questions_from(self, question_id: str, max_retries: int = 1) -> Any:
        """Re-run a single nine-question and its downstream chain."""
        kernel = self._require_kernel_service("rerun_nine_questions_from")
        return self._require_kernel_method(
            kernel,
            "rerun_nine_questions_from",
            "rerun_nine_questions_from",
        )(question_id, max_retries=max_retries)

    def run_single_nine_question(self, question_id: str, max_retries: int = 1) -> Any:
        """Run only one nine-question and keep downstream questions untouched."""
        kernel = self._require_kernel_service("run_single_nine_question")
        return self._require_kernel_method(
            kernel,
            "run_single_nine_question",
            "run_single_nine_question",
        )(question_id, max_retries=max_retries)

    def get_session_state(self, session_id: str) -> Optional[dict]:
        """Get comprehensive session state"""
        kernel = self._require_kernel_service("get_session_state")
        return self._require_kernel_method(kernel, "get_session_state", "get_session_state")(session_id)

    def get_working_memory(self, session_id: str) -> list[Optional[dict]]:
        """Get working memory snapshot"""
        kernel = self._require_kernel_service("get_working_memory")
        return self._require_kernel_method(kernel, "get_working_memory", "get_working_memory")(session_id)

    def update_working_memory_frame(
        self,
        *,
        session_id: str,
        tick_id: str,
        new_candidates: list[dict[str, Any]],
        attention_budget: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 52 working memory frame update to kernel.service."""
        kernel = self._require_kernel_service("update_working_memory_frame")
        return self._require_kernel_method(
            kernel,
            "update_working_memory_frame",
            "update_working_memory_frame",
        )(
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
    ) -> dict:
        """Delegate Feature 52 high-risk interrupt to kernel.service."""
        kernel = self._require_kernel_service("interrupt_working_memory_focus")
        return self._require_kernel_method(
            kernel,
            "interrupt_working_memory_focus",
            "interrupt_working_memory_focus",
        )(
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
    ) -> dict:
        """Delegate Feature 52 resume to kernel.service."""
        kernel = self._require_kernel_service("resume_working_memory_focus")
        return self._require_kernel_method(
            kernel,
            "resume_working_memory_focus",
            "resume_working_memory_focus",
        )(
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
    ) -> dict:
        """Delegate Feature 52 recently-considered marker to kernel.service."""
        kernel = self._require_kernel_service("mark_working_memory_considered")
        return self._require_kernel_method(
            kernel,
            "mark_working_memory_considered",
            "mark_working_memory_considered",
        )(
            session_id=session_id,
            ref_id=ref_id,
            tick_id=tick_id,
            trace_id=trace_id,
        )

    def query_working_memory_frame(self, *, session_id: str) -> dict:
        """Delegate Feature 52 frame query to kernel.service."""
        kernel = self._require_kernel_service("query_working_memory_frame")
        return self._require_kernel_method(
            kernel,
            "query_working_memory_frame",
            "query_working_memory_frame",
        )(session_id=session_id)

    def update_living_self_model(
        self,
        *,
        session_id: str,
        turn_result: dict,
        recent_events: Optional[list[dict]] = None,
        working_memory_frame: Optional[dict] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 53 living self-model update to kernel.service."""
        kernel = self._require_kernel_service("update_living_self_model")
        return self._require_kernel_method(
            kernel,
            "update_living_self_model",
            "update_living_self_model",
        )(
            session_id=session_id,
            turn_result=turn_result,
            recent_events=recent_events,
            working_memory_frame=working_memory_frame,
            trace_id=trace_id,
        )

    def query_living_self_model(self, *, session_id: str) -> dict:
        """Delegate Feature 53 living self-model query to kernel.service."""
        kernel = self._require_kernel_service("query_living_self_model")
        return self._require_kernel_method(
            kernel,
            "query_living_self_model",
            "query_living_self_model",
        )(session_id=session_id)

    def detect_living_self_weakness_patterns(
        self,
        *,
        session_id: str,
        recent_events: list[dict],
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 53 weakness detection to kernel.service."""
        kernel = self._require_kernel_service("detect_living_self_weakness_patterns")
        return self._require_kernel_method(
            kernel,
            "detect_living_self_weakness_patterns",
            "detect_living_self_weakness_patterns",
        )(session_id=session_id, recent_events=recent_events, trace_id=trace_id)

    def check_living_self_confidence_drift(
        self,
        *,
        session_id: str,
        statements: list[dict],
        evidence: Optional[object] = None,
        threshold: float = 0.25,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 53 confidence drift check to kernel.service."""
        kernel = self._require_kernel_service("check_living_self_confidence_drift")
        return self._require_kernel_method(
            kernel,
            "check_living_self_confidence_drift",
            "check_living_self_confidence_drift",
        )(
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
        working_memory_frame: dict,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 53 load adjustment to kernel.service."""
        kernel = self._require_kernel_service("apply_living_self_load_adjustment")
        return self._require_kernel_method(
            kernel,
            "apply_living_self_load_adjustment",
            "apply_living_self_load_adjustment",
        )(session_id=session_id, working_memory_frame=working_memory_frame, trace_id=trace_id)

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
        """Delegate Feature 54 scheduler decision to kernel.service."""
        kernel = self._require_kernel_service("decide_meta_cognition")
        return self._require_kernel_method(
            kernel,
            "decide_meta_cognition",
            "decide_meta_cognition",
        )(
            session_id=session_id,
            wm_frame=wm_frame,
            self_model=self_model,
            budget=budget,
            nine_q_state=nine_q_state,
            agenda=agenda,
            tool_registry=tool_registry,
            trace_id=trace_id,
        )

    def query_meta_cognition_decision(self, *, session_id: str) -> dict:
        """Delegate Feature 54 scheduler query to kernel.service."""
        kernel = self._require_kernel_service("query_meta_cognition_decision")
        return self._require_kernel_method(
            kernel,
            "query_meta_cognition_decision",
            "query_meta_cognition_decision",
        )(session_id=session_id)

    def tick_temporal_agenda(
        self,
        *,
        session_id: str,
        current_time: str,
        agenda_items: list[dict],
        brain_scope: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate Feature 55 temporal agenda tick to kernel.service."""
        kernel = self._require_kernel_service("tick_temporal_agenda")
        return self._require_kernel_method(
            kernel,
            "tick_temporal_agenda",
            "tick_temporal_agenda",
        )(
            session_id=session_id,
            current_time=current_time,
            agenda_items=agenda_items,
            brain_scope=brain_scope,
            trace_id=trace_id,
        )

    def query_temporal_agenda_state(self, *, session_id: str) -> dict:
        """Delegate Feature 55 temporal agenda query to kernel.service."""
        kernel = self._require_kernel_service("query_temporal_agenda_state")
        return self._require_kernel_method(
            kernel,
            "query_temporal_agenda_state",
            "query_temporal_agenda_state",
        )(session_id=session_id)

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
        """Delegate Feature 56 cognitive conflict detection to kernel.service."""
        kernel = self._require_kernel_service("detect_cognitive_conflicts")
        return self._require_kernel_method(
            kernel,
            "detect_cognitive_conflicts",
            "detect_cognitive_conflicts",
        )(
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

    def query_cognitive_conflicts(self, *, session_id: str) -> dict:
        """Delegate Feature 56 cognitive conflict query to kernel.service."""
        kernel = self._require_kernel_service("query_cognitive_conflicts")
        return self._require_kernel_method(
            kernel,
            "query_cognitive_conflicts",
            "query_cognitive_conflicts",
        )(session_id=session_id)

    def get_self_model_snapshot(self, session_id: str) -> Optional[dict]:
        """Get self model snapshot"""
        kernel = self._require_kernel_service("get_self_model_snapshot")
        return self._require_kernel_method(
            kernel,
            "get_self_model_snapshot",
            "get_self_model_snapshot",
        )(session_id)

    def get_temporal_snapshot(self, session_id: str) -> Optional[dict]:
        """Get temporal agenda snapshot"""
        kernel = self._require_kernel_service("get_temporal_snapshot")
        return self._require_kernel_method(kernel, "get_temporal_snapshot", "get_temporal_snapshot")(session_id)

    def get_nine_question_state(self) -> Optional[dict]:
        """Return the shared nine-question baseline state."""
        kernel = self._require_kernel_service("get_nine_question_state")
        return self._require_kernel_method(
            kernel,
            "get_nine_question_state",
            "get_nine_question_state",
        )()

    def consult_external_brain(
        self,
        *,
        session_id: str,
        user_input: str,
        context: Optional[dict] = None,
        turn_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Delegate G1 external-brain consultation to kernel.service."""
        kernel = self._require_kernel_service("consult_external_brain")
        return self._require_kernel_method(
            kernel,
            "consult_external_brain",
            "consult_external_brain",
        )(
            session_id=session_id,
            user_input=user_input,
            context=context,
            turn_id=turn_id,
            trace_id=trace_id,
        )

    def get_core_architecture_snapshot(self) -> dict:
        """Delegate G2 architecture query to kernel.service."""
        kernel = self._require_kernel_service("get_core_architecture_snapshot")
        return self._require_kernel_method(
            kernel,
            "get_core_architecture_snapshot",
            "get_core_architecture_snapshot",
        )()

    def control_brain_daemon(
        self,
        *,
        action: str,
        session_id: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        max_consecutive_failures: Optional[int] = None,
        run_background: bool = False,
    ) -> dict:
        """Delegate G3 BrainDaemon control to kernel.service."""
        kernel = self._require_kernel_service("control_brain_daemon")
        return self._require_kernel_method(
            kernel,
            "control_brain_daemon",
            "control_brain_daemon",
        )(
            action=action,
            session_id=session_id,
            interval_seconds=interval_seconds,
            max_consecutive_failures=max_consecutive_failures,
            run_background=run_background,
        )

    def get_brain_daemon_status(self) -> dict:
        """Delegate G3 BrainDaemon status query to kernel.service."""
        kernel = self._require_kernel_service("get_brain_daemon_status")
        return self._require_kernel_method(
            kernel,
            "get_brain_daemon_status",
            "get_brain_daemon_status",
        )()

    def observe_environment_awareness(
        self,
        *,
        session_id: str,
        turn_id: Optional[str] = None,
        raw_signals: Optional[list[str]] = None,
        source_conflict_field: str = "memory_used_ratio",
        source_conflict_samples: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Delegate G4 environment-awareness observation to kernel.service."""
        kernel = self._require_kernel_service("observe_environment_awareness")
        return self._require_kernel_method(
            kernel,
            "observe_environment_awareness",
            "observe_environment_awareness",
        )(
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
    ) -> dict:
        """Delegate G4 environment-awareness snapshot query to kernel.service."""
        kernel = self._require_kernel_service("query_environment_awareness_snapshots")
        return self._require_kernel_method(
            kernel,
            "query_environment_awareness_snapshots",
            "query_environment_awareness_snapshots",
        )(session_id=session_id, limit=limit)

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
        """Delegate G5 resource negotiation creation to kernel.service."""
        kernel = self._require_kernel_service("create_resource_negotiation_request")
        return await self._require_kernel_method(
            kernel,
            "create_resource_negotiation_request",
            "create_resource_negotiation_request",
        )(
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
    ) -> dict:
        """Delegate G5 resource negotiation query to kernel.service."""
        kernel = self._require_kernel_service("query_resource_negotiation_requests")
        return self._require_kernel_method(
            kernel,
            "query_resource_negotiation_requests",
            "query_resource_negotiation_requests",
        )(session_id=session_id, task_id=task_id, status=status)

    async def resolve_resource_negotiation_request(
        self,
        *,
        session_id: str,
        negotiation_id: str,
        approved: bool,
        resolution_note: str,
        granted_asset: Optional[str] = None,
    ) -> dict:
        """Delegate G5 resource negotiation resolution to kernel.service."""
        kernel = self._require_kernel_service("resolve_resource_negotiation_request")
        return await self._require_kernel_method(
            kernel,
            "resolve_resource_negotiation_request",
            "resolve_resource_negotiation_request",
        )(
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
    ) -> dict:
        """Delegate G6 identity kernel mounting to kernel.service."""
        kernel = self._require_kernel_service("mount_identity_kernel")
        return self._require_kernel_method(
            kernel,
            "mount_identity_kernel",
            "mount_identity_kernel",
        )(
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
    ) -> dict:
        """Delegate G6 identity anchor query to kernel.service."""
        kernel = self._require_kernel_service("query_identity_anchors")
        return self._require_kernel_method(
            kernel,
            "query_identity_anchors",
            "query_identity_anchors",
        )(
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
    ) -> dict:
        """Delegate G6 identity change evaluation to kernel.service."""
        kernel = self._require_kernel_service("evaluate_identity_change")
        return self._require_kernel_method(
            kernel,
            "evaluate_identity_change",
            "evaluate_identity_change",
        )(
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
    ) -> dict:
        """Delegate G7 inter-agent conflict creation to kernel.service."""
        kernel = self._require_kernel_service("create_inter_agent_conflict")
        return await self._require_kernel_method(
            kernel,
            "create_inter_agent_conflict",
            "create_inter_agent_conflict",
        )(
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
    ) -> dict:
        """Delegate G7 inter-agent conflict query to kernel.service."""
        kernel = self._require_kernel_service("query_inter_agent_conflict")
        return self._require_kernel_method(
            kernel,
            "query_inter_agent_conflict",
            "query_inter_agent_conflict",
        )(session_id=session_id, conflict_id=conflict_id, task_id=task_id)

    async def reassign_inter_agent_conflict(
        self,
        *,
        session_id: str,
        conflict_id: str,
        task_id: str,
        failed_agent_id: str,
        failure_reason: str,
    ) -> dict:
        """Delegate G7 inter-agent reassignment to kernel.service."""
        kernel = self._require_kernel_service("reassign_inter_agent_conflict")
        return await self._require_kernel_method(
            kernel,
            "reassign_inter_agent_conflict",
            "reassign_inter_agent_conflict",
        )(
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
    ) -> dict:
        """Delegate G8 SafetyGate validation to kernel.service."""
        kernel = self._require_kernel_service("validate_safety_gate_action")
        return self._require_kernel_method(
            kernel,
            "validate_safety_gate_action",
            "validate_safety_gate_action",
        )(
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
    ) -> dict:
        """Delegate G8 SafetyGate decision query to kernel.service."""
        kernel = self._require_kernel_service("query_safety_gate_decision")
        return self._require_kernel_method(
            kernel,
            "query_safety_gate_decision",
            "query_safety_gate_decision",
        )(session_id=session_id, decision_id=decision_id)

    def confirm_safety_gate_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
        confirmed_by: str,
        confirmation_context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Delegate G8 SafetyGate confirmation to kernel.service."""
        kernel = self._require_kernel_service("confirm_safety_gate_decision")
        return self._require_kernel_method(
            kernel,
            "confirm_safety_gate_decision",
            "confirm_safety_gate_decision",
        )(
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
    ) -> dict:
        """Delegate G9 ThoughtSandbox simulation to kernel.service."""
        kernel = self._require_kernel_service("run_thought_sandbox_simulation")
        return self._require_kernel_method(
            kernel,
            "run_thought_sandbox_simulation",
            "run_thought_sandbox_simulation",
        )(
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
    ) -> dict:
        """Delegate G9 ThoughtSandbox query to kernel.service."""
        kernel = self._require_kernel_service("query_thought_sandbox_outcome")
        return self._require_kernel_method(
            kernel,
            "query_thought_sandbox_outcome",
            "query_thought_sandbox_outcome",
        )(session_id=session_id, outcome_id=outcome_id)

    def ingest_sensory_signal(
        self,
        *,
        session_id: str,
        source: str,
        payload: str,
        domain: str = "environment",
        source_observations: Optional[list[dict[str, Any]]] = None,
    ) -> dict:
        """Delegate G10 sensory chain to kernel.service."""
        kernel = self._require_kernel_service("ingest_sensory_signal")
        return self._require_kernel_method(
            kernel,
            "ingest_sensory_signal",
            "ingest_sensory_signal",
        )(
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
    ) -> dict:
        """Delegate G10 sensory event query to kernel.service."""
        kernel = self._require_kernel_service("query_sensory_event")
        return self._require_kernel_method(
            kernel,
            "query_sensory_event",
            "query_sensory_event",
        )(session_id=session_id, event_id=event_id)

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
        """Delegate G11 expectation registration to kernel.service."""
        kernel = self._require_kernel_service("register_experience_expectation")
        return self._require_kernel_method(
            kernel,
            "register_experience_expectation",
            "register_experience_expectation",
        )(
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
    ) -> dict:
        """Delegate G11 outcome binding to kernel.service."""
        kernel = self._require_kernel_service("bind_experience_outcome")
        return self._require_kernel_method(
            kernel,
            "bind_experience_outcome",
            "bind_experience_outcome",
        )(
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
    ) -> dict:
        """Delegate G11 outcome binding query to kernel.service."""
        kernel = self._require_kernel_service("query_experience_binding")
        return self._require_kernel_method(
            kernel,
            "query_experience_binding",
            "query_experience_binding",
        )(session_id=session_id, binding_id=binding_id)

    def rank_goals_with_experience(
        self,
        *,
        session_id: str,
        candidate_goals: list[dict[str, Any]],
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Delegate G11 goal ranking to kernel.service."""
        kernel = self._require_kernel_service("rank_goals_with_experience")
        return self._require_kernel_method(
            kernel,
            "rank_goals_with_experience",
            "rank_goals_with_experience",
        )(session_id=session_id, candidate_goals=candidate_goals, context=context)

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
        """Delegate G12 dynamic tool discovery to kernel.service."""
        kernel = self._require_kernel_service("learn_dynamic_tool_capability")
        return self._require_kernel_method(
            kernel,
            "learn_dynamic_tool_capability",
            "learn_dynamic_tool_capability",
        )(
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
    ) -> dict:
        """Delegate G12 tool knowledge query to kernel.service."""
        kernel = self._require_kernel_service("query_tool_knowledge_record")
        return self._require_kernel_method(
            kernel,
            "query_tool_knowledge_record",
            "query_tool_knowledge_record",
        )(session_id=session_id, knowledge_id=knowledge_id)

    def query_capability_registration(
        self,
        *,
        session_id: str,
        capability_id: str,
    ) -> dict:
        """Delegate G12 capability registration query to kernel.service."""
        kernel = self._require_kernel_service("query_capability_registration")
        return self._require_kernel_method(
            kernel,
            "query_capability_registration",
            "query_capability_registration",
        )(session_id=session_id, capability_id=capability_id)

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
        """Delegate G13 value engine evaluation to kernel.service."""
        kernel = self._require_kernel_service("evaluate_value_engine")
        return self._require_kernel_method(
            kernel,
            "evaluate_value_engine",
            "evaluate_value_engine",
        )(
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
    ) -> dict:
        """Delegate G13 value decision query to kernel.service."""
        kernel = self._require_kernel_service("query_value_engine_decision")
        return self._require_kernel_method(
            kernel,
            "query_value_engine_decision",
            "query_value_engine_decision",
        )(session_id=session_id, decision_id=decision_id)

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
        """Delegate G14 self-refactor proposal to kernel.service."""
        kernel = self._require_kernel_service("submit_self_refactor_proposal")
        return self._require_kernel_method(
            kernel,
            "submit_self_refactor_proposal",
            "submit_self_refactor_proposal",
        )(
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
    ) -> dict:
        """Delegate G14 self-refactor query to kernel.service."""
        kernel = self._require_kernel_service("query_self_refactor_proposal")
        return self._require_kernel_method(
            kernel,
            "query_self_refactor_proposal",
            "query_self_refactor_proposal",
        )(session_id=session_id, proposal_id=proposal_id)

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
        """Delegate G15 isolated self-coding cycle to kernel.service."""
        kernel = self._require_kernel_service("run_self_coding_cycle")
        return self._require_kernel_method(
            kernel,
            "run_self_coding_cycle",
            "run_self_coding_cycle",
        )(
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
    ) -> dict:
        """Delegate G15 self-coding patch query to kernel.service."""
        kernel = self._require_kernel_service("query_self_coding_patch")
        return self._require_kernel_method(
            kernel,
            "query_self_coding_patch",
            "query_self_coding_patch",
        )(session_id=session_id, patch_id=patch_id)

    async def run_preference_judgment(
        self,
        *,
        session_id: str,
        detected_state: dict[str, Any],
        detection_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Delegate G16 preference judgment to kernel.service."""
        kernel = self._require_kernel_service("run_preference_judgment")
        return await self._require_kernel_method(
            kernel,
            "run_preference_judgment",
            "run_preference_judgment",
        )(
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
    ) -> dict:
        """Delegate G16 preference confirmation to kernel.service."""
        kernel = self._require_kernel_service("confirm_preference_case")
        return await self._require_kernel_method(
            kernel,
            "confirm_preference_case",
            "confirm_preference_case",
        )(
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
    ) -> dict:
        """Delegate G16 preference query to kernel.service."""
        kernel = self._require_kernel_service("query_preference_record")
        return await self._require_kernel_method(
            kernel,
            "query_preference_record",
            "query_preference_record",
        )(session_id=session_id, preference_id=preference_id)

    async def revoke_preference_record(
        self,
        *,
        session_id: str,
        preference_id: str,
        reason: str,
        user_id: str,
    ) -> dict:
        """Delegate G16 preference revocation to kernel.service."""
        kernel = self._require_kernel_service("revoke_preference_record")
        return await self._require_kernel_method(
            kernel,
            "revoke_preference_record",
            "revoke_preference_record",
        )(session_id=session_id, preference_id=preference_id, reason=reason, user_id=user_id)

    async def intercept_extreme_signal(
        self,
        *,
        session_id: str,
        signal_content: str,
        signal_source: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Delegate G16 extreme signal interception to kernel.service."""
        kernel = self._require_kernel_service("intercept_extreme_signal")
        return await self._require_kernel_method(
            kernel,
            "intercept_extreme_signal",
            "intercept_extreme_signal",
        )(
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
    ) -> dict:
        """Delegate G16 attack sample marking to kernel.service."""
        kernel = self._require_kernel_service("mark_attack_sample")
        return await self._require_kernel_method(
            kernel,
            "mark_attack_sample",
            "mark_attack_sample",
        )(
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
    ) -> dict:
        """Delegate G16 similar attack detection to kernel.service."""
        kernel = self._require_kernel_service("detect_similar_attack")
        return await self._require_kernel_method(
            kernel,
            "detect_similar_attack",
            "detect_similar_attack",
        )(
            session_id=session_id,
            signal_content=signal_content,
            similarity_threshold=similarity_threshold,
        )

    def get_runtime_overview(
        self,
        session_id: str = "zentex-default-session",
        weight_assembler: Any = None,
    ) -> dict:
        """Delegate to kernel service; must fail if kernel is unavailable.
        
        Standard Redline:
        - Honest Reporting: Do not return 'fake' empty dictionaries if the kernel
          is missing or if the implementation is removed. An empty dashboard is 
          a deception that masks engine failure.
        """
        kernel = self._require_kernel_service("get_runtime_overview")
        try:
            return self._require_kernel_method(
                kernel,
                "get_runtime_overview",
                "get_runtime_overview",
            )(
                session_id=session_id,
                weight_assembler=weight_assembler,
            )
        except Exception as exc:
            logger.exception("[WEBCONSOLE] Failed to retrieve runtime overview from kernel")
            raise RuntimeError(f"Kernel Runtime Overview failure: {exc}") from exc
