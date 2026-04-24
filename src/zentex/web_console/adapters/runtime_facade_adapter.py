from __future__ import annotations
"""Runtime Facade Adapter - Translates old runtime interface to new Facade

This adapter provides a compatibility bridge between:
- Old code: `runtime = get_runtime(request); runtime.active_session`
- New design: `facade = get_kernel_service_facade(request); await facade.get_session_manager()`

Purpose:
- Allows gradual migration from old runtime -> new Facade
- Minimal changes to existing routes
- Fast path to Phase 1 completion

This adapter lazily wraps Facade calls when old runtime interface is accessed.

Note: This adapter is deprecated and should be removed once all route handlers
are migrated to use KernelServiceFacade directly.
"""


from typing import Any, Optional
import asyncio

# Import KernelService for type checking only
try:
    from zentex.kernel.service import KernelService
except ImportError:
    KernelService = None  # type: ignore


class RuntimeFacadeAdapter:
    """Adapter that maps old BrainRuntime interface to new KernelServiceFacade
    
    When old code does: `runtime.active_session`
    This adapter intercepts and calls: `facade.get_session_manager().get_active_session()`
    """
    
    def __init__(self, facade: Any, original_kernel_service: Optional[Any] = None):
        """
        Args:
            facade: The new KernelServiceFacade instance
            original_kernel_service: The original KernelService (fallback for unmapped properties)
        """
        self._facade = facade
        self._original_kernel_service = original_kernel_service
        self._cached_session = None
        self._cached_state = None
    
    # ========== Old BrainRuntime Interface Mappings ==========
    
    @property
    def active_session(self) -> Any:
        """Map: active_session -> facade.session_manager.get_active_session()
        
        Returns async value - caller must handle properly
        """
        if self._cached_session is not None:
            return self._cached_session
        
        # Return a deferred callable that wraps the async call
        async def _get_session():
            session_mgr = self._facade.get_session_manager()
            return await session_mgr.get_active_session()
        
        return _get_session
    
    @property
    def nine_question_state(self) -> Any:
        """Map: nine_question_state -> facade.state_manager.get_state()"""
        if self._cached_state is not None:
            return self._cached_state
        
        async def _get_state():
            state_mgr = self._facade.get_nine_question_state_manager()
            raise NotImplementedError("nine_question_state mapping is incomplete on adapter facade.")
        
        return _get_state
    
    @property
    def nine_question_router(self) -> Any:
        """Map: nine_question_router -> facade.event_bus"""
        return self._facade.get_event_bus()
    
    # ========== Fallback to original kernel service for unmapped properties ==========
    
    def __getattr__(self, name: str) -> Any:
        """Fallback: unmapped properties delegate to original kernel service"""
        if self._original_kernel_service is not None:
            return getattr(self._original_kernel_service, name)
        raise AttributeError(
            f"RuntimeFacadeAdapter has no attribute '{name}'. "
            f"This adapter is deprecated - use KernelServiceFacade directly."
        )
