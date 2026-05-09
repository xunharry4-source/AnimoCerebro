from __future__ import annotations
"""Unified DI Container for Web Console

Manages object lifecycle and provides FastAPI Depends-friendly factories.
Replaces scattered get_* functions in dependencies.py.
"""


import logging
from typing import TYPE_CHECKING, Callable, Any, Dict, List, Optional, Union
from functools import lru_cache

if TYPE_CHECKING:
    from fastapi import Request

    from .contracts.kernel_service import KernelServiceFacade

logger = logging.getLogger(__name__)


class WebConsoleContainer:
    """Application-level DI container
    
    Manages the lifecycle of KernelServiceFacade and provides
    Depends-friendly factories for FastAPI route handlers.
    
    Usage:
        # At app startup
        WebConsoleContainer.initialize()
        
        # In route handlers
        @app.get("/api/sessions")
        async def list_sessions(
            session_mgr = Depends(WebConsoleContainer.get_session_manager_depends)
        ):
            sessions = await session_mgr.list_active_sessions()
            return {"sessions": sessions}
    """

    _kernel_service: Optional[KernelServiceFacade] = None
    _initialized = False

    @classmethod
    def initialize(
        cls,
        kernel_service: Optional[KernelServiceFacade] = None,
    ):
        """Initialize container at application startup

        Standard Redline:
        - Fail-Closed: If the KernelServiceFacade fails to initialize, this method
          must propagate the exception to prevent the system from starting in a
          zombie state.
        """
        if kernel_service is None:
            from .contracts.kernel_service import AppConfig
            from .kernel_service_impl import DefaultKernelServiceFacade
            from zentex.kernel.workspace_policy import get_q1_default_analysis_workspace

            # Any initialization failure here correctly propagates up
            kernel_service = DefaultKernelServiceFacade(
                config=AppConfig(default_workspace=str(get_q1_default_analysis_workspace()))
            )

        cls._kernel_service = kernel_service
        cls._initialized = True
        logger.info("WebConsoleContainer initialized")

    @classmethod
    def get_kernel_service(cls) -> KernelServiceFacade:
        """Get singleton KernelServiceFacade

        Raises:
            RuntimeError: If not initialized
        """
        if cls._kernel_service is None:
            raise RuntimeError(
                "WebConsoleContainer not initialized. "
                "Call WebConsoleContainer.initialize() in app startup."
            )
        return cls._kernel_service

    # ========== Depends Factories ==========

    @staticmethod
    def get_plugin_registry_depends() -> Callable:
        """FastAPI Depends factory for plugin registry"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_plugin_registry()

        return _get

    @staticmethod
    def get_cognitive_tools_depends() -> Callable:
        """FastAPI Depends factory for cognitive tools"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_cognitive_tools()

        return _get

    @staticmethod
    def get_session_manager_depends() -> Callable:
        """FastAPI Depends factory for session manager"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_session_manager()

        return _get

    @staticmethod
    def get_nine_question_state_manager_depends() -> Callable:
        """FastAPI Depends factory for nine-question state manager"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_nine_question_state_manager()

        return _get

    @staticmethod
    def get_event_bus_depends() -> Callable:
        """FastAPI Depends factory for event bus"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_event_bus()

        return _get

    @staticmethod
    def get_config_depends() -> Callable:
        """FastAPI Depends factory for config"""

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_config()

        return _get
