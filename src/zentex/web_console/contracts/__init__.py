"""Web Console Contracts & Facades

This package defines the dependency contracts and facades for web_console,
isolating it from direct dependencies on core/runtime modules.

Public API:
- KernelServiceFacade: Main entry point (Facade pattern)
- SessionManager, NineQuestionStateManager, EventBus: Service contracts
- SessionSnapshot, NineQuestionStateSnapshot, AppConfig: DTOs
"""

from .kernel_service import (
    KernelServiceFacade,
    SessionSnapshot,
    NineQuestionStateSnapshot,
    AppConfig,
)
from .session_manager import SessionManager
from .state_manager import NineQuestionStateManager
from .event_bus import EventBus, EventPublishResult, Subscription

__all__ = [
    "KernelServiceFacade",
    "SessionSnapshot",
    "NineQuestionStateSnapshot",
    "AppConfig",
    "SessionManager",
    "NineQuestionStateManager",
    "EventBus",
    "EventPublishResult",
    "Subscription",
]
