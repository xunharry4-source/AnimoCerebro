from __future__ import annotations

"""
Zentex Cognition Service Facade.

Centralizes cognitive planning, counterfactual simulation, and social mind modeling,
providing a high-level API for intent inference and scenario pre-calculation.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.cognition.simulation import (
    CounterfactualSimulationEngine,
    OutcomeComparison,
    ScenarioBranch,
    SimulationBundle,
)
from zentex.plugins.simulation import SimulationIntent
from zentex.cognition.social_mind import (
    CommunicationFitProfile,
    InteractionMindEngine,
    InteractionMindModel,
    InteractionMindState,
)
from zentex.foundation.specs.model_provider import ModelProviderSpec
from zentex.llm.service import LLMService

logger = logging.getLogger(__name__)


class CognitionService:
    """
    Gateway service for Zentex cognitive reasoning systems.
    
    Coordinates the simulation engine and social mind state management.
    """

    def __init__(
        self,
        model_provider: ModelProviderSpec | None = None,
        llm_service: LLMService | None = None,
        model_provider_key: str | None = None,
        simulation_plugins: Optional[List[Any]] = None,
        brain_scope: str = "zentex.runtime"
    ) -> None:
        if not simulation_plugins:
            raise RuntimeError("CognitionService requires at least one simulation plugin.")
        self._simulation = CounterfactualSimulationEngine(
            llm_service=llm_service,
            model_provider=model_provider,
            model_provider_key=model_provider_key,
            simulation_plugins=simulation_plugins
        )
        self._social_mind = InteractionMindEngine(
            llm_service=llm_service,
            model_provider=model_provider,
            model_provider_key=model_provider_key,
            brain_scope=brain_scope
        )
        logger.info("CognitionService initialized")

    @property
    def interaction_mind_engine(self) -> InteractionMindEngine:
        """Public access to the interaction mind engine (social mind)."""
        return self._social_mind

    @property
    def simulation_engine(self) -> Any:
        """Public access to the counterfactual simulation engine.
        
        This property is used by kernel.service.simulation_engine to expose
        the simulation engine to web console routers.
        """
        return self._simulation

    def submit_simulation(
        self,
        goal_id: str,
        branches: List[Dict[str, Any]],
        snapshot_version: int,
        idempotency_key: str,
        base_context: Dict[str, Any]
    ) -> Any:
        """Submit a background simulation task to evaluate potential scenarios."""
        return self._simulation.submit_simulation(
            goal_id=goal_id,
            branches=branches,
            snapshot_version=snapshot_version,
            idempotency_key=idempotency_key,
            base_context=base_context
        )

    def simulate_action(
        self,
        intent: SimulationIntent,
        context: Dict[str, Any],
    ) -> Any:
        """
        Perform a synchronous simulation of an action.
        
        This wraps the underlying simulation engine's plugin-specific logic.
        """
        # In a real environment, we would look up the best plugin for the intent
        # but here we delegate to internal engine's plugins.
        for plugin in self._simulation._simulation_plugins:
            if intent.target_domain in plugin.supported_domains:
                return plugin.simulate_action(intent, context)
        
        raise RuntimeError(f"No simulation plugin found for domain {intent.target_domain}")

    def get_simulation_result(self, goal_id: str) -> Optional[SimulationBundle]:
        """Retrieve the latest simulation results for a specific goal."""
        return self._simulation.get_bundle(goal_id)

    def infer_social_mind(
        self,
        entity_id: str,
        snapshot_version: int,
        context: Dict[str, Any]
    ) -> InteractionMindState:
        """Infer the intent and state of an interaction partner (e.g., user)."""
        return self._social_mind.infer_interaction_mind(
            entity_id=entity_id,
            snapshot_version=snapshot_version,
            context=context
        )

    def get_social_state(self, entity_id: str) -> Optional[InteractionMindState]:
        """Retrieve the current social mind snapshot for an entity."""
        return self._social_mind.get_state(entity_id)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health information for cognitive engines."""
        return {
            "simulation_snapshot_version": self._simulation.snapshot_version,
            "social_mind_scope": self._social_mind.brain_scope,
        }


# Global singleton instance (Optional, usually needs manual init with provider)
_default_service: Optional[CognitionService] = None


def get_cognition_service() -> CognitionService:
    """Return the global CognitionService instance. Raises if not initialized."""
    global _default_service
    if _default_service is None:
        raise RuntimeError("CognitionService must be initialized before use via init_cognition_service().")
    return _default_service


def get_service() -> CognitionService:
    """Standard service factory function for launcher assembly.
    
    Lazily initializes CognitionService with default configuration if not already initialized.
    This ensures the service is always available when requested by the launcher.
    
    Returns:
        CognitionService instance (never None)
    """
    global _default_service
    if _default_service is None:
        # Lazy initialization with minimal defaults
        # In production, this should be properly configured via init_cognition_service()
        logger.warning(
            "CognitionService not explicitly initialized. "
            "Auto-initializing with default simulation plugin. "
            "For production, call init_cognition_service() with proper configuration."
        )
        try:
            # Create a minimal default simulation plugin
            from zentex.plugins.simulation import SimulationDomainPlugin, SimulationIntent, SimulationResult
            
            class DefaultSimulationPlugin(SimulationDomainPlugin):
                """Minimal fallback simulation plugin for development."""
                plugin_id: str = "default_simulation"
                version: str = "1.0.0"
                supported_domains: list[str] = ["general"]
                
                def simulate_action(self, intent: SimulationIntent, context: dict) -> SimulationResult:
                    return SimulationResult(
                        is_safe=True,
                        predicted_impacts=["Default simulation - no specific impacts predicted"],
                        simulated_by="default_simulation",
                    )
            
            _default_service = CognitionService(
                model_provider=None,
                llm_service=None,
                simulation_plugins=[DefaultSimulationPlugin()],
                brain_scope="zentex.cognition"
            )
            logger.info("✓ CognitionService auto-initialized with default simulation plugin")
        except Exception as exc:
            logger.error(f"Failed to auto-initialize CognitionService: {exc}", exc_info=True)
            raise RuntimeError(
                f"CognitionService initialization failed: {exc}. "
                "Please call init_cognition_service() with proper configuration."
            ) from exc
    
    return _default_service


def init_cognition_service(
    model_provider: ModelProviderSpec | None = None,
    llm_service: LLMService | None = None,
    model_provider_key: str | None = None,
    simulation_plugins: Optional[List[Any]] = None,
    brain_scope: str = "zentex.cognition"
) -> CognitionService:
    """Initialize the global CognitionService with required dependencies."""
    global _default_service
    _default_service = CognitionService(
        model_provider=model_provider,
        llm_service=llm_service,
        model_provider_key=model_provider_key,
        simulation_plugins=simulation_plugins,
        brain_scope=brain_scope
    )
    return _default_service
