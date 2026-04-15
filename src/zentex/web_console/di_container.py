"""Unified DI Container for Web Console

Manages object lifecycle and provides FastAPI Depends-friendly factories.
Replaces scattered get_* functions in dependencies.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Any, Dict
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
        WebConsoleContainer.initialize(
            session_db_path="./data/sessions.db",
            transcript_db_path="./data/transcripts.db",
        )
        
        # In route handlers
        @app.get("/api/sessions")
        async def list_sessions(
            session_mgr = Depends(WebConsoleContainer.get_session_manager_depends)
        ):
            sessions = await session_mgr.list_active_sessions()
            return {"sessions": sessions}
    """

    _kernel_service: KernelServiceFacade | None = None
    _initialized = False

    @classmethod
    def initialize(
        cls,
        kernel_service: KernelServiceFacade | None = None,
        session_db_path: str = "./data/sessions.db",
        transcript_db_path: str = "./data/transcripts.db",
    ):
        """Initialize container at application startup

        Args:
            kernel_service: Optional custom facade (default: DefaultKernelServiceFacade)
            session_db_path: SQLite DB path
            transcript_db_path: SQLite DB path
        """
        if kernel_service is None:
            from .kernel_service_impl import DefaultKernelServiceFacade

            kernel_service = DefaultKernelServiceFacade(
                session_db_path=session_db_path,
                transcript_db_path=transcript_db_path,
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
    def get_transcript_store_depends() -> Callable:
        """FastAPI Depends factory for transcript store

        Returns:
            Callable suitable for Depends()

        Usage:
            Depends(WebConsoleContainer.get_transcript_store_depends())
        """

        async def _get(_ = None):
            container = WebConsoleContainer.get_kernel_service()
            return container.get_transcript_store()

        return _get

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
