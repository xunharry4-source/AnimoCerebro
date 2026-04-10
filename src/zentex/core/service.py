from __future__ import annotations

"""
Zentex Core Service Facade.

Provides a unified interface for the foundational architecture of Zentex, 
including versioning, baseline configuration snapshots, and system-wide constants.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CoreService:
    """
    Gateway service for Zentex Core Architecture.
    
    Acts as a lightweight facade for system-wide metadata and fundamental base classes.
    """

    def __init__(self) -> None:
        logger.info("CoreService initialized")

    def get_system_version(self) -> str:
        """Return the current version of the Zentex platform."""
        return "2.0.0-alpha"

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and versioning information for the core module."""
        return {
            "version": self.get_system_version(),
            "status": "ready",
            "module": "zentex.core"
        }


# Global singleton instance
_default_service: Optional[CoreService] = None


def get_core_service() -> CoreService:
    """Return the shared global instance of the CoreService."""
    global _default_service
    if _default_service is None:
        _default_service = CoreService()
    return _default_service
