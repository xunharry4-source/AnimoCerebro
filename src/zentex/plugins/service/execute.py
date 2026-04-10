"""
Execution Service: Plugin Execution Management

Handles:
- Plugin execution with real results
- Call hierarchy validation
- Execution statistics tracking
- Automatic degradation on failures
"""

from __future__ import annotations

import logging
import json
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zentex.plugins.models import PluginLifecycleStatus
from zentex.common.protocol import TaskFeedback

logger = logging.getLogger(__name__)


class ExecutionService:
    """
    Provides plugin execution capabilities.
    
    Responsibilities:
    - Execute plugins with real logic
    - Validate call hierarchy
    - Track execution statistics
    - Handle failures and auto-degradation
    """
    
    def __init__(self, storage, plugin_instances, execution_stats, determine_category_fn=None, promote_fn=None):
        """
        Initialize execution service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            execution_stats: Execution statistics cache
            determine_category_fn: Function to determine plugin category
            promote_fn: Function to promote plugin to new status
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._execution_stats = execution_stats
        self._determine_category = determine_category_fn
        self._promote_plugin = promote_fn

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
        
        Args:
            plugin_id: ID of plugin to execute
            task_id: Task identifier
            parameters: Parameters to pass to plugin
            trace_id: Trace identifier for logging
            originator_id: ID of request originator
            caller_plugin_id: Optional caller plugin ID for hierarchy validation
            
        Returns:
            TaskFeedback with execution result
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

        # Validate call hierarchy constraints if caller is a plugin
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
        
        Args:
            plugin_instance: The instantiated plugin object
            task_id: Task identifier
            parameters: Parameters dict
            trace_id: Trace identifier
            originator_id: Originator identifier
            
        Returns:
            Plugin execution result
        """
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
        - Cognitive → Cognitive: ❌ DENIED
        - Cognitive → Functional: ✅ ALLOWED
        - Functional → Anything: ❌ DENIED
        
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
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="target_plugin_not_registered",
                remarks=f"Target plugin {target_plugin_id} is not registered."
            )
        
        target_category = target_db.get("category", "functional")

        # Rule 1: Cognitive cannot call Cognitive
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

        # Rule 2: Functional cannot call anything
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

        # Rule 3: All others are allowed (cognitive → functional)
        logger.debug(
            f"[Plugins] Call allowed: {caller_category} plugin {caller_plugin_id} "
            f"→ {target_category} plugin {target_plugin_id} (trace: {trace_id})"
        )
        return None

    def _record_successful_execution(self, plugin_id: str) -> None:
        """
        Record successful plugin execution.
        
        Args:
            plugin_id: The plugin that was executed
        """
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
        """
        Record failed plugin execution and possibly degrade.
        
        Args:
            plugin_id: The plugin that failed
            error_msg: Error message
        """
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
        if stats['failure_count'] >= 3 and self._promote_plugin:
            logger.warning(f"[Plugins] Auto-degrading {plugin_id} after 3 failures")
            try:
                self._promote_plugin(
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
