from __future__ import annotations

import logging
import json
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable

from zentex.plugins.models import BasePluginSpec, PluginLifecycleStatus
from zentex.plugins.manager import PluginManager
from zentex.plugins.storage import PluginStorage
from zentex.common.protocol import TaskEnvelope, TaskFeedback

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


class SystemPluginService:
    """
    Core Plugin Governance Service for Zentex.
    
    Responsibilities:
    1. Register internal plugins from src/plugins/ directory
    2. Query available plugins by category, status, behavior_key
    3. Execute registered plugins and return results
    4. Persist plugin metadata and execution records
    """
    
    # Class-level cache for plugin factories (lazily loaded)
    _FACTORIES_CACHE = None

    def __init__(
        self, 
        db_path: str,
        manager: Optional[PluginManager] = None, 
    ) -> None:
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
        """Determine plugin category from ID."""
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

    def _validate_plugin_call_hierarchy(
        self,
        *,
        caller_plugin_id: str,
        target_plugin_id: str,
        trace_id: str,
    ) -> Optional[TaskFeedback]:
        """
        Validate that a plugin call respects the classification constraints.
        
        Rules:
        - ✅ Cognitive → Cognitive: ❌ DENIED (avoid circular logic)
        - ✅ Cognitive → Functional: ✅ ALLOWED (cognitive orchestrates functional)
        - ❌ Functional → Anything: ❌ DENIED (functional must stay independent)
        
        Args:
            caller_plugin_id: The plugin attempting to call
            target_plugin_id: The plugin being called
            trace_id: For logging
            
        Returns:
            TaskFeedback with error if constraint violated, None if allowed
        """
        # Get caller's category
        caller_db = self._storage.get_plugin(caller_plugin_id)
        if not caller_db:
            # Caller plugin not found in registry - unknown plugin
            logger.warning(
                f"[Plugins] Call attempt from unregistered plugin {caller_plugin_id} "
                f"to {target_plugin_id} (trace: {trace_id})"
            )
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="caller_plugin_not_registered",
                remarks=f"Caller plugin {caller_plugin_id} is not registered."
            )

        caller_category = caller_db.get("category", "functional")
        
        # Get target's category  
        target_db = self._storage.get_plugin(target_plugin_id)
        if not target_db:
            # This should have been caught earlier, but be safe
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="target_plugin_not_registered",
                remarks=f"Target plugin {target_plugin_id} is not registered."
            )
        
        target_category = target_db.get("category", "functional")

        # ✅ Rule 1: Cognitive cannot call Cognitive
        if caller_category == "cognitive" and target_category == "cognitive":
            log_msg = (
                f"[Plugins] CONSTRAINT VIOLATION: Cognitive plugin {caller_plugin_id} "
                f"attempted to call cognitive plugin {target_plugin_id} (trace: {trace_id})"
            )
            logger.error(log_msg)
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="call_hierarchy_violation",
                remarks=f"Cognitive plugin cannot call another cognitive plugin. "
                        f"Caller: {caller_plugin_id}, Target: {target_plugin_id}"
            )

        # ✅ Rule 2: Functional cannot call anything
        if caller_category == "functional":
            log_msg = (
                f"[Plugins] CONSTRAINT VIOLATION: Functional plugin {caller_plugin_id} "
                f"attempted to call {target_category} plugin {target_plugin_id} (trace: {trace_id})"
            )
            logger.error(log_msg)
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="call_hierarchy_violation",
                remarks=f"Functional plugin cannot call other plugins. "
                        f"Caller: {caller_plugin_id}, Target: {target_plugin_id}"
            )

        # ✅ Rule 3: All others are allowed (cognitive → functional)
        logger.debug(
            f"[Plugins] Call allowed: {caller_category} plugin {caller_plugin_id} "
            f"→ {target_category} plugin {target_plugin_id} (trace: {trace_id})"
        )
        return None

    def get_active_inventory(self) -> List[Dict[str, Any]]:
        """
        Return list of currently ACTIVE plugins.
        This is the current usable plugins list.
        """
        records = self._storage.list_plugins()
        active_plugins = []
        
        for r in records:
            if r["status"] == PluginLifecycleStatus.ACTIVE.value:
                active_plugins.append({
                    "plugin_id": r["plugin_id"],
                    "category": r["category"],
                    "version": r["version"],
                    "status": r["status"],
                    "behavior_key": r["behavior_key"],
                    "feature_code": r.get("feature_code", r["plugin_id"]),
                    "instantiated": r["plugin_id"] in self._plugin_instances,
                })
        
        return active_plugins

    def get_plugin_execution_stats(self, plugin_id: str) -> Dict[str, Any]:
        """Get execution statistics for a plugin."""
        if plugin_id not in self._execution_stats:
            db_plugin = self._storage.get_plugin(plugin_id)
            if db_plugin:
                self._execution_stats[plugin_id] = {
                    'usage_count': db_plugin.get('usage_count', 0),
                    'failure_count': db_plugin.get('failure_count', 0),
                    'last_executed_at': None,
                }
            else:
                return {}
        
        return self._execution_stats[plugin_id]


    def query_plugins(
        self,
        *,
        category: Optional[str] = None,
        status: str = PluginLifecycleStatus.ACTIVE.value,
        behavior_key: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Query available plugins for callers.

        Note: This method only returns list metadata and an execution contract.
        Caller decides whether to execute sequentially or concurrently.
        """
        target_limit = max(1, min(limit, 500))
        records = self._storage.list_plugins(category=category if category in {"cognitive", "functional"} else None)

        items: List[Dict[str, Any]] = []
        for record in records:
            if status and record.get("status") != status:
                continue
            if behavior_key and record.get("behavior_key") != behavior_key:
                continue

            items.append(
                {
                    "plugin_id": record.get("plugin_id"),
                    "category": record.get("category"),
                    "version": record.get("version"),
                    "status": record.get("status"),
                    "behavior_key": record.get("behavior_key"),
                    "execution_contract": {
                        "method": "execute_plugin_once",
                        "required_fields": ["plugin_id", "task_id", "parameters", "trace_id", "originator_id"],
                    },
                }
            )

        return {
            "query_id": f"plugin-query-{uuid4()}",
            "total": len(items),
            "items": items[:target_limit],
            "truncated": len(items) > target_limit,
        }

    async def execute_plugin_once(
        self,
        *,
        plugin_id: str,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
        caller_plugin_id: Optional[str] = None,
    ) -> TaskFeedback:
        """
        Execute exactly one registered plugin instance.
        
        Flow:
        1. Validate plugin_id
        2. Validate call hierarchy constraints (classification rules)
        3. Check plugin is ACTIVE
        4. Get plugin instance from _plugin_instances
        5. Call plugin's execute method
        6. Return real execution result
        
        Note: caller_plugin_id is optional. If provided, verifies that the call
        hierarchy follows plugin classification rules (cognitive can call functional,
        functional cannot call anything, etc.)
        """
        if not plugin_id:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_found",
                remarks="Missing plugin_id."
            )

        # Validate plugin exists in database
        db_plugin = self._storage.get_plugin(plugin_id)
        if not db_plugin:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_found",
                remarks=f"Plugin {plugin_id} not registered in database."
            )

        # ✅ NEW: Validate call hierarchy constraints if caller is a plugin
        if caller_plugin_id:
            constraint_error = self._validate_plugin_call_hierarchy(
                caller_plugin_id=caller_plugin_id,
                target_plugin_id=plugin_id,
                trace_id=trace_id
            )
            if constraint_error:
                return constraint_error

        # Validate plugin is ACTIVE
        if db_plugin.get("status") != PluginLifecycleStatus.ACTIVE.value:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_active",
                remarks=f"Plugin {plugin_id} is {db_plugin.get('status')}, not ACTIVE."
            )

        # Get plugin instance from memory
        plugin_instance = self._plugin_instances.get(plugin_id)
        if not plugin_instance:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_instantiated",
                remarks=f"Plugin {plugin_id} is not instantiated in memory. Call bootstrap() first."
            )

        try:
            # Call actual plugin execution
            # Try different method names that plugins might use
            result = await self._call_plugin_execute(
                plugin_instance=plugin_instance,
                task_id=task_id,
                parameters=parameters,
                trace_id=trace_id,
                originator_id=originator_id
            )
            
            # Update execution stats
            self._record_successful_execution(plugin_id)
            
            return TaskFeedback(
                task_id=task_id,
                status="done",
                result=result if result else {
                    "plugin_id": plugin_id,
                    "trace_id": trace_id,
                    "parameters": parameters,
                },
                progress=1.0,
                remarks=f"Plugin {plugin_id} executed successfully."
            )
            
        except Exception as exc:
            logger.error(f"[Plugins] Execution error in {plugin_id}: {exc}", exc_info=True)
            
            # Update failure stats
            self._record_failed_execution(plugin_id, str(exc))
            
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="execution_error",
                result={
                    "plugin_id": plugin_id,
                    "error": str(exc),
                },
                remarks=f"Plugin {plugin_id} execution failed: {exc}"
            )

    async def _call_plugin_execute(
        self,
        *,
        plugin_instance: Any,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Call the plugin's execute method with proper parameter mapping.
        Supports multiple method signatures.
        """
        import inspect
        
        # Try to find execute method
        execute_method = None
        for method_name in ['execute', 'process', 'run', 'handle']:
            if hasattr(plugin_instance, method_name):
                execute_method = getattr(plugin_instance, method_name)
                break
        
        if not execute_method:
            logger.warning(f"[Plugins] Plugin instance has no execute/process/run/handle method")
            return None
        
        # Build parameters based on method signature
        sig = inspect.signature(execute_method)
        call_kwargs = {}
        
        for param_name in sig.parameters:
            if param_name == 'self':
                continue
            elif param_name == 'task_id':
                call_kwargs['task_id'] = task_id
            elif param_name == 'parameters' or param_name == 'input':
                call_kwargs[param_name] = parameters
            elif param_name == 'trace_id':
                call_kwargs['trace_id'] = trace_id
            elif param_name == 'originator_id':
                call_kwargs['originator_id'] = originator_id
            elif param_name in parameters:
                # Use parameter from input if available
                call_kwargs[param_name] = parameters[param_name]
        
        # Call with async support
        if inspect.iscoroutinefunction(execute_method):
            result = await execute_method(**call_kwargs)
        else:
            result = execute_method(**call_kwargs)
        
        return result

    def _record_successful_execution(self, plugin_id: str) -> None:
        """Record successful plugin execution."""
        if plugin_id not in self._execution_stats:
            self._execution_stats[plugin_id] = {
                'usage_count': 0,
                'failure_count': 0,
                'last_executed_at': None,
            }
        
        stats = self._execution_stats[plugin_id]
        stats['usage_count'] += 1
        stats['failure_count'] = 0  # Reset on success
        stats['last_executed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update database
        db_plugin = self._storage.get_plugin(plugin_id)
        if db_plugin:
            spec_dict = json.loads(db_plugin['spec_json'])
            self._storage.upsert_plugin(
                category=db_plugin['category'],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={**db_plugin, 'usage_count': stats['usage_count']}
            )

    def _record_failed_execution(self, plugin_id: str, error_msg: str) -> None:
        """Record failed plugin execution and possibly degrade."""
        if plugin_id not in self._execution_stats:
            self._execution_stats[plugin_id] = {
                'usage_count': 0,
                'failure_count': 0,
                'last_executed_at': None,
            }
        
        stats = self._execution_stats[plugin_id]
        stats['failure_count'] += 1
        stats['last_executed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Auto-degrade after 3 consecutive failures
        if stats['failure_count'] >= 3:
            logger.warning(f"[Plugins] Auto-degrading {plugin_id} after 3 failures")
            try:
                self.promote_plugin(
                    plugin_id=plugin_id,
                    target_status=PluginLifecycleStatus.DEGRADED,
                    reason=f"Auto-degraded after 3 consecutive failures: {error_msg}"
                )
            except Exception as e:
                logger.error(f"[Plugins] Failed to auto-degrade {plugin_id}: {e}")
        
        # Update database
        db_plugin = self._storage.get_plugin(plugin_id)
        if db_plugin:
            spec_dict = json.loads(db_plugin['spec_json'])
            self._storage.upsert_plugin(
                category=db_plugin['category'],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={**db_plugin, 'failure_count': stats['failure_count']}
            )


    def promote_plugin(self, plugin_id: str, target_status: PluginLifecycleStatus, reason: str) -> None:
        """Governance gateway for native plugin state transitions."""
        plugin = self._storage.get_plugin(plugin_id)
        if not plugin:
            raise KeyError(f"Plugin {plugin_id} not found in database.")

        # If promoting to ACTIVE, deactivate conflicting plugins
        if target_status == PluginLifecycleStatus.ACTIVE:
            self._deactivate_conflicting_plugins(plugin_id, plugin.get("behavior_key"), reason)

        now = datetime.now(timezone.utc).isoformat()
        
        # Update spec status
        spec_dict = json.loads(plugin["spec_json"])
        spec_dict["status"] = target_status.value
        
        # Update registration metadata
        registration_update = {
            "status": target_status.value,
            "updated_at": now
        }
        if target_status == PluginLifecycleStatus.ACTIVE:
            registration_update["started_at"] = now
            registration_update["stopped_at"] = None
        elif target_status in {PluginLifecycleStatus.REVOKED, PluginLifecycleStatus.DEGRADED}:
            registration_update["stopped_at"] = now

        # Persist to database
        self._storage.upsert_plugin(
            category=plugin["category"],
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict={**plugin, **registration_update}
        )
        
        # Update memory registry
        self._plugin_specs[plugin_id] = spec_dict
        
        if target_status == PluginLifecycleStatus.ACTIVE:
            # Try to instantiate if not already in memory
            if plugin_id not in self._plugin_instances:
                factory = self._get_factories().get(plugin_id)
                if factory:
                    try:
                        self._plugin_instances[plugin_id] = factory()
                    except Exception as e:
                        logger.warning(f"[Plugins] Failed to instantiate {plugin_id} during promotion: {e}")
        elif plugin_id in self._plugin_instances:
            # Keep instance in memory but mark as inactive
            pass
            
        logger.info(f"[Plugins] {plugin_id} promoted to {target_status.value}. Reason: {reason}")

    def _deactivate_conflicting_plugins(self, plugin_id: str, behavior_key: Optional[str], reason: str) -> None:
        """Deactivate other plugins with same behavior_key."""
        if not behavior_key:
            return
        
        all_plugins = self._storage.list_plugins()
        for p in all_plugins:
            if (p["plugin_id"] != plugin_id and 
                p["behavior_key"] == behavior_key and 
                p["status"] == PluginLifecycleStatus.ACTIVE.value):
                try:
                    self.promote_plugin(
                        plugin_id=p["plugin_id"],
                        target_status=PluginLifecycleStatus.DEGRADED,
                        reason=f"Conflict with {plugin_id}: {reason}"
                    )
                except Exception as e:
                    logger.warning(f"[Plugins] Failed to deactivate conflicting plugin {p['plugin_id']}: {e}")

    def force_enable_plugin(self, plugin_id: str, reason: str) -> None:
        """Force activate a plugin."""
        self.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, reason)

    def force_disable_plugin(self, plugin_id: str, reason: str) -> None:
        """Force degrade a plugin."""
        self.promote_plugin(plugin_id, PluginLifecycleStatus.DEGRADED, reason)

    def register_plugin(
        self,
        plugin_id: str,
        plugin_instance: Any,
        category: str,
        version: str = "1.0.0",
        behavior_key: Optional[str] = None,
    ) -> None:
        """
        Manually register a plugin instance.
        
        This is useful for dynamically registered plugins or external plugins.
        """
        spec_dict = {
            'plugin_id': plugin_id,
            'version': version,
            'status': PluginLifecycleStatus.CANDIDATE.value,
            'category': category,
            'behavior_key': behavior_key,
            'feature_code': getattr(plugin_instance, 'feature_code', plugin_id),
        }
        
        registration = {
            'source_kind': 'manual_registration',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        self._storage.upsert_plugin(
            category=category,
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict=registration
        )
        
        self._plugin_instances[plugin_id] = plugin_instance
        self._plugin_specs[plugin_id] = spec_dict
        
        logger.info(f"[Plugins] Registered new plugin: {plugin_id}")


    async def handle_task(self, envelope: TaskEnvelope) -> TaskFeedback:
        """
        ZTP Implementation: Standardized task entry point for Plugin Pillar.
        Supports call hierarchy validation via 'caller_plugin_id' parameter.
        """
        plugin_id = envelope.parameters.get("plugin_id")
        if not plugin_id:
            return TaskFeedback(
                task_id=envelope.task_id,
                status="failed",
                error="Missing 'plugin_id' in task parameters",
                remarks="Plugin Pillar requires 'plugin_id' parameter."
            )

        # Extract optional caller_plugin_id for constraint checking
        caller_plugin_id = envelope.parameters.get("caller_plugin_id")

        return await self.execute_plugin_once(
            plugin_id=plugin_id,
            task_id=envelope.task_id,
            parameters=envelope.parameters,
            trace_id=envelope.trace_id,
            originator_id=envelope.originator_id,
            caller_plugin_id=caller_plugin_id,
        )


# Backward compatibility name used by runtime/web_console modules.
class PluginGovernanceService(SystemPluginService):
    pass
