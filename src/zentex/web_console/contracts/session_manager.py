from __future__ import annotations
"""Session Management Contract

Defines the interface for session lifecycle management, replacing
direct access to runtime.active_session.
"""


from abc import ABC, abstractmethod
from typing import List

from .kernel_service import SessionSnapshot


class SessionManager(ABC):
    """Session lifecycle management
    
    Replaces direct access to runtime.active_session. Handles creation,
    retrieval, and persistence of session state to SQLite.
    
    All methods are async-safe for use in FastAPI handlers.
    """

    @abstractmethod
    async def get_active_session(self, session_id: str) -> SessionSnapshot:
        """Get an active session by ID
        
        Args:
            session_id: Session UUID
            
        Returns:
            SessionSnapshot: Current session state
            
        Raises:
            ValueError: If session not found or inactive
        """
        pass

    @abstractmethod
    async def create_session(
        self,
        workspace: str,
        session_id: Optional[str] = None,
    ) -> SessionSnapshot:
        """Create a new session
        
        Args:
            workspace: Default workspace path for session
            session_id: Optional UUID; generated if omitted
            
        Returns:
            SessionSnapshot: Newly created session
        """
        pass

    @abstractmethod
    async def list_active_sessions(self) -> List[SessionSnapshot]:
        """List all active sessions
        
        Returns:
            List of SessionSnapshot for all active sessions
        """
        pass

    @abstractmethod
    async def update_session_state(
        self,
        session_id: str,
        **updates,
    ) -> SessionSnapshot:
        """Update session state atomically
        
        Args:
            session_id: Session to update
            **updates: Fields to update (last_turn_id, metadata, etc.)
            
        Returns:
            SessionSnapshot: Updated session
        """
        pass

    @abstractmethod
    async def persist_session(self, session: SessionSnapshot) -> None:
        """Persist session to SQLite
        
        Args:
            session: SessionSnapshot to persist
        """
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Delete a session
        
        Args:
            session_id: Session to delete
        """
        pass

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """Mark session as closed (soft delete)
        
        Args:
            session_id: Session to close
        """
        pass
