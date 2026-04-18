"""Nine-Question State Manager Implementation"""

from __future__ import annotations

from datetime import datetime
from typing import List
import logging

from ..contracts.state_manager import NineQuestionStateManager
from ..contracts.kernel_service import NineQuestionStateSnapshot
from ..contracts.event_bus import EventBus
from ..cache_manager import CacheNamespace, WebConsoleCacheManager
from .state_store import SQLiteStateStore

logger = logging.getLogger(__name__)


class NineQuestionStateManagerImpl(NineQuestionStateManager):
    """Implementation of NineQuestionStateManager using SQLite store"""

    def __init__(
        self,
        store: SQLiteStateStore,
        event_bus: EventBus,
        cache_manager: WebConsoleCacheManager | None = None,
    ):
        self._store = store
        self._event_bus = event_bus
        self._cache_manager = cache_manager

    async def get_state(self, session_id: str) -> NineQuestionStateSnapshot:
        """Get current nine-question state"""
        if self._cache_manager is not None:
            cached = self._cache_manager.get(CacheNamespace.STATE, session_id)
            if isinstance(cached, NineQuestionStateSnapshot):
                return cached
        state = await self._store.get(session_id)
        if not state:
            raise ValueError(f"Nine-question state for session {session_id} not found")
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.STATE, session_id, state)
        return state

    async def get_dirty_questions(self, session_id: str) -> List[str]:
        """Get list of dirty questions"""
        state = await self.get_state(session_id)
        return state.dirty_questions

    async def get_last_refresh_reason(self, session_id: str) -> str | None:
        """Get reason for last refresh"""
        state = await self.get_state(session_id)
        return state.last_refresh_reason

    async def update_state(
        self,
        session_id: str,
        **updates,
    ) -> NineQuestionStateSnapshot:
        """Update state atomically"""
        state = await self.get_state(session_id)

        # Apply updates and increment revision
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        state.revision += 1
        state.updated_at = datetime.utcnow()

        await self._store.save(session_id, state)
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.STATE, session_id, state)

        # Emit event
        await self._event_bus.publish(
            EventBus.NINE_QUESTION_STATE_CHANGED,
            {"session_id": session_id, "state": state.model_dump()},
            session_id=session_id,
        )

        logger.debug(f"Updated 9Q state for {session_id}, revision={state.revision}")
        return state

    async def mark_questions_dirty(
        self,
        session_id: str,
        question_refs: List[str],
    ) -> NineQuestionStateSnapshot:
        """Mark questions as dirty"""
        state = await self.get_state(session_id)

        # Add to dirty_questions (avoid duplicates)
        existing = set(state.dirty_questions)
        existing.update(question_refs)
        state.dirty_questions = sorted(list(existing))

        await self.update_state(session_id, dirty_questions=state.dirty_questions)
        logger.debug(f"Marked dirty for {session_id}: {question_refs}")
        return state

    async def clear_dirty_questions(self, session_id: str) -> NineQuestionStateSnapshot:
        """Clear all dirty marks"""
        return await self.update_state(session_id, dirty_questions=[])

    async def bootstrap_state(
        self,
        session_id: str,
        snapshot_version: int = 9,
    ) -> NineQuestionStateSnapshot:
        """Initialize state for a new session"""
        state = NineQuestionStateSnapshot(
            version=1,
            revision=0,
            dirty_questions=[],
            question_snapshots={},
            last_refresh_reason=None,
            snapshot_version=snapshot_version,
        )

        await self._store.save(session_id, state)
        if self._cache_manager is not None:
            self._cache_manager.set(CacheNamespace.STATE, session_id, state)
        logger.info(f"Bootstrapped 9Q state for {session_id}")
        return state
