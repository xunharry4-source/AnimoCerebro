from __future__ import annotations
"""
Phase B1: Internal executor - handles task dispatch to FUNCTIONAL plugins.
Implements internal plugin lookup, capability matching, and execution.

Routing Priority: Internal plugins have highest priority (executed before external).
"""

import logging
import inspect
from typing import Any, Dict, List, Optional
from zentex.foundation.contracts import ActionIntent
from zentex.tasks.models import SubtaskIntent
from zentex.tasks.dispatch.models import (
    ExecutorCandidate,
    DispatchDecision,
    ExecutorType,
)

logger = logging.getLogger(__name__)


class InternalPluginExecutor:
    """
    Phase B1: Executor that routes subtasks to PluginLayer.FUNCTIONAL plugins.
    
    Responsibilities:
    1. Query available functional plugins by capability
    2. Match subtask required_capabilities to plugin capabilities
    3. Rank plugins by health/success rate
    4. Execute subtask on matched plugin
    5. Record execution results for credit updates
    
    Note: This is a concrete executor; it implements TaskRouter interface indirectly
    via the unified TaskRouter adapter that composes internal + external executors.
    """
    
    def __init__(self, plugin_layer: Any = None):
        """
        Initialize internal executor.
        
        Args:
            plugin_layer: Reference to PluginLayer (can be injected for testing)
        """
        self.plugin_layer = plugin_layer
        self._plugin_registry: Dict[str, Dict[str, Any]] = {}  # Plugin cache
        self._plugin_credit_scores: Dict[str, float] = {}  # Plugin reputation
        self._plugin_metrics: Dict[str, Dict[str, Any]] = {}  # Plugin stats
    
    def set_plugin_layer(self, plugin_layer: Any) -> None:
        """Update the plugin layer reference (for late dependency injection)."""
        self.plugin_layer = plugin_layer
        logger.debug("InternalPluginExecutor: plugin_layer updated.")
    
    async def get_matching_plugins_for_subtask(
        self,
        subtask: SubtaskIntent,
    ) -> List[ExecutorCandidate]:
        """
        Phase B1: Find all FUNCTIONAL plugins that match subtask requirements.
        
        Matching Algorithm:
            1. Get all plugins from PluginLayer.FUNCTIONAL
            2. For each plugin, extract its declared capabilities
            3. Check if plugin capabilities ⊇ subtask.required_capabilities
            4. Score plugins by:
               - capability_match_score: % of required capabilities matched
               - success_rate: historical execution success ratio
               - credit_score: reputation from previous executions
               - is_healthy: current health status
            5. Sort by priority: (is_healthy, success_rate, credit_score)
        
        Args:
            subtask: Subtask with required_capabilities filter
        
        Returns:
            List of ExecutorCandidate (INTERNAL_PLUGIN type) sorted by quality
        """
        candidates = []
        
        if not self.plugin_layer:
            logger.warning("InternalPluginExecutor: No plugin_layer configured; returning empty candidates")
            return candidates
        
        try:
            # Get all functional plugins
            functional_plugins = self.plugin_layer.get_plugins(
                category="FUNCTIONAL",  # Only functional plugins for internal routing
            )
            
            required_caps = set(subtask.required_capabilities) if subtask.required_capabilities else set()
            
            for plugin in functional_plugins:
                plugin_id = plugin.get("id")
                plugin_name = plugin.get("name", plugin_id)
                plugin_capabilities = set(plugin.get("capabilities", []))
                
                # Check capability match
                if required_caps and not (required_caps <= plugin_capabilities):
                    # Plugin doesn't have all required capabilities
                    continue
                
                # Calculate match score
                if required_caps:
                    match_score = len(required_caps & plugin_capabilities) / len(required_caps)
                else:
                    match_score = 1.0  # No requirements = full match
                
                # Get metrics
                metrics = self._plugin_metrics.get(plugin_id, {})
                success_rate = metrics.get("success_rate", 0.5)  # Default 0.5 if no history
                credit_score = self._plugin_credit_scores.get(plugin_id, 1.0)
                is_healthy = metrics.get("is_healthy", True)
                
                # Create candidate
                candidate = ExecutorCandidate(
                    executor_id=plugin_id,
                    executor_type=ExecutorType.INTERNAL_PLUGIN,
                    executor_name=plugin_name,
                    has_required_capabilities=bool(required_caps <= plugin_capabilities),
                    capability_match_score=match_score,
                    is_healthy=is_healthy,
                    success_rate=success_rate,
                    average_execution_time_seconds=metrics.get("avg_execution_time_seconds"),
                    credit_score=credit_score,
                    times_selected=metrics.get("times_selected", 0),
                    times_succeeded=metrics.get("times_succeeded", 0),
                    priority_rank=0,  # Internal plugins always priority 0
                    routing_reason=f"Internal plugin matches {len(required_caps & plugin_capabilities)}/{len(required_caps)} capabilities",
                )
                candidates.append(candidate)
            
            # Sort by quality: is_healthy → success_rate → credit_score
            candidates.sort(
                key=lambda c: (-int(c.is_healthy), -c.success_rate, -c.credit_score),
            )
            
            logger.debug(f"Found {len(candidates)} internal plugins for subtask {subtask.local_id}")
            
        except Exception as e:
            logger.error(f"Error querying internal plugins: {e}")
        
        return candidates
    
    async def execute_on_plugin(
        self,
        plugin_id: str,
        subtask: SubtaskIntent,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Phase B1: Execute subtask on a specific internal plugin.
        
        Args:
            plugin_id: ID of plugin to execute on
            subtask: Subtask to execute
            task_id: Physical task ID (for audit trail)
        
        Returns:
            {
                "succeeded": bool,
                "output": Any (if succeeded),
                "error": str (if failed),
                "duration_seconds": float,
                "failure_classification": str (if failed),
            }
        """
        result = {
            "succeeded": False,
            "output": None,
            "error": None,
            "duration_seconds": 0.0,
            "failure_classification": None,
        }
        
        if not self.plugin_layer:
            result["error"] = "No plugin_layer configured"
            result["failure_classification"] = "system_error"
            return result
        
        try:
            import time
            start = time.time()
            
            # Get plugin
            plugin = self.plugin_layer.get_plugin(plugin_id, category="FUNCTIONAL")
            if not plugin:
                result["error"] = f"Plugin {plugin_id} not found"
                result["failure_classification"] = "plugin_not_found"
                return result
            
            parameters = {
                "task_id": task_id,
                "local_id": subtask.local_id,
                "title": subtask.title,
                "task_type": str(subtask.task_type),
                "objective": subtask.objective,
                "content": subtask.content,
                "input_data": {
                    "task_id": task_id,
                    "local_id": subtask.local_id,
                    "title": subtask.title,
                    "task_type": str(subtask.task_type),
                    "objective": subtask.objective,
                    "content": subtask.content,
                },
                "constraints": {
                    "timeout_seconds": subtask.execution_timeout_seconds,
                    "required_capabilities": subtask.required_capabilities,
                },
            }
            output = await self._invoke_plugin(plugin, parameters)
            
            duration = time.time() - start
            
            result["succeeded"] = True
            result["output"] = output
            result["duration_seconds"] = duration
            
            # Update metrics
            plugin_metrics = self._plugin_metrics.get(plugin_id, {})
            plugin_metrics["times_selected"] = plugin_metrics.get("times_selected", 0) + 1
            plugin_metrics["times_succeeded"] = plugin_metrics.get("times_succeeded", 0) + 1
            plugin_metrics["avg_execution_time_seconds"] = (
                (plugin_metrics.get("avg_execution_time_seconds", 0) * (plugin_metrics["times_selected"] - 1) + duration)
                / plugin_metrics["times_selected"]
            )
            plugin_metrics["success_rate"] = plugin_metrics["times_succeeded"] / plugin_metrics["times_selected"]
            self._plugin_metrics[plugin_id] = plugin_metrics
            
            logger.debug(f"Plugin {plugin_id} executed subtask {subtask.local_id} in {duration:.2f}s")
            
        except asyncio.TimeoutError:
            result["error"] = f"Plugin execution timeout after {subtask.execution_timeout_seconds}s"
            result["failure_classification"] = "timeout"
            self._record_plugin_failure(plugin_id)
            
        except Exception as e:
            result["error"] = f"Plugin execution error: {str(e)}"
            result["failure_classification"] = "execution_error"
            self._record_plugin_failure(plugin_id)
            logger.error(f"Plugin {plugin_id} execution failed: {e}")
        
        return result

    async def _invoke_plugin(self, plugin: Any, parameters: Dict[str, Any]) -> Any:
        """Invoke heterogeneous functional plugin entrypoints using their real signatures."""
        method = None
        call_kwargs: Dict[str, Any] = {}
        for method_name in ("execute", "process", "run", "handle", "run_tool"):
            candidate = getattr(plugin, method_name, None)
            if callable(candidate):
                method = candidate
                break

        if method is None:
            method, call_kwargs = self._resolve_family_method(plugin, parameters)

        if method is None:
            raise AttributeError(f"{plugin.__class__.__name__!s} has no supported execution entrypoint")

        if not call_kwargs:
            signature = inspect.signature(method)
            for name, param in signature.parameters.items():
                if name == "self":
                    continue
                if param.kind is inspect.Parameter.VAR_KEYWORD:
                    call_kwargs.update(parameters)
                    continue
                if name in {"parameters", "input", "context"}:
                    call_kwargs[name] = parameters
                elif name in {"input_data", "data"}:
                    call_kwargs[name] = parameters.get("input_data", parameters)
                elif name == "constraints":
                    call_kwargs[name] = parameters.get("constraints", {})
                elif name in parameters:
                    call_kwargs[name] = parameters[name]
                elif param.default is inspect.Parameter.empty:
                    call_kwargs[name] = parameters

        if inspect.iscoroutinefunction(method):
            return await method(**call_kwargs)
        result = method(**call_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def _resolve_family_method(self, plugin: Any, parameters: Dict[str, Any]) -> tuple[Any, Dict[str, Any]]:
        family_methods: list[tuple[str, Dict[str, Any]]] = [
            ("execute_action", {"intent": self._build_action_intent(parameters), "context": parameters}),
            ("refine_task_queue", {"task_queue": [parameters.get("input_data", parameters)], "context": parameters}),
            ("apply_posture", {"decision_trace": parameters}),
            ("get_downgrade_options", {"block_context": parameters}),
            ("check_compliance", {"action_trace": parameters}),
            ("calculate_weight", {"task_context": parameters}),
            ("sanitize_signal", {"raw_signal": parameters.get("content", "")}),
            ("interpret_signal", {"signal": parameters.get("content", "")}),
            ("capture_host_state", {"context": parameters}),
            ("get_payload", {}),
            ("get_forbidden_zones", {}),
            ("get_whitelist", {}),
        ]
        for method_name, kwargs in family_methods:
            method = getattr(plugin, method_name, None)
            if callable(method):
                return method, kwargs
        return None, {}

    @staticmethod
    def _build_action_intent(parameters: Dict[str, Any]) -> ActionIntent:
        raw_intent = parameters.get("intent")
        if isinstance(raw_intent, ActionIntent):
            return raw_intent
        if isinstance(raw_intent, dict):
            return ActionIntent.model_validate(raw_intent)

        input_data = parameters.get("input_data")
        if not isinstance(input_data, dict):
            input_data = {}

        action_parameters = dict(parameters.get("parameters") or parameters.get("action_payload") or {})
        if not action_parameters:
            action_parameters = {
                "task_id": parameters.get("task_id") or input_data.get("task_id"),
                "local_id": parameters.get("local_id") or input_data.get("local_id"),
                "title": parameters.get("title") or input_data.get("title"),
                "objective": parameters.get("objective") or input_data.get("objective"),
                "content": parameters.get("content") or input_data.get("content"),
                "required_capabilities": list(
                    (parameters.get("constraints") or {}).get("required_capabilities") or []
                ),
            }

        return ActionIntent(
            action_type=str(
                parameters.get("action_type")
                or parameters.get("action_name")
                or input_data.get("action_type")
                or input_data.get("task_type")
                or parameters.get("task_type")
                or "describe_capability"
            ),
            target=str(
                parameters.get("target")
                or input_data.get("target")
                or parameters.get("title")
                or input_data.get("title")
                or parameters.get("content")
                or input_data.get("content")
                or ""
            ),
            parameters=action_parameters,
            requester_id=str(parameters.get("requester_id") or parameters.get("originator_id") or ""),
        )
    
    def _record_plugin_failure(self, plugin_id: str) -> None:
        """Update metrics after plugin failure."""
        plugin_metrics = self._plugin_metrics.get(plugin_id, {})
        plugin_metrics["times_selected"] = plugin_metrics.get("times_selected", 0) + 1
        if plugin_metrics["times_selected"] > 0:
            plugin_metrics["success_rate"] = plugin_metrics.get("times_succeeded", 0) / plugin_metrics["times_selected"]
        self._plugin_metrics[plugin_id] = plugin_metrics
        
        # Reduce credit score on failure
        current_credit = self._plugin_credit_scores.get(plugin_id, 1.0)
        self._plugin_credit_scores[plugin_id] = max(0.1, current_credit * 0.9)  # Decay by 10%
    
    def update_plugin_credit_score(self, plugin_id: str, delta: float) -> None:
        """
        Phase B1+: Update executor credit score based on execution outcome.
        
        Args:
            plugin_id: Plugin to update
            delta: Credit change (positive for success, negative for failure)
        """
        current = self._plugin_credit_scores.get(plugin_id, 1.0)
        self._plugin_credit_scores[plugin_id] = max(0.1, min(10.0, current + delta))
        logger.debug(f"Updated plugin {plugin_id} credit score: {self._plugin_credit_scores[plugin_id]:.2f}")


# Import asyncio for timeout handling
import asyncio
