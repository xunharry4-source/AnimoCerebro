from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NegotiationRequest(BaseModel):
    """
    A request for resources or permissions to resolve a task blockage.
    """
    negotiation_id: str = Field(default_factory=lambda: f"neg-{uuid4().hex[:8]}")
    target_task_id: str
    gap_type: str = Field(..., description="e.g., 'permission', 'compute_resource', 'human_verification'")
    required_asset: str
    proposed_tradeoff: Optional[str] = None
    status: str = Field(default="pending") # pending, active, resolved, rejected
    priority: int = Field(default=3, ge=1, le=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NegotiationGenerator:
    """
    Analyzes task gaps and generates negotiation requests.
    """
    def __init__(self, task_service: Any):
        self.task_service = task_service
        self._active_negotiations: Dict[str, NegotiationRequest] = {}

    def scan_for_gaps(self, suspended_tasks: List[Any]) -> List[NegotiationRequest]:
        """
        Scan a list of suspended tasks (e.g., from TaskService) and generate negotiations.
        """
        new_negotiations: List[NegotiationRequest] = []
        for task in suspended_tasks:
            # Check if this task already has an active negotiation
            if self._has_active_negotiation(task.task_id):
                continue
                
            # Logic to detect gaps based on task metadata
            # In a real system, this would look at 'blocking_reason' or 'required_permissions'
            gap_type = getattr(task, "gap_type", None)
            if not gap_type:
                 # Heuristic: if suspended due to permission
                 if "permission" in str(getattr(task, "reason", "")).lower():
                     gap_type = "permission"
                 else:
                     continue
            
            neg = NegotiationRequest(
                target_task_id=task.task_id,
                gap_type=gap_type,
                required_asset=getattr(task, "required_asset", "unknown_permission"),
                priority=getattr(task, "priority", 3)
            )
            self._active_negotiations[neg.negotiation_id] = neg
            new_negotiations.append(neg)
            logger.info(f"Generated auto-negotiation {neg.negotiation_id} for task {task.task_id}")
            
        return new_negotiations

    def _has_active_negotiation(self, task_id: str) -> bool:
        return any(n.target_task_id == task_id and n.status in {"pending", "active"} 
                   for n in self._active_negotiations.values())
                   
    def resolve_negotiation(self, negotiation_id: str, success: bool):
        if negotiation_id in self._active_negotiations:
            neg = self._active_negotiations[negotiation_id]
            neg.status = "resolved" if success else "rejected"
            logger.info(f"Negotiation {negotiation_id} marked as {neg.status}")
