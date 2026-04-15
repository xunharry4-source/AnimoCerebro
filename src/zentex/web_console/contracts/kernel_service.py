"""Core Facade & DTO Definitions

Defines the main dependency contract for web_console, hiding complexity of
kernel.service and providing a stable interface for web_console modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .session_manager import SessionManager
    from .state_manager import NineQuestionStateManager
    from .event_bus import EventBus
    from .config_manager import ConfigManager


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
    last_turn_id: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess-123",
                "state_id": "state-456",
                "workspace": "/home/user/project",
                "created_at": "2026-04-13T10:30:00Z",
                "question_drivers": ["q1", "q2"],
            }
        }


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
    last_refresh_reason: str | None = None
    snapshot_version: int = 9  # Legacy field for compatibility
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "version": 1,
                "revision": 5,
                "dirty_questions": ["q3", "q5"],
                "last_refresh_reason": "trajectory_bounded",
                "snapshot_version": 9,
            }
        }


class AppConfig(BaseModel):
    """Application configuration (replaces scattered runtime configs)
    
    Centralizes all configuration needed by web_console and its dependencies.
    """

    default_workspace: str = "."
    transcript_db_path: str = "./data/transcripts.db"
    session_db_path: str = "./data/sessions.db"
    cache_ttl_seconds: int = 3600
    log_level: str = "INFO"
    enable_persistence: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "default_workspace": "/work",
                "transcript_db_path": "./data/transcripts.db",
                "session_db_path": "./data/sessions.db",
                "cache_ttl_seconds": 3600,
                "log_level": "INFO",
            }
        }


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
    def get_transcript_store(self) -> Any:
        """Get transcript storage adapter
        
        Returns:
            TranscriptStore: Persisted event log storage
        """
        pass

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
    def get_session_state(self, session_id: str) -> dict | None:
        """Get comprehensive session state (Working Memory, Self Model, Temporal)"""
        pass

    @abstractmethod
    def get_working_memory(self, session_id: str) -> list[dict] | None:
        """Get working memory snapshot"""
        pass

    @abstractmethod
    def get_self_model_snapshot(self, session_id: str) -> dict | None:
        """Get self model snapshot"""
        pass

    @abstractmethod
    def get_temporal_snapshot(self, session_id: str) -> dict | None:
        """Get temporal agenda snapshot"""
        pass

    @abstractmethod
    def get_nine_question_state(self, session_id: str) -> dict | None:
        """Get nine-question state dict"""
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
