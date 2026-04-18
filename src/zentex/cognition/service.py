from __future__ import annotations

"""
Zentex Cognition Service Facade.

Centralizes cognitive planning, counterfactual simulation, and social mind modeling,
providing a high-level API for intent inference and scenario pre-calculation.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.common.prompt_upgrade_contract import ModulePromptUpgradeContract, build_section_policy
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

    def seed_test_simulation_data(self) -> None:
        """Seed test simulation data for development/demo purposes.
        
        This method creates a pre-computed simulation bundle for 'goal-runtime-stability'
        to support frontend development and testing without requiring actual LLM calls.
        """
        from datetime import datetime, timezone
        
        goal_id = "goal-runtime-stability"
        
        # Check if already seeded
        existing_bundle = self._simulation.get_bundle(goal_id)
        if existing_bundle is not None:
            logger.info(f"Simulation data for {goal_id} already exists, skipping seeding")
            return
        
        # Create test branches
        test_branches = [
            ScenarioBranch(
                branch_id="branch-conservative",
                branch_label="保守方案",
                target_domain="general",
                predicted_impacts=[
                    "系统稳定性提升 15%",
                    "内存占用降低 8%",
                    "响应延迟增加 50ms"
                ],
                risk_score=0.2,
                failure_cascade=False,
                simulated_by=["default_simulation"],
            ),
            ScenarioBranch(
                branch_id="branch-aggressive",
                branch_label="激进优化方案",
                target_domain="general",
                predicted_impacts=[
                    "性能提升 40%",
                    "资源利用率提高 25%",
                    "存在 15% 的回滚风险"
                ],
                risk_score=0.65,
                failure_cascade=True,
                simulated_by=["default_simulation"],
            ),
            ScenarioBranch(
                branch_id="branch-balanced",
                branch_label="平衡方案",
                target_domain="general",
                predicted_impacts=[
                    "性能提升 20%",
                    "稳定性保持当前水平",
                    "实施周期适中"
                ],
                risk_score=0.35,
                failure_cascade=False,
                simulated_by=["default_simulation"],
            ),
        ]
        
        # Create outcome comparison
        outcome_comparison = OutcomeComparison(
            summary="经过多维度评估，保守方案在稳定性和可预测性方面表现最佳，推荐作为首选实施方案。激进方案虽然性能提升显著，但回滚风险较高。平衡方案可作为备选。",
            risk_ranking=[
                {"branch_id": "branch-conservative", "risk_score": 0.2, "rank": 1},
                {"branch_id": "branch-balanced", "risk_score": 0.35, "rank": 2},
                {"branch_id": "branch-aggressive", "risk_score": 0.65, "rank": 3},
            ],
            recommended_branch_id="branch-conservative",
        )
        
        # Create simulation bundle
        test_bundle = SimulationBundle(
            goal_id=goal_id,
            idempotency_key=f"seed-{goal_id}-{int(datetime.now(timezone.utc).timestamp())}",
            snapshot_version=self._simulation.snapshot_version,
            status="completed",
            branches=test_branches,
            outcome_comparison=outcome_comparison,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        
        # Inject into simulation engine
        with self._simulation._lock:
            self._simulation._bundles_by_goal[goal_id] = test_bundle
        
        logger.info(f"✓ Seeded test simulation data for {goal_id}")


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
            
            # Seed test simulation data for development
            _default_service.seed_test_simulation_data()
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
    
    # Seed test simulation data for development/demo
    _default_service.seed_test_simulation_data()
    
    return _default_service


def list_prompt_upgrade_contracts() -> list[ModulePromptUpgradeContract]:
    return [
        ModulePromptUpgradeContract(
            prompt_id="cognition.interaction_mind",
            module_id="cognition",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/cognition/llm_prompt.py",
            prompt_builder_name="build_interaction_mind_prompt",
            prompt_builder_symbol="zentex.cognition.llm_prompt.build_interaction_mind_prompt",
            target_component="cognition.interaction_mind.prompt",
            immutable_intent="Interaction mind prompt must infer the other party's intent, knowledge gaps, communication fit, and misunderstanding signals.",
            expected_output_key="model",
            allowed_prompt_change_scope=["tighten internal-state wording", "clarify social-mind schema"],
            forbidden_prompt_changes=["must not add action recommendations", "must not remove misunderstanding_signals", "must not change this into execution planning"],
            editable_prompt_sections=["output_contract", "quality_rules"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve interaction-mind inference identity.", purpose="Prevent drift into action planning.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce social-mind schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove model", "remove misunderstanding_signals"]),
                build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain inference scope.", purpose="Keep output limited to internal state inference.", allowed_operations=["tighten wording"], forbidden_operations=["allow action recommendations"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        ),
        ModulePromptUpgradeContract(
            prompt_id="cognition.simulation_comparison",
            module_id="cognition",
            prompt_file_path="/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/cognition/llm_prompt.py",
            prompt_builder_name="build_simulation_comparison_prompt",
            prompt_builder_symbol="zentex.cognition.llm_prompt.build_simulation_comparison_prompt",
            target_component="cognition.simulation_comparison.prompt",
            immutable_intent="Simulation comparison prompt must compare simulated branches and recommend one branch based on evidence.",
            expected_output_key="recommended_branch_id",
            allowed_prompt_change_scope=["compress comparison framing", "clarify recommendation schema"],
            forbidden_prompt_changes=["must not remove risk_ranking", "must not recommend without evidence", "must not turn comparison into chat prose"],
            editable_prompt_sections=["input_summary", "output_contract", "quality_rules"],
            immutable_prompt_sections=["role"],
            section_change_policy=[
                build_section_policy(section_key="role", mutable=False, intent="Preserve simulation comparison identity.", purpose="Prevent drift into generic analysis.", forbidden_operations=["change prompt identity"]),
                build_section_policy(section_key="input_summary", mutable=True, intent="Provide comparison scope.", purpose="Allow concise branch-context framing.", allowed_operations=["compress evidence"], forbidden_operations=["change goal identity"]),
                build_section_policy(section_key="output_contract", mutable=True, intent="Enforce comparison schema.", purpose="Allow schema clarification.", allowed_operations=["clarify schema"], forbidden_operations=["remove recommended_branch_id", "remove risk_ranking"]),
                build_section_policy(section_key="quality_rules", mutable=True, intent="Constrain recommendation basis.", purpose="Keep recommendation evidence-based.", allowed_operations=["tighten wording"], forbidden_operations=["allow unsupported recommendation"]),
            ],
            validation_commands=["pytest tests/test_module_prompt_upgrade_contracts.py -q"],
        ),
    ]


def get_prompt_upgrade_contract(prompt_id: str) -> ModulePromptUpgradeContract:
    contracts = {contract.prompt_id: contract for contract in list_prompt_upgrade_contracts()}
    return contracts[prompt_id]
