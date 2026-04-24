from __future__ import annotations

"""
Zentex Cognition Service Facade.

Centralizes cognitive planning, counterfactual simulation, and social mind modeling,
providing a high-level API for intent inference and scenario pre-calculation.
"""

import logging
from typing import Any, Dict, List, Optional, Union

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
from zentex.cognition.motivation import MotivationEngine, Motivation

logger = logging.getLogger(__name__)


class CognitionService:
    """
    Gateway service for Zentex cognitive reasoning systems.
    
    Coordinates the simulation engine and social mind state management.
    """

    def __init__(
        self,
        model_provider: Optional[ModelProviderSpec] = None,
        llm_service: Optional[LLMService] = None,
        model_provider_key: Optional[str] = None,
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
        self._motivation = MotivationEngine()
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

    def evaluate_drive(
        self,
        session_id: str,
        turn_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase 1.5: Drive — Authentically compute situational motivations.
        """
        # Identity and Nine-Question state must be in context (passed from Kernel)
        identity = context.get("identity")
        nine_q_state = context.get("nine_question_state")
        
        if not identity or not nine_q_state:
             # AUTHENTIC GROUNDING POLICY: Decisional logic must never run without baseline grounding.
             logger.critical(f"Integrity Violation: Missing identity/NQ baseline for session {session_id}. Cognitive drive cannot be established without grounding.")
             raise RuntimeError(f"Cognitive Turn Halt: Grounding failure in evaluate_drive. Identity or Nine-Question baseline missing.")

        try:
            active_motivations = self._motivation.generate_motivations(identity, nine_q_state)
            return {
                "active_motivations": [m.model_dump() if hasattr(m, "model_dump") else m.__dict__ for m in active_motivations],
                "drive_evaluated": True,
                "drive_timestamp": context.get("timestamp")
            }
        except Exception as e:
            logger.error(f"Integrity Violation: Motivation generation failed: {e}")
            raise RuntimeError(f"Cognitive Turn Halt: Motivation drive could not be established.")

    def frame(
        self,
        session_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase 2: Frame — Primary cognitive pass guided by motivations.
        """
        # Policy: Eradicate Mock Framing.
        # This implementation uses the active motivations to weight scenario interpretation.
        active_motivations = context.get("active_motivations", [])
        observations = context.get("observations", {})
        
        framing_result = {
            "cognitive_frame": "mission_pursuit" if active_motivations else "neutral",
            "observation_salience": {},
            "active_drives_count": len(active_motivations)
        }
        
        # Heuristic: Highlight observations that match motivation sources
        # AUTHENTIC GROUNDING: Weight scenario interpretation based on established boundaries.
        baseline_snapshot = context.get("context_snapshot", {})
        redlines = baseline_snapshot.get("q6_redline_profile", {}).get("active_redlines", [])
        capabilities = baseline_snapshot.get("q4_capability_boundary_profile", {}).get("verified_capabilities", [])

        for obs_key, obs_value in observations.items():
            # 1. Motivation Alignment (already extracted)
            if any(s in obs_key for s in motivation_sources):
                 framing_result["observation_salience"][obs_key] = 1.0
            
            # 2. Redline/Constraint Awareness
            # If an observation overlaps with a redline (Q6) or capability limit (Q4/Q7), spike salience.
            obs_text = str(obs_value).lower()
            if any(str(r).lower() in obs_text for r in redlines):
                framing_result["observation_salience"][obs_key] = 1.0
                framing_result["cognitive_frame"] = "constraint_alert"
            
            # 3. Default salience
            if obs_key not in framing_result["observation_salience"]:
                framing_result["observation_salience"][obs_key] = 0.5
                
        return {
            "framing": framing_result,
            "framing_version": "1.0.0",
            "frame_status": "synced"
        }

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health information for cognitive engines."""
        return {
            "simulation_snapshot_version": self._simulation.snapshot_version,
            "social_mind_scope": self._social_mind.brain_scope,
            "simulation_workers": self._simulation._executor._max_workers if hasattr(self._simulation, "_executor") else 0,
            "social_mind_entities_tracked": len(self._social_mind._states),
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
    
    Standard Fail-Closed policy:
    This function NO LONGER auto-initializes with fake dummy plugins.
    If init_cognition_service() was not called by the launcher, this raises RuntimeError.
    """
    global _default_service
    if _default_service is None:
        raise RuntimeError(
            "CognitionService was not explicitly initialized. "
            "Auto-initialization with fake dummy plugins is strictly prohibited by security and resilience policies. "
            "Please ensure init_cognition_service() is called during bootstrap."
        )
    return _default_service


def init_cognition_service(
    model_provider: Optional[ModelProviderSpec] = None,
    llm_service: Optional[LLMService] = None,
    model_provider_key: Optional[str] = None,
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
