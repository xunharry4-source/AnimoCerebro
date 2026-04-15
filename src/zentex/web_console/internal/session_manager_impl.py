"""Session Manager Implementation"""

from __future__ import annotations

from uuid import uuid4
from datetime import datetime
from typing import List
import logging

from ..contracts.session_manager import SessionManager
from ..contracts.kernel_service import SessionSnapshot
from ..contracts.event_bus import EventBus
from ..cache_manager import CacheNamespace, WebConsoleCacheManager
from .session_store import SQLiteSessionStore

logger = logging.getLogger(__name__)


class SessionManagerImpl(SessionManager):
    """Implementation of SessionManager using SQLite store"""

    def __init__(
        self,
        store: SQLiteSessionStore,
        event_bus: EventBus,
        cache_manager: WebConsoleCacheManager | None = None,
    ):
        self._store = store
        self._event_bus = event_bus
        self._cache_manager = cache_manager

    async def get_active_session(self, session_id: str) -> SessionSnapshot:
        """Get an active session by ID"""
        if self._cache_manager is not None:
            cached = self._cache_manager.get(CacheNamespace.SESSION, session_id)
            if isinstance(cached, SessionSnapshot):
                return cached
        session = await self._store.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found or inactive")
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.SESSION, session_id, session)
        return session

    async def create_session(
        self,
        workspace: str,
        session_id: str | None = None,
    ) -> SessionSnapshot:
        """Create a new session"""
        session_id = session_id or str(uuid4())
        session = SessionSnapshot(
            session_id=session_id,
            state_id=str(uuid4()),
            workspace=workspace,
            created_at=datetime.utcnow(),
        )

        await self._store.save(session)
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.SESSION, session_id, session)

        # Emit event
        await self._event_bus.publish(
            EventBus.SESSION_CREATED,
            {"session": session.model_dump()},
            session_id=session_id,
        )

        logger.info(f"Created session {session_id} in {workspace}")
        return session

    async def list_active_sessions(self) -> List[SessionSnapshot]:
        """List all active sessions"""
        return await self._store.list_active()

    async def update_session_state(
        self,
        session_id: str,
        **updates,
    ) -> SessionSnapshot:
        """Update session state"""
        session = await self.get_active_session(session_id)

        # Apply updates
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)

        await self._store.save(session)
        logger.debug(f"Updated session {session_id}: {updates}")
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.SESSION, session_id, session)
        return session

    async def persist_session(self, session: SessionSnapshot) -> None:
        """Persist session to store"""
        await self._store.save(session)
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.SESSION, session.session_id, session)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session"""
        await self._store.delete(session_id)
        if self._cache_manager is not None:
            self._cache_manager.invalidate_namespace(CacheNamespace.SESSION, key_prefix=session_id)

        await self._event_bus.publish(
            EventBus.SESSION_CLOSED,
            {"session_id": session_id},
            session_id=session_id,
        )

        logger.info(f"Deleted session {session_id}")

    async def close_session(self, session_id: str) -> None:
        """Mark session as closed"""
        await self.delete_session(session_id)
