from __future__ import annotations

"""
Zentex Reflection Service Facade.

This module provides a simplified, high-level interface for other Zentex components
to interact with the reflection engine without needing to manage internal persistence
or complex generation logic.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.reflection.service import ReflectionService
from zentex.reflection.persistence import ReflectionPersistence
from zentex.reflection.models import ReflectionRecord, ReflectionType

logger = logging.getLogger(__name__)


class ReflectionServiceFacade:
    """
    Gateway service for the Zentex Reflection Engine.
    
    Coordinates reflection generation, management, and governance via a unified API.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            import os
            from pathlib import Path
            storage_path = os.environ.get("ZENTEX_REFLECTION_ROOT") or str(Path.home() / ".zentex" / "reflection")
        
        self._persistence = ReflectionPersistence(storage_path=storage_path)
        self._internal_service = ReflectionService(persistence=self._persistence)
        logger.info(f"ReflectionServiceFacade initialized at {storage_path}")

    def reflect(
        self,
        *,
        subject: str,
        context: Dict[str, Any],
        reflection_type: str = "decision_reflection",
        trace_id: Optional[str] = None,
    ) -> ReflectionRecord:
        """
        Generate and store a new reflection record.
        
        Args:
            subject: The topic of the reflection.
            context: The context data for the reflection.
            reflection_type: The type of reflection (e.g., 'decision_reflection', 'error_reflection').
            trace_id: Optional trace ID for auditability.
            
        Returns:
            The created ReflectionRecord.
        """
        try:
            r_type = ReflectionType(reflection_type)
        except ValueError:
            raise ValueError(f"Invalid reflection type: {reflection_type}")

        return self._internal_service.generate_reflection(
            subject=subject,
            reflection_type=r_type,
            context=context,
            trace_id=trace_id,
        )

    def get_reflection(self, reflection_id: str) -> Optional[ReflectionRecord]:
        """Retrieve a specific reflection record by its unique ID."""
        try:
            return self._internal_service.get_reflection(reflection_id)
        except Exception:
            return None

    def list_reflections(self, limit: int = 50) -> List[ReflectionRecord]:
        """List recent reflection records."""
        reflections = self._internal_service.list_reflections()
        return sorted(reflections, key=lambda r: r.created_at, reverse=True)[:limit]

    def verify_reflection(self, reflection_id: str, verified_by: str) -> Optional[ReflectionRecord]:
        """Mark a reflection as verified."""
        try:
            return self._internal_service.verify_reflection(reflection_id, verified_by)
        except Exception:
            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Return diagnostic information about the reflection service."""
        metrics = self._internal_service.get_metrics()
        return metrics.model_dump()


# Global singleton instance for easy access
_default_service: Optional[ReflectionServiceFacade] = None


def get_reflection_service() -> ReflectionServiceFacade:
    """Return the global default ReflectionServiceFacade instance."""
    global _default_service
    if _default_service is None:
        _default_service = ReflectionServiceFacade()
    return _default_service
