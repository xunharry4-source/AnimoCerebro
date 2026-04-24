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
