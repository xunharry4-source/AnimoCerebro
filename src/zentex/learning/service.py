from __future__ import annotations

"""
Zentex Learning Service Facade.

This module provides a simplified, high-level interface for other Zentex components
to interact with the learning engine without needing to manage internal state or
complex evolution logic.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.learning.engine import LearningEngine
from zentex.learning.models import LearningRecord, LearningOutcome

logger = logging.getLogger(__name__)


class LearningServiceFacade:
    """
    Gateway service for the Zentex Learning Engine.
    
    Coordinates learning record ingestion, analysis, and model updates via a unified API.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            import os
            from pathlib import Path
            storage_path = os.environ.get("ZENTEX_LEARNING_ROOT") or str(Path.home() / ".zentex" / "learning")
        
        self._engine = LearningEngine(storage_path=storage_path)
        logger.info(f"LearningServiceFacade initialized at {storage_path}")

    def ingest_learning(
        self,
        *,
        content: str,
        outcome: str,
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LearningRecord:
        """
        Store a new learning record.
        
        Args:
            content: The content of the learning experience.
            outcome: The result (e.g., 'success', 'failure').
            trace_id: Optional trace ID for auditability.
            metadata: Additional key-value pairs.
            
        Returns:
            The created LearningRecord.
        """
        return self._engine.store_record(
            content=content,
            outcome=outcome,
            trace_id=trace_id,
            metadata=metadata or {},
        )

    def get_learning(self, record_id: str) -> Optional[LearningRecord]:
        """Retrieve a specific learning record by its unique ID."""
        try:
            return self._engine.get_record(record_id)
        except Exception:
            return None

    def analyze_patterns(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Analyze recent learning records for recurring patterns."""
        return self._engine.analyze_recent_patterns(limit=limit)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic information about the learning service."""
        return self._engine.get_diagnostics()


# Global singleton instance for easy access
_default_service: Optional[LearningServiceFacade] = None


def get_learning_service() -> LearningServiceFacade:
    """Return the global default LearningServiceFacade instance."""
    global _default_service
    if _default_service is None:
        _default_service = LearningServiceFacade()
    return _default_service
