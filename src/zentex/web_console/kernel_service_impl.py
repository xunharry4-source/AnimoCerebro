"""Default Kernel Service Facade Implementation

Adapter pattern connecting web_console to kernel.service.
Gradually replaces direct kernel/runtime dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .contracts.kernel_service import (
    KernelServiceFacade,
    AppConfig,
)
from .cache_manager import WebConsoleCacheManager
from .contracts.session_manager import SessionManager
from .contracts.state_manager import NineQuestionStateManager
from .contracts.event_bus import EventBus
from .contracts.config_manager import ConfigManager

if TYPE_CHECKING:
    from zentex.kernel.service import KernelService

logger = logging.getLogger(__name__)


class DefaultKernelServiceFacade(KernelServiceFacade):
    """Default implementation using adapter pattern
    
    Strategy:
    - Old interfaces (get_transcript_store) still come from kernel.service
    - New interfaces (session_manager) use new SQL stores
    - Gradual transition during migration from core/runtime
    """

    def __init__(
        self,
        session_db_path: str = "./data/sessions.db",
        transcript_db_path: str = "./data/transcripts.db",
        config: AppConfig | None = None,
    ):
        """Initialize facade with storage backends

        Args:
            session_db_path: SQLite path for sessions
            transcript_db_path: SQLite path for transcripts
            config: Optional custom config (defaults to AppConfig)
        """
        # Lazy import to avoid circular dependencies
        from .internal.event_bus_impl import InProcessEventBus
        from .internal.session_store import SQLiteSessionStore
        from .internal.state_store import SQLiteStateStore
        from .internal.session_manager_impl import SessionManagerImpl
        from .internal.state_manager_impl import NineQuestionStateManagerImpl

        # Backend: old runtime service (lazy loaded on first use)
        self._runtime_service: Any = None  # Will be loaded on demand
        self._runtime_service_loaded = False

        # New components (SQL persistence)
        self._session_store = SQLiteSessionStore(session_db_path)
        self._state_store = SQLiteStateStore(session_db_path)
        self._event_bus = InProcessEventBus()
        self._cache_manager = WebConsoleCacheManager(
            default_ttl_seconds=(config.cache_ttl_seconds if config is not None else AppConfig().cache_ttl_seconds)
        )

        # New components (Manager services)
        self._session_manager: SessionManager = SessionManagerImpl(
            store=self._session_store,
            event_bus=self._event_bus,
            cache_manager=self._cache_manager,
        )
        self._state_manager: NineQuestionStateManager = NineQuestionStateManagerImpl(
            store=self._state_store,
            event_bus=self._event_bus,
            cache_manager=self._cache_manager,
        )

        # Configuration
        self._config = config or AppConfig(
            default_workspace=".",
            transcript_db_path=transcript_db_path,
            session_db_path=session_db_path,
        )

    def _get_kernel_service(self) -> Any:
        """Lazily load kernel service on first access"""
        if not self._runtime_service_loaded:
            try:
                from zentex.kernel.service import get_service as get_kernel_service
                self._runtime_service = get_kernel_service()
            except Exception as e:
                logger.warning(f"Could not load kernel service: {e}")
                self._runtime_service = None
            self._runtime_service_loaded = True
        return self._runtime_service


    def get_transcript_store(self) -> Any:
        """Get transcript storage (from kernel.service)"""
        kernel_service = self._get_kernel_service()
        if kernel_service:
            return kernel_service.get_transcript_store()
        raise RuntimeError("Kernel service not available - transcript store cannot be accessed")

    def get_session_transcript_store(self, session_id: str) -> Any:
        """Get transcript storage for a specific kernel session."""
        kernel_service = self._get_kernel_service()
        if kernel_service and hasattr(kernel_service, "get_session_transcript_store"):
            return kernel_service.get_session_transcript_store(session_id)
        return None

    def get_nine_question_audit_store(self, session_id: str) -> Any:
        """Get the session-scoped nine-question audit transcript store."""
        kernel_service = self._get_kernel_service()
        if kernel_service and hasattr(kernel_service, "get_nine_question_audit_store"):
            return kernel_service.get_nine_question_audit_store(session_id)
        return None

    def get_plugin_registry(self) -> Any:
        """Get plugin registry from plugins.service"""
        # Plugin registry is now managed by plugins.service, not kernel
        # This method should be deprecated in favor of direct plugins.service usage
        raise NotImplementedError(
            "get_plugin_registry is deprecated. "
            "Use plugins.service.SystemPluginService directly or inject it via app.state.plugin_service"
        )

    def get_cognitive_tools(self) -> Any:
        """Get cognitive tool registry from plugins.service"""
        # Cognitive tools are now managed by plugins.service
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

    def get_config(self) -> AppConfig:
        """Get application configuration"""
        return self._config

    # ========== Session State Queries (Migration Helpers) ==========

    def list_active_sessions(self) -> list[str]:
        """List active session IDs"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.list_active_sessions()
        return []

    def get_session_meta(self, session_id: str) -> dict | None:
        """Get kernel session metadata."""
        kernel = self._get_kernel_service()
        if kernel and hasattr(kernel, "get_session_meta"):
            return kernel.get_session_meta(session_id)
        return None

    def create_kernel_session(self, user_id: str = "") -> str:
        """Create a kernel-backed session."""
        kernel = self._get_kernel_service()
        if kernel and hasattr(kernel, "create_session"):
            return str(kernel.create_session(user_id=user_id))
        raise RuntimeError("Kernel service not available - cannot create kernel session")

    def ensure_nine_questions_bootstrap(self, session_id: str, *, force: bool = False) -> Any:
        """Run kernel nine-question bootstrap."""
        kernel = self._get_kernel_service()
        if kernel and hasattr(kernel, "ensure_nine_questions_bootstrap"):
            return kernel.ensure_nine_questions_bootstrap(session_id, force=force)
        raise RuntimeError("Kernel service not available - cannot bootstrap nine questions")

    def rerun_nine_questions_from(self, session_id: str, question_id: str) -> Any:
        """Re-run a single nine-question and its downstream chain."""
        kernel = self._get_kernel_service()
        if kernel and hasattr(kernel, "rerun_nine_questions_from"):
            return kernel.rerun_nine_questions_from(session_id, question_id)
        raise RuntimeError("Kernel service not available - cannot rerun single nine question")

    def get_session_state(self, session_id: str) -> dict | None:
        """Get comprehensive session state"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.get_session_state(session_id)
        return None

    def get_working_memory(self, session_id: str) -> list[dict] | None:
        """Get working memory snapshot"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.get_working_memory(session_id)
        return None

    def get_self_model_snapshot(self, session_id: str) -> dict | None:
        """Get self model snapshot"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.get_self_model_snapshot(session_id)
        return None

    def get_temporal_snapshot(self, session_id: str) -> dict | None:
        """Get temporal agenda snapshot"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.get_temporal_snapshot(session_id)
        return None

    def get_nine_question_state(self, session_id: str) -> dict | None:
        """Get nine-question state dict"""
        kernel = self._get_kernel_service()
        if kernel:
            return kernel.get_nine_question_state(session_id)
        return None

    def get_runtime_overview(
        self,
        session_id: str = "zentex-default-session",
        weight_assembler: Any = None,
    ) -> dict:
        """Delegate to kernel service; return empty overview when kernel is unavailable."""
        kernel = self._get_kernel_service()
        if kernel and hasattr(kernel, "get_runtime_overview"):
            return kernel.get_runtime_overview(
                session_id=session_id,
                weight_assembler=weight_assembler,
            )
        return {
            "runtime": {},
            "session": None,
            "working_memory": {"slots": []},
            "metacognition": {},
            "living_self_model": {},
            "temporal_agenda": {},
            "recent_entries": [],
            "last_intervention": None,
            "weights": {},
        }
