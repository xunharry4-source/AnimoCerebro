from __future__ import annotations
"""Public simulation plugin contracts owned by zentex.plugins."""


from abc import abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import Field

from zentex.plugins.contracts import BasePluginSpec


class SimulationIntent(BasePluginSpec):
    plugin_id: str = "simulation-intent"
    version: str = "1.0.0"
    feature_code: str = "simulation.intent"
    is_concurrency_safe: bool = True
    intent_name: str
    target_domain: str
    intent_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"


class SimulationResult(BasePluginSpec):
    plugin_id: str = "simulation-result"
    version: str = "1.0.0"
    feature_code: str = "simulation.result"
    is_concurrency_safe: bool = True
    is_safe: bool
    predicted_impacts: list[str] = Field(default_factory=list)
    
    # Brain-Specific Integrity Metrics
    cognitive_impact: float = Field(default=0.0, ge=0.0, le=1.0) # 0 = no change, 1 = total state wipe
    resource_usage: float = Field(default=0.0, ge=0.0, le=1.0)   # 0 = free, 1 = budget exhaustion
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)      # Computed risk score
    
    veto_reason: Optional[str] = None
    replan_required: bool = False
    simulated_by: str
    fallback_used: bool = False


class SimulationDomainPlugin(BasePluginSpec):
    supported_domains: list[str] = Field(default_factory=list)

    @abstractmethod
    def simulate_action(
        self,
        intent: SimulationIntent,
        context: dict[str, Any],
    ) -> SimulationResult: ...


SimulationIntent.model_rebuild()
SimulationResult.model_rebuild()
SimulationDomainPlugin.model_rebuild()
