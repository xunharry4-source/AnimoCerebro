"""
Phase B1: Internal executor - handles task dispatch to FUNCTIONAL plugins.
Implements internal plugin lookup, capability matching, and execution.

Routing Priority: Internal plugins have highest priority (executed before external).
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
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
            
            # Execute plugin with subtask content
            # (Concrete implementation depends on plugin interface)
            output = await plugin.execute(
                input_data={
                    "task_id": task_id,
                    "local_id": subtask.local_id,
                    "title": subtask.title,
                    "objective": subtask.objective,
                    "content": subtask.content,
                },
                constraints={
                    "timeout_seconds": subtask.execution_timeout_seconds,
                    "required_capabilities": subtask.required_capabilities,
                },
            )
            
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
