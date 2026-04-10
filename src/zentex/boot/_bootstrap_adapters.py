"""
Adapter bootstrap module for web_dev.py

Handles initialization of Agent coordination adapters via proper service APIs.

NOTE: MCP and CLI adapter initialization has been moved to _bootstrap_integrations.py
for consolidation of legacy adapter code that still uses direct class instantiation.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple
import logging

from zentex.tasks.service import TaskManagementService
from zentex.agents.service import AgentCoordinationService
from zentex.runtime.transcript import BrainTranscriptStore

logger = logging.getLogger(__name__)


def setup_agent_coordination(
    *,
    asset_store: Optional[Any] = None,
    task_service: Optional[TaskManagementService] = None,
    transcript_store: Optional[BrainTranscriptStore] = None,
) -> Tuple[Any, AgentCoordinationService]:
    """
    Setup agent coordination through proper service API.
    
    Creates AgentCoordinationService (facade) which manages AgentManager internally.
    Returns Tuple[manager_placeholder, service] for backward compatibility.
    """
    # Initialize via service
    service = AgentCoordinationService(
        db_path=str(asset_store.db_path) if hasattr(asset_store, 'db_path') else ":memory:",
        transcript_store=transcript_store,
        task_service=task_service,
    )
    
    logger.info("[Agents] Coordination service initialized via AgentCoordinationService")
    # Return tuple for backward compatibility: (manager_placeholder, service)
    return None, service

