"""
Base Plugin Service: Initialization and Bootstrap

Handles:
- Plugin service initialization
- Factory loading
- Bootstrap process
- Plugin instantiation
- Category determination
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.storage import PluginStorage
from zentex.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


def _get_plugin_factories() -> Dict[str, Callable]:
    """
    Lazy-loaded plugin factories to avoid circular imports.
    This function is called only when needed.
    """
    # Import here to avoid circular imports at module level
    from zentex.plugins.boot_exports import (
        build_default_cloud_browser_executor,
        build_default_local_system_executor,
        build_budget_conflict_plugin,
        build_expired_assumption_cleaner_plugin,
        build_failure_mode_cluster_plugin,
        build_semantic_conflict_plugin,
        build_memory_extractor_plugin,
        build_q1_where_am_i_plugin,
        build_q2_who_am_i_plugin,
        build_q3_what_do_i_have_plugin,
        build_q4_what_can_i_do_plugin,
        build_q5_what_am_i_allowed_to_do_plugin,
        build_q6_what_should_i_not_do_plugin,
        build_q7_what_else_can_i_do_plugin,
        build_q8_what_should_i_do_now_plugin,
        build_q9_how_should_i_act_plugin,
        build_default_alternative_oracle,
        build_default_objective_oracle,
        build_default_posture_oracle,
        build_default_redline_oracle,
        build_reflection_generator_plugin,
        build_default_provider_tools_model_provider,
        BasicEnvironmentInterpreter,
        BasicPromptInjectionSanitizer,
        BasicWebhookIngestPlugin,
        build_default_host_telemetry_plugin,
        build_default_market_simulator,
        build_default_thought_sandbox,
        WeightPluginAssembler,
        build_default_conservative_weight,
    )
    
    return {
        # Execution Plugins
        'execution_cloud_browser': build_default_cloud_browser_executor,
        'execution_local_system': build_default_local_system_executor,
        # Cognitive Plugins
        'cognitive_budget_conflict': build_budget_conflict_plugin,
        'cognitive_expired_assumption': build_expired_assumption_cleaner_plugin,
        'cognitive_failure_cluster': build_failure_mode_cluster_plugin,
        'cognitive_semantic_conflict': build_semantic_conflict_plugin,
        # Memory Plugins
        'memory_extractor': build_memory_extractor_plugin,
        # Nine Questions Plugins
        'q1_where_am_i': build_q1_where_am_i_plugin,
        'q2_who_am_i': build_q2_who_am_i_plugin,
        'q3_what_do_i_have': build_q3_what_do_i_have_plugin,
        'q4_what_can_i_do': build_q4_what_can_i_do_plugin,
        'q5_allowed_to_do': build_q5_what_am_i_allowed_to_do_plugin,
        'q6_should_not_do': build_q6_what_should_i_not_do_plugin,
        'q7_else_can_do': build_q7_what_else_can_i_do_plugin,
        'q8_should_do_now': build_q8_what_should_i_do_now_plugin,
        'q9_how_should_act': build_q9_how_should_i_act_plugin,
        # Oracle Plugins
        'oracle_alternative': build_default_alternative_oracle,
        'oracle_objective': build_default_objective_oracle,
        'oracle_posture': build_default_posture_oracle,
        'oracle_redline': build_default_redline_oracle,
        # Reflection Plugins
        'reflection_generator': build_reflection_generator_plugin,
        # Model Provider Plugins
        'model_provider_tools': build_default_provider_tools_model_provider,
        # Sensory Plugins
        'sensory_environment': BasicEnvironmentInterpreter,
        'sensory_injection_sanitizer': BasicPromptInjectionSanitizer,
        'sensory_webhook': BasicWebhookIngestPlugin,
        'sensory_telemetry': build_default_host_telemetry_plugin,
        # Simulation Plugins
        'simulation_market': build_default_market_simulator,
        'simulation_thought': build_default_thought_sandbox,
        # Weight Plugins
        'weight_assembler': WeightPluginAssembler,
        'weight_conservative': build_default_conservative_weight,
    }


class BasePluginService:
    """
    Base service providing initialization and bootstrap for plugin system.
    
    Responsibilities:
    - Manage storage and registry
    - Initialize service state
    - Load plugin factories
    - Bootstrap plugins on startup
    - Determine plugin categories
    """
    
    # Class-level cache for plugin factories (lazily loaded)
    _FACTORIES_CACHE = None

    def __init__(
        self, 
        db_path: str,
        manager: Optional[PluginManager] = None, 
    ) -> None:
        """
        Initialize the plugin service.
        
        Args:
            db_path: Path to SQLite database
            manager: Optional PluginManager reference
        """
        self._storage = PluginStorage(db_path)
        self.manager = manager
        
        # In-memory registry: plugin_id -> actual plugin instance
        self._plugin_instances: Dict[str, Any] = {}
        
        # Spec cache for quick lookup: plugin_id -> spec dict
        self._plugin_specs: Dict[str, Dict[str, Any]] = {}
        
        # Execution records: plugin_id -> execution stats
        self._execution_stats: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _get_factories(cls) -> Dict[str, Callable]:
        """Get plugin factories (cached)."""
        if cls._FACTORIES_CACHE is None:
            cls._FACTORIES_CACHE = _get_plugin_factories()
        return cls._FACTORIES_CACHE

    def bootstrap(self) -> None:
        """
        Autonomous bootstrap:
        1. Register all built-in plugins from factory functions
        2. Load ACTIVE plugins from DB into memory with real instances
        3. Initialize execution statistics
        """
        logger.info("[Plugins] Starting autonomous bootstrap...")
        
        # Step 1: Load and instantiate all plugins from factories
        self._load_and_instantiate_plugins()
        
        # Step 2: Load existing registrations from database
        records = self._storage.list_plugins()
        active_count = 0
        
        for record in records:
            plugin_id = record["plugin_id"]
            try:
                spec_dict = json.loads(record["spec_json"])
                self._plugin_specs[plugin_id] = spec_dict
                
                # Only load to memory if ACTIVE
                if record["status"] == PluginLifecycleStatus.ACTIVE.value:
                    if plugin_id not in self._plugin_instances:
                        # Try to instantiate from factory
                        factory = self._get_factories().get(plugin_id)
                        if factory:
                            try:
                                instance = factory()
                                self._plugin_instances[plugin_id] = instance
                                active_count += 1
                            except Exception as e:
                                logger.warning(f"[Plugins] Failed to instantiate {plugin_id}: {e}")
                    else:
                        active_count += 1
                        
                # Initialize execution stats
                if plugin_id not in self._execution_stats:
                    self._execution_stats[plugin_id] = {
                        'usage_count': record.get('usage_count', 0),
                        'failure_count': record.get('failure_count', 0),
                        'last_executed_at': None,
                    }
                    
            except Exception as exc:
                logger.error(f"[Plugins] Failed to load {plugin_id}: {exc}")
        
        logger.info(f"[Plugins] Bootstrap complete. {active_count} plugins active, {len(self._plugin_instances)} instantiated.")

    def _load_and_instantiate_plugins(self) -> None:
        """
        Instantiate all built-in plugins from factory functions
        and register them to the database if not already registered.
        """
        registered = {r['plugin_id'] for r in self._storage.list_plugins()}
        
        for plugin_id, factory in self._get_factories().items():
            if plugin_id in registered:
                continue  # Already registered, skip
            
            try:
                logger.info(f"[Plugins] Instantiating new plugin: {plugin_id}")
                instance = factory()
                
                # Determine category from plugin_id
                category = self._determine_category(plugin_id)
                
                # Create spec from instance
                spec_dict = {
                    'plugin_id': plugin_id,
                    'version': getattr(instance, 'version', '1.0.0'),
                    'status': PluginLifecycleStatus.CANDIDATE.value,
                    'category': category,
                    'behavior_key': getattr(instance, 'behavior_key', None),
                    'feature_code': getattr(instance, 'feature_code', plugin_id),
                }
                
                # Register in database
                registration = {
                    'source_kind': 'built_in',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }
                
                self._storage.upsert_plugin(
                    category=category,
                    plugin_id=plugin_id,
                    spec_dict=spec_dict,
                    registration_dict=registration
                )
                
                self._plugin_instances[plugin_id] = instance
                self._plugin_specs[plugin_id] = spec_dict
                
            except Exception as e:
                logger.error(f"[Plugins] Failed to register {plugin_id}: {e}")

    def _determine_category(self, plugin_id: str) -> str:
        """
        Determine plugin category from its ID.
        
        Args:
            plugin_id: The plugin identifier
            
        Returns:
            Category string ('cognitive', 'functional', 'sensory', etc.)
        """
        if 'execution' in plugin_id:
            return 'functional'
        elif any(x in plugin_id for x in ['cognitive', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'oracle', 'memory']):
            return 'cognitive'
        elif 'sensory' in plugin_id or 'telemetry' in plugin_id:
            return 'sensory'
        elif 'simulation' in plugin_id:
            return 'simulation'
        elif 'weight' in plugin_id:
            return 'governance'
        elif 'model_provider' in plugin_id:
            return 'llm'
        else:
            return 'functional'
