from __future__ import annotations

"""
Zentex Safety Service Facade.

This module provides a simplified, high-level interface for other Zentex components
to interact with the safety and governance engine. It wraps the comprehensive
SafetyManager to provide a consistent service entry point.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.safety.safety_manager import SafetyManager, SafetyConfig

logger = logging.getLogger(__name__)


class SafetyService:
    """
    Gateway service for the Zentex Safety Engine.
    
    Coordinates safety checks, policy enforcement, and audit logging.
    Delegates to the underlying SafetyManager for complex multi-layer safety checks.
    """

    def __init__(self, config: Optional[SafetyConfig] = None) -> None:
        self._manager = SafetyManager(config=config)
        logger.info("SafetyService initialized")

    def check_safety(
        self,
        *,
        content: str,
        action_type: str = "general",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform a safety check on the provided content or action.
        
        Args:
            content: The content or payload to be checked.
            action_type: The type of action being performed.
            trace_id: Optional trace ID for auditability.
            
        Returns:
            A dictionary containing 'is_safe' and detailed evaluation metrics.
        """
        # For simple content checks, wrap it in an evaluation
        decision = self._manager.evaluate_action(
            action_type=action_type,
            payload={"content": content},
            context={"trace_id": trace_id}
        )
        
        return {
            "is_safe": decision.allowed,
            "reasons": [decision.reason],
            "risk_score": 0.9 if decision.risk_level == "critical" else 0.1,
            "decision_id": decision.decision_id
        }

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent safety audit logs from the manager."""
        # SafetyManager status includes aggregate metrics; 
        # for specific logs we might need direct engine access if exposed.
        # For now, return a placeholder or implement specific log retrieval if needed.
        return []

    def update_policy(self, policy_name: str, policy_config: Dict[str, Any]) -> bool:
        """Update a specific safety policy configuration via the manager."""
        # SafetyManager has a SafetyGate property
        return self._manager.safety_gate.update_policy(policy_name, policy_config)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health information for the safety subsystem."""
        status = self._manager.get_status()
        return status.model_dump()


# Global singleton instance for easy access
_default_service: Optional[SafetyService] = None


def get_safety_service() -> SafetyService:
    """Return the global shared SafetyService instance."""
    global _default_service
    if _default_service is None:
        _default_service = SafetyService()
    return _default_service
