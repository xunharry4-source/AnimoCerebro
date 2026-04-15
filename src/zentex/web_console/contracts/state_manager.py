"""Nine-Question State Management Contract

Defines atomic operations on nine-question state, replacing
direct access to runtime.nine_question_state and runtime.nine_question_router.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .kernel_service import NineQuestionStateSnapshot


class NineQuestionStateManager(ABC):
    """Nine-question state atomic operations
    
    Replaces:
    - runtime.nine_question_state (read/write)
    - runtime.nine_question_router.derive_dirty_questions_for_event()
    - runtime.refresh_nine_question_state()
    
    All methods provide strong consistency guarantees for state updates.
    """

    @abstractmethod
    async def get_state(self, session_id: str) -> NineQuestionStateSnapshot:
        """Get current nine-question state for a session
        
        Args:
            session_id: Session UUID
            
        Returns:
            NineQuestionStateSnapshot: Current state
            
        Raises:
            ValueError: If session not found or state not bootstrapped
        """
        pass

    @abstractmethod
    async def get_dirty_questions(self, session_id: str) -> List[str]:
        """Get list of questions marked as needing recomputation
        
        Args:
            session_id: Session UUID
            
        Returns:
            List of question IDs (e.g., ["q3", "q5"])
        """
        pass

    @abstractmethod
    async def get_last_refresh_reason(self, session_id: str) -> str | None:
        """Get reason for last state refresh
        
        Args:
            session_id: Session UUID
            
        Returns:
            Refresh reason (e.g., "trajectory_bounded") or None
        """
        pass

    @abstractmethod
    async def get_latest_populated_state(self) -> NineQuestionStateSnapshot | None:
        """Get the most recently updated state that already contains snapshots."""
        pass

    @abstractmethod
    async def update_state(
        self,
        session_id: str,
        **updates,
    ) -> NineQuestionStateSnapshot:
        """Update state atomically (increments revision)
        
        Args:
            session_id: Session UUID
            **updates: State fields to update (dirty_questions, last_refresh_reason, etc.)
            
        Returns:
            Updated NineQuestionStateSnapshot
        """
        pass

    @abstractmethod
    async def mark_questions_dirty(
        self,
        session_id: str,
        question_refs: List[str],
    ) -> NineQuestionStateSnapshot:
        """Mark questions as needing recomputation
        
        Replaces: runtime.nine_question_router.derive_dirty_questions_for_event()
        
        Args:
            session_id: Session UUID
            question_refs: Question IDs to mark (e.g., ["q1", "q2"])
            
        Returns:
            Updated NineQuestionStateSnapshot with dirty_questions updated
        """
        pass

    @abstractmethod
    async def clear_dirty_questions(self, session_id: str) -> NineQuestionStateSnapshot:
        """Clear all dirty question marks
        
        Args:
            session_id: Session UUID
            
        Returns:
            Updated NineQuestionStateSnapshot with empty dirty_questions
        """
        pass

    @abstractmethod
    async def bootstrap_state(
        self,
        session_id: str,
        snapshot_version: int = 9,
    ) -> NineQuestionStateSnapshot:
        """Initialize nine-question state for a new session
        
        Args:
            session_id: Session UUID
            snapshot_version: Version marker (default 9 for compatibility)
            
        Returns:
            Initialized NineQuestionStateSnapshot
        """
        pass
