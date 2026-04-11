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
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.storage import PluginStorage
from zentex.plugins.manager import PluginManager
from zentex.plugins.plugin_ids import iter_plugin_id_aliases

logger = logging.getLogger(__name__)


def _bind_factory_plugin_id(plugin_id: str, factory: Callable) -> Callable:
    def _factory():
        try:
            return factory(plugin_id=plugin_id)
        except TypeError:
            return factory()

    return _factory


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
        build_default_environment_interpreter_plugin,
        build_default_prompt_injection_sanitizer_plugin,
        build_default_webhook_ingest_plugin,
        build_default_host_telemetry_plugin,
        build_default_market_simulator,
        build_default_thought_sandbox,
        WeightPluginAssembler,
        build_default_conservative_weight,
    )
    
    base_catalog = {
        # Execution Plugins
        'execution_cloud_browser': _bind_factory_plugin_id('execution_cloud_browser', build_default_cloud_browser_executor),
        'execution_local_system': _bind_factory_plugin_id('execution_local_system', build_default_local_system_executor),
        # Cognitive Plugins
        'cognitive_budget_conflict': _bind_factory_plugin_id('cognitive_budget_conflict', build_budget_conflict_plugin),
        'cognitive_expired_assumption': _bind_factory_plugin_id('cognitive_expired_assumption', build_expired_assumption_cleaner_plugin),
        'cognitive_failure_cluster': _bind_factory_plugin_id('cognitive_failure_cluster', build_failure_mode_cluster_plugin),
        'cognitive_semantic_conflict': _bind_factory_plugin_id('cognitive_semantic_conflict', build_semantic_conflict_plugin),
        # Memory Plugins
        'memory_extractor': _bind_factory_plugin_id('memory_extractor', build_memory_extractor_plugin),
        # Nine Questions Plugins
        'nine-question-q1-where-am-i': _bind_factory_plugin_id('nine-question-q1-where-am-i', build_q1_where_am_i_plugin),
        'nine-question-q2-who-am-i': _bind_factory_plugin_id('nine-question-q2-who-am-i', build_q2_who_am_i_plugin),
        'nine-question-q3-what-do-i-have': _bind_factory_plugin_id('nine-question-q3-what-do-i-have', build_q3_what_do_i_have_plugin),
        'nine-question-q4-what-can-i-do': _bind_factory_plugin_id('nine-question-q4-what-can-i-do', build_q4_what_can_i_do_plugin),
        'nine-question-q5-what-am-i-allowed-to-do': _bind_factory_plugin_id('nine-question-q5-what-am-i-allowed-to-do', build_q5_what_am_i_allowed_to_do_plugin),
        'nine-question-q6-what-should-i-not-do': _bind_factory_plugin_id('nine-question-q6-what-should-i-not-do', build_q6_what_should_i_not_do_plugin),
        'nine_question_q7_alternatives': _bind_factory_plugin_id('nine_question_q7_alternatives', build_q7_what_else_can_i_do_plugin),
        'nine_question_q8_decision': _bind_factory_plugin_id('nine_question_q8_decision', build_q8_what_should_i_do_now_plugin),
        'nine_question_q9_posture': _bind_factory_plugin_id('nine_question_q9_posture', build_q9_how_should_i_act_plugin),
        # Oracle Plugins
        'oracle_alternative': _bind_factory_plugin_id('oracle_alternative', build_default_alternative_oracle),
        'oracle_objective': _bind_factory_plugin_id('oracle_objective', build_default_objective_oracle),
        'oracle_posture': _bind_factory_plugin_id('oracle_posture', build_default_posture_oracle),
        'oracle_redline': _bind_factory_plugin_id('oracle_redline', build_default_redline_oracle),
        # Reflection Plugins
        'reflection_generator': _bind_factory_plugin_id('reflection_generator', build_reflection_generator_plugin),
        # Model Provider Plugins
        'model_provider_tools': _bind_factory_plugin_id('model_provider_tools', build_default_provider_tools_model_provider),
        # Sensory Plugins
        'sensory_environment': _bind_factory_plugin_id('sensory_environment', build_default_environment_interpreter_plugin),
        'sensory_injection_sanitizer': _bind_factory_plugin_id('sensory_injection_sanitizer', build_default_prompt_injection_sanitizer_plugin),
        'sensory_webhook': _bind_factory_plugin_id('sensory_webhook', build_default_webhook_ingest_plugin),
        'sensory_telemetry': _bind_factory_plugin_id('sensory_telemetry', build_default_host_telemetry_plugin),
        # Simulation Plugins
        'simulation_market': _bind_factory_plugin_id('simulation_market', build_default_market_simulator),
        'simulation_thought': _bind_factory_plugin_id('simulation_thought', build_default_thought_sandbox),
        # Weight Plugins
        'weight_assembler': _bind_factory_plugin_id('weight_assembler', WeightPluginAssembler),
        'weight_conservative': _bind_factory_plugin_id('weight_conservative', build_default_conservative_weight),
    }

    # Resolve through the internal startup wrapper over src/plugins plugin units.
    try:
        from zentex.plugins.startup import resolve_registry_factories

        return dict(resolve_registry_factories(base_catalog))
    except Exception as exc:
        logger.warning(f"[Plugins] Failed to resolve registry factories, fallback to base catalog: {exc}")
        return base_catalog


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
    _CATALOG_CONFIG_CACHE: Dict[str, Dict[str, str]] | None = None

    @classmethod
    def _get_plugin_catalog_config(cls) -> Dict[str, Dict[str, str]]:
        """Load plugin metadata from discovered plugin unit directories.

        Primary source:
            src/plugins/<plugin>/plugin.json
            src/plugins/<group>/<plugin>/plugin.json

        Legacy fallback:
            src/plugins/plugin_catalog.json

        Returns:
            Mapping: plugin_id -> {"name": str, "description": str}
        """
        if cls._CATALOG_CONFIG_CACHE is not None:
            return cls._CATALOG_CONFIG_CACHE

        try:
            catalog: Dict[str, Dict[str, str]] = {}

            discovered_dirs = []
            try:
                from zentex.plugins.startup import discover_plugin_unit_directories

                discovered_dirs = discover_plugin_unit_directories()
            except Exception as exc:
                logger.warning(f"[Plugins] Failed discovering plugin unit dirs for metadata: {exc}")

            for plugin_dir in discovered_dirs:
                metadata_path = plugin_dir / "plugin.json"
                if not metadata_path.exists():
                    continue
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning(f"[Plugins] Invalid JSON in {metadata_path}")
                    continue

                plugin_id = str(metadata.get("plugin_id", "")).strip()
                if not plugin_id:
                    logger.warning(f"[Plugins] Missing plugin_id in {metadata_path}")
                    continue

                name = str(metadata.get("name", "")).strip()
                description = str(metadata.get("description", "")).strip()
                if not name and not description:
                    continue
                catalog[plugin_id] = {
                    "name": name,
                    "description": description,
                }

            if catalog:
                cls._CATALOG_CONFIG_CACHE = catalog
                logger.info(
                    f"[Plugins] Loaded plugin unit metadata for {len(catalog)} plugins"
                )
                return cls._CATALOG_CONFIG_CACHE

            # Fallback: legacy central catalog
            config_path = Path(__file__).resolve().parents[3] / "plugins" / "plugin_catalog.json"
            if not config_path.exists():
                logger.info(f"[Plugins] Plugin unit metadata and central catalog not found: {config_path}")
                cls._CATALOG_CONFIG_CACHE = {}
                return cls._CATALOG_CONFIG_CACHE

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            plugins = payload.get("plugins") if isinstance(payload, dict) else None
            if not isinstance(plugins, dict):
                logger.warning(f"[Plugins] Invalid catalog config schema in {config_path}")
                cls._CATALOG_CONFIG_CACHE = {}
                return cls._CATALOG_CONFIG_CACHE

            for plugin_id, metadata in plugins.items():
                if not isinstance(plugin_id, str) or not isinstance(metadata, dict):
                    continue
                name = str(metadata.get("name", "")).strip()
                description = str(metadata.get("description", "")).strip()
                if not name and not description:
                    continue
                catalog[plugin_id] = {
                    "name": name,
                    "description": description,
                }

            cls._CATALOG_CONFIG_CACHE = catalog
            logger.info(f"[Plugins] Loaded catalog metadata for {len(catalog)} plugins")
            return cls._CATALOG_CONFIG_CACHE
        except Exception as exc:
            logger.warning(f"[Plugins] Failed to load catalog config: {exc}")
            cls._CATALOG_CONFIG_CACHE = {}
            return cls._CATALOG_CONFIG_CACHE

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

    def _index_plugin_runtime_state(
        self,
        plugin_id: str,
        *,
        instance: Any | None = None,
        spec_dict: Dict[str, Any] | None = None,
        execution_stats: Dict[str, Any] | None = None,
    ) -> None:
        for alias in iter_plugin_id_aliases(plugin_id):
            if instance is not None:
                self._plugin_instances[alias] = instance
            if spec_dict is not None:
                self._plugin_specs[alias] = spec_dict
            if execution_stats is not None:
                self._execution_stats[alias] = execution_stats

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

                if plugin_id not in self._plugin_instances:
                    factory = self._get_factories().get(plugin_id)
                    if factory:
                        try:
                            self._plugin_instances[plugin_id] = factory()
                        except Exception as e:
                            logger.warning(f"[Plugins] Failed to instantiate {plugin_id}: {e}")

                if record["status"] == PluginLifecycleStatus.ACTIVE.value and plugin_id in self._plugin_instances:
                    active_count += 1
                        
                # Initialize execution stats
                if plugin_id not in self._execution_stats:
                    self._execution_stats[plugin_id] = {
                        'usage_count': record.get('usage_count', 0),
                        'failure_count': record.get('failure_count', 0),
                        'last_executed_at': None,
                    }
                self._index_plugin_runtime_state(
                    plugin_id,
                    instance=self._plugin_instances.get(plugin_id),
                    spec_dict=self._plugin_specs.get(plugin_id),
                    execution_stats=self._execution_stats.get(plugin_id),
                )
                    
            except Exception as exc:
                logger.error(f"[Plugins] Failed to load {plugin_id}: {exc}")

        self._seed_default_relationships()
        
        logger.info(f"[Plugins] Bootstrap complete. {active_count} plugins active, {len(self._plugin_instances)} instantiated.")

    def _load_and_instantiate_plugins(self) -> None:
        """
        Instantiate all built-in plugins from factory functions
        and register them to the database if not already registered.
        """
        registered = {r['plugin_id'] for r in self._storage.list_plugins()}
        catalog = self._get_plugin_catalog_config()
        
        for plugin_id, factory in self._get_factories().items():
            if plugin_id in registered:
                continue  # Already registered, skip
            
            try:
                logger.info(f"[Plugins] Instantiating new plugin: {plugin_id}")
                instance = factory()
                
                # Determine category from plugin_id
                category = self._determine_category(plugin_id)
                
                # Create spec from instance
                catalog_item = catalog.get(plugin_id, {})
                configured_name = str(catalog_item.get("name", "")).strip()
                configured_description = str(catalog_item.get("description", "")).strip()
                fallback_name = str(getattr(instance, 'display_name', '') or '').strip()
                fallback_description = str(
                    getattr(instance, 'description', '') or getattr(instance, 'purpose', '') or ''
                ).strip()

                spec_dict = {
                    'plugin_id': plugin_id,
                    'version': getattr(instance, 'version', '1.0.0'),
                    'status': PluginLifecycleStatus.CANDIDATE.value,
                    'category': category,
                    'behavior_key': getattr(instance, 'behavior_key', None),
                    'feature_code': getattr(instance, 'feature_code', plugin_id),
                    'display_name': configured_name or fallback_name or plugin_id,
                    'description': configured_description or fallback_description,
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
                self._index_plugin_runtime_state(
                    plugin_id,
                    instance=instance,
                    spec_dict=spec_dict,
                )
                
            except Exception as e:
                logger.error(f"[Plugins] Failed to register {plugin_id}: {e}")

    def _seed_default_relationships(self) -> None:
        q1_cognitive_id = "nine-question-q1-where-am-i"
        q1_functional_bindings = [
            ("sensory_webhook", "primary", 1),
            ("sensory_injection_sanitizer", "primary", 2),
            ("sensory_environment", "primary", 3),
            ("sensory_telemetry", "support", 4),
        ]

        if not self._storage.get_plugin(q1_cognitive_id):
            return

        for functional_plugin_id, role, priority in q1_functional_bindings:
            if not self._storage.get_plugin(functional_plugin_id):
                continue
            if self._storage.get_relation(q1_cognitive_id, functional_plugin_id):
                continue
            self._storage.create_relation(
                cognitive_plugin_id=q1_cognitive_id,
                functional_plugin_id=functional_plugin_id,
                role=role,
                priority=priority,
            )

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
