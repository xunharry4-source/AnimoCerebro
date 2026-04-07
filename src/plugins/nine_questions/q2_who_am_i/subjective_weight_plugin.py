from __future__ import annotations

from typing import Any, Dict, List
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import SubjectiveWeightSpec


class RiskWeightPlugin(SubjectiveWeightSpec):
    """
    G17 Subjective Weight Plugin for Risk appetite.
    """
    
    plugin_id: str = "subjective_risk_profile"
    target_metric: str = "risk"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def calculate_weight(self, task_context: Dict[str, Any]) -> float:
        """
        Logic for Risk appetite.
        If environment is production, risk weight should be high (conservative).
        """
        environment = task_context.get("q1_scene_model", {}).get("primary_domain", "unknown")
        if "production" in environment.lower() or "live" in environment.lower():
            return 0.9  # High conservatism
        return 0.4    # Default risk appetite
