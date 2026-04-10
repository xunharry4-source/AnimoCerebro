"""
Session Lifecycle Manager

Purpose:
    Manages session lifecycle including creation, activity tracking,
    expiration detection, and automatic cleanup.
    Prevents memory leaks from accumulated inactive sessions.
    
Responsibilities:
    - Track session activity and state
    - Detect and clean up expired sessions
    - Enforce maximum session limits
    - Provide session statistics for monitoring
    
Not Responsible For:
    - Session business logic (handled by BrainSession)
    - Session persistence (handled by storage layer)
    - Session authentication (handled by security layer)
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Session lifecycle state."""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    CLOSED = "closed"


@dataclass
class SessionInfo:
    """Session metadata for lifecycle management."""
    session_id: str
    created_at: datetime
    last_activity: datetime
    state: SessionState
    turn_count: int = 0
    memory_usage_mb: float = 0.0
    metadata: Dict = field(default_factory=dict)
    
    def mark_active(self):
        """Mark session as active."""
        self.state = SessionState.ACTIVE
        self.last_activity = datetime.now()
    
    def mark_idle(self):
        """Mark session as idle."""
        if self.state == SessionState.ACTIVE:
            self.state = SessionState.IDLE
    
    def is_expired(self, idle_timeout: timedelta) -> bool:
        """Check if session has exceeded idle timeout."""
        if self.state in [SessionState.EXPIRED, SessionState.CLOSED]:
            return False
        
        idle_time = datetime.now() - self.last_activity
        return idle_time > idle_timeout


class SessionLifecycleManager:
    """
    Manages session lifecycle with automatic cleanup.
    
    Features:
        - Activity tracking
        - Automatic expiration detection
        - Configurable cleanup intervals
        - Session limit enforcement
        - Detailed statistics
    
    Usage:
        >>> manager = SessionLifecycleManager(
        ...     idle_timeout_minutes=30,
        ...     max_sessions=100
        ... )
        >>> manager.register_session("session-123")
        >>> manager.update_activity("session-123")
        >>> expired = manager.get_expired_sessions()
    """
    
    def __init__(
        self,
        idle_timeout_minutes: int = 30,
        max_sessions: int = 100,
        cleanup_interval_minutes: int = 5,
        on_session_expired: Optional[Callable[[str], None]] = None,
    ):
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.max_sessions = max_sessions
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self.on_session_expired = on_session_expired
        
        # Session tracking
        self._session_info: Dict[str, SessionInfo] = {}
        
        # Last cleanup time
        self._last_cleanup: Optional[datetime] = None
        
        logger.info(
            f"SessionLifecycleManager initialized: "
            f"idle_timeout={idle_timeout_minutes}min, "
            f"max_sessions={max_sessions}, "
            f"cleanup_interval={cleanup_interval_minutes}min"
        )
    
    def register_session(self, session_id: str, metadata: Optional[Dict] = None):
        """
        Register new session.
        
        Args:
            session_id: Unique session identifier
            metadata: Optional session metadata
        """
        now = datetime.now()
        self._session_info[session_id] = SessionInfo(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            state=SessionState.ACTIVE,
            metadata=metadata or {},
        )
        
        logger.debug(f"Session registered: {session_id}")
    
    def update_activity(self, session_id: str):
        """
        Update session last activity time.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._session_info:
            info = self._session_info[session_id]
            info.mark_active()
            logger.debug(f"Session activity updated: {session_id}")
    
    def increment_turn(self, session_id: str):
        """
        Increment session turn count.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._session_info:
            self._session_info[session_id].turn_count += 1
    
    def unregister_session(self, session_id: str):
        """
        Unregister session (manual removal).
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if session was removed, False if not found
        """
        if session_id in self._session_info:
            self._session_info[session_id].state = SessionState.CLOSED
            del self._session_info[session_id]
            logger.debug(f"Session unregistered: {session_id}")
            return True
        return False
    
    def should_cleanup(self) -> bool:
        """Check if cleanup should run based on interval."""
        if self._last_cleanup is None:
            return True
        
        return (datetime.now() - self._last_cleanup) > self.cleanup_interval
    
    def get_expired_sessions(self) -> list[str]:
        """
        Get list of expired session IDs.
        
        Returns:
            List of expired session IDs
        """
        expired = []
        
        for session_id, info in self._session_info.items():
            if info.is_expired(self.idle_timeout):
                expired.append(session_id)
                info.state = SessionState.EXPIRED
        
        if expired:
            logger.info(f"Found {len(expired)} expired sessions")
        
        return expired
    
    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        expired_ids = self.get_expired_sessions()
        cleaned_count = 0
        
        for session_id in expired_ids:
            try:
                # Call callback if provided (may raise exception)
                if self.on_session_expired:
                    try:
                        self.on_session_expired(session_id)
                    except Exception as e:
                        logger.warning(
                            f"Callback failed for {session_id}: {e}"
                        )
                        # Continue with cleanup despite callback failure
                
                # Remove from tracking
                del self._session_info[session_id]
                cleaned_count += 1
                
                logger.info(f"Cleaned expired session: {session_id}")
            
            except Exception as e:
                logger.error(
                    f"Failed to clean session {session_id}: {e}",
                    exc_info=True
                )
        
        self._last_cleanup = datetime.now()
        
        if cleaned_count > 0:
            logger.info(f"Cleanup completed: {cleaned_count} sessions removed")
        
        return cleaned_count
    
    def check_session_limit(self) -> bool:
        """
        Check if session limit is reached.
        
        Returns:
            True if can create new session, False if limit reached
        """
        active_count = sum(
            1 for info in self._session_info.values()
            if info.state in [SessionState.ACTIVE, SessionState.IDLE]
        )
        
        if active_count >= self.max_sessions:
            logger.warning(
                f"Session limit reached: {active_count}/{self.max_sessions}"
            )
            return False
        
        return True
    
    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return sum(
            1 for info in self._session_info.values()
            if info.state in [SessionState.ACTIVE, SessionState.IDLE]
        )
    
    def get_session_stats(self) -> dict:
        """
        Get comprehensive session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        stats = {
            'total_registered': len(self._session_info),
            'active': 0,
            'idle': 0,
            'expired': 0,
            'closed': 0,
            'total_turns': 0,
            'oldest_session_age_minutes': 0,
            'avg_turns_per_session': 0,
        }
        
        now = datetime.now()
        ages = []
        
        for info in self._session_info.values():
            if info.state == SessionState.ACTIVE:
                stats['active'] += 1
            elif info.state == SessionState.IDLE:
                stats['idle'] += 1
            elif info.state == SessionState.EXPIRED:
                stats['expired'] += 1
            elif info.state == SessionState.CLOSED:
                stats['closed'] += 1
            
            stats['total_turns'] += info.turn_count
            
            # Calculate age
            age = (now - info.created_at).total_seconds() / 60
            ages.append(age)
        
        if ages:
            stats['oldest_session_age_minutes'] = max(ages)
            stats['avg_turns_per_session'] = (
                stats['total_turns'] / len(self._session_info)
            )
        
        return stats
    
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get session information.
        
        Args:
            session_id: Session identifier
        
        Returns:
            SessionInfo or None if not found
        """
        return self._session_info.get(session_id)
    
    def clear_all(self):
        """Clear all session tracking data."""
        self._session_info.clear()
        self._last_cleanup = None
        logger.info("All session tracking data cleared")
