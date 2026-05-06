from __future__ import annotations

"""Public agent service boundary.

The concrete coordination implementation lives in
``zentex.agents.coordination.service``. Keep this module thin so launcher,
web-console, tests, and plugins can continue importing the stable public
service entrypoint without concentrating implementation logic here.
"""

from zentex.agents.coordination.service import (
    AgentCoordinationService,
    AgentRegistrationRequest,
)
from zentex.agents.manager import AgentAsset, AgentManager, AgentStatus, AgentTrustLevel

_default_service: AgentCoordinationService | None = None


def get_service() -> AgentCoordinationService:
    """Return the public singleton agent coordination service."""
    global _default_service
    if _default_service is None:
        _default_service = AgentCoordinationService(
            manager=None,
            transcript_store=None,
        )
    return _default_service


__all__ = [
    "AgentCoordinationService",
    "AgentRegistrationRequest",
    "AgentManager",
    "AgentAsset",
    "AgentStatus",
    "AgentTrustLevel",
    "get_service",
]
