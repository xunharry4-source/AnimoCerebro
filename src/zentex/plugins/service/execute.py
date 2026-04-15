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

from zentex.foundation.contracts import ActionIntent

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
    
    def __init__(self, storage, plugin_instances, execution_stats, determine_category_fn=None, promote_fn=None, public_service=None):
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
        self._public_service = public_service

    @staticmethod
    def _normalize_lifecycle_status(value: object) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @staticmethod
    def _normalize_operational_status(value: object) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_result_payload(result: Any) -> Dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        return {"value": result}

    def _derive_operational_status(self, db_plugin: Dict[str, Any]) -> str:
        lifecycle_status = self._normalize_lifecycle_status(db_plugin.get("lifecycle_status"))
        if lifecycle_status != PluginLifecycleStatus.ACTIVE.value:
            return "unavailable"

        if db_plugin.get("stopped_at"):
            return "stopped"

        plugin_id = str(db_plugin.get("plugin_id") or "").strip()
        plugin_instance = self._plugin_instances.get(plugin_id)
        if plugin_instance is None:
            return "stopped"

        health = getattr(plugin_instance, "health_status", None)
        normalized_health = str(getattr(health, "value", health) or "").strip().lower()
        if normalized_health in {"degraded", "unhealthy", "abnormal"}:
            return "abnormal"

        persisted_operational_status = self._normalize_operational_status(
            db_plugin.get("operational_status")
        )
        if persisted_operational_status in {"enabled", "stopped", "abnormal"}:
            return persisted_operational_status
        return "enabled"

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

        lifecycle_status = self._normalize_lifecycle_status(db_plugin.get("lifecycle_status"))
        if lifecycle_status != PluginLifecycleStatus.ACTIVE.value:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_active",
                remarks=f"Plugin {plugin_id} lifecycle_status is {lifecycle_status or 'unknown'}, not ACTIVE."
            )

        operational_status = self._derive_operational_status(db_plugin)
        if operational_status != "enabled":
            logger.warning(
                "[Plugins] Refusing execution for %s trace=%s session=%s turn=%s: lifecycle=%s operational=%s in_memory=%s stopped_at=%s",
                plugin_id,
                trace_id,
                parameters.get("session_id"),
                parameters.get("turn_id"),
                lifecycle_status,
                operational_status,
                plugin_id in self._plugin_instances,
                db_plugin.get("stopped_at"),
            )
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_enabled",
                remarks=(
                    f"Plugin {plugin_id} is ACTIVE but operational_status is "
                    f"{operational_status}, so it cannot execute."
                ),
            )

        # Get plugin instance from memory (with on-demand rehydration)
        plugin_instance = self._plugin_instances.get(plugin_id)
        if not plugin_instance and self._public_service is not None:
            if hasattr(self._public_service, "ensure_runtime_instance_loaded"):
                if self._public_service.ensure_runtime_instance_loaded(plugin_id):
                    plugin_instance = self._plugin_instances.get(plugin_id)

        if not plugin_instance:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_instantiated",
                remarks=(
                    f"Plugin {plugin_id} is ACTIVE in the library but failed to instantiate "
                    "in memory. Check logs for rehydration errors."
                )
            )

        try:
            if isinstance(parameters, dict) and self._public_service is not None:
                parameters.setdefault("plugin_service", self._public_service)
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
                result=self._normalize_result_payload(result) if result is not None else {
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
        # Try to find the canonical execution entrypoint for the plugin type.
        execute_method = None
        selected_method_name = None
        for method_name in ['execute', 'process', 'run', 'handle', 'run_tool']:
            if hasattr(plugin_instance, method_name):
                execute_method = getattr(plugin_instance, method_name)
                selected_method_name = method_name
                break

        family_call_kwargs: Dict[str, Any] = {}
        if execute_method is None:
            execute_method, selected_method_name, family_call_kwargs = self._resolve_functional_family_method(
                plugin_instance=plugin_instance,
                parameters=parameters,
            )

        if not execute_method:
            logger.warning(
                "[Plugins] Plugin instance has no execute/process/run/handle/run_tool method"
            )
            return None
        
        # Build parameters based on method signature
        sig = inspect.signature(execute_method)
        call_kwargs = dict(family_call_kwargs)
        
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
            elif param_name == 'context':
                call_kwargs['context'] = parameters
            elif param_name in parameters:
                # Use parameter from input if available
                call_kwargs[param_name] = parameters[param_name]

        if selected_method_name == 'run_tool' and 'context' not in call_kwargs:
            call_kwargs['context'] = parameters

        # Call with async support
        if inspect.iscoroutinefunction(execute_method):
            result = await execute_method(**call_kwargs)
        else:
            result = execute_method(**call_kwargs)
        
        return result

    def _resolve_functional_family_method(
        self,
        *,
        plugin_instance: Any,
        parameters: Dict[str, Any],
    ) -> tuple[Any | None, str | None, Dict[str, Any]]:
        family_methods: list[tuple[str, Any]] = [
            ("ingest_signal", lambda: {}),
            (
                "sanitize_signal",
                lambda: {"raw_signal": parameters.get("raw_signal", parameters.get("signal", ""))},
            ),
            (
                "interpret_signal",
                lambda: {"signal": parameters.get("signal", parameters.get("sanitized_signal"))},
            ),
            ("capture_host_state", lambda: {"context": parameters}),
            ("get_payload", lambda: {}),
            ("get_forbidden_zones", lambda: {}),
            ("get_downgrade_options", lambda: {"block_context": parameters.get("block_context", parameters)}),
            (
                "refine_task_queue",
                lambda: {
                    "task_queue": parameters.get("task_queue", []),
                    "context": parameters.get("context", parameters),
                },
            ),
            ("apply_posture", lambda: {"decision_trace": parameters.get("decision_trace", parameters)}),
            ("calculate_weight", lambda: {"task_context": parameters.get("task_context", parameters)}),
            ("check_compliance", lambda: {"action_trace": parameters.get("action_trace", parameters)}),
            ("get_whitelist", lambda: {}),
            ("get_agent_scope", lambda: {"agent_id": parameters.get("agent_id", "")}),
            (
                "execute_action",
                lambda: {
                    "intent": self._build_action_intent(parameters),
                    "context": parameters.get("context", parameters),
                },
            ),
        ]

        for method_name, kwargs_factory in family_methods:
            if not hasattr(plugin_instance, method_name):
                continue
            method = getattr(plugin_instance, method_name)
            if not callable(method):
                continue
            return method, method_name, kwargs_factory()
        return None, None, {}

    @staticmethod
    def _build_action_intent(parameters: Dict[str, Any]) -> ActionIntent:
        raw_intent = parameters.get("intent")
        if isinstance(raw_intent, ActionIntent):
            return raw_intent
        if isinstance(raw_intent, dict):
            return ActionIntent.model_validate(raw_intent)
        return ActionIntent(
            action_type=str(parameters.get("action_type") or parameters.get("action_name") or "describe_capability"),
            target=str(parameters.get("target") or ""),
            parameters=dict(parameters.get("parameters") or parameters.get("action_payload") or {}),
            requester_id=str(parameters.get("requester_id") or parameters.get("originator_id") or ""),
        )

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
                    target_lifecycle_status=PluginLifecycleStatus.DEGRADED,
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
