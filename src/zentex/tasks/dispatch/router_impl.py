from __future__ import annotations
"""
Phase B2: Unified TaskRouter implementation.
Implements internal FUNCTIONAL plugin priority + external executor fallback.

Routing Priority:
1. Try to find matching FUNCTIONAL plugins (internal)
2. If no internal match, query external executors (MCP/AGENT/CLI)
3. Rank external by credit_score + success_rate + health
4. If no candidates at all, escalate with empty fallback chain
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from zentex.tasks.models import SubtaskIntent
from zentex.tasks.dispatch.models import (
    ExecutorCandidate,
    DispatchDecision,
    DispatchResult,
    ExecutorType,
)
from zentex.tasks.dispatch.errors import DispatchRoutingError, NoMatchingExecutorError
from zentex.tasks.dispatch.router import TaskRouter
from zentex.tasks.dispatch.internal import InternalPluginExecutor

logger = logging.getLogger(__name__)


class UnifiedTaskRouter(TaskRouter):
    """
    Phase B2: Central router implementing the complete routing policy.
    
    Routing Algorithm:
        1. Query internal plugins matching required_capabilities
        2. If found, select highest-ranked internal plugin
        3. If no internal match, query all external executors (MCP/AGENT/CLI)
        4. Rank external by: is_healthy → credit_score → success_rate
        5. Return best candidate with fallback chain
        6. If no candidates, escalate to supervision layer
    """
    
    def __init__(
        self,
        internal_executor: Optional[InternalPluginExecutor] = None,
        external_executor_registry: Optional[Dict[str, ExecutorCandidate]] = None,
        plugin_layer: Any = None,
        transcript_store: Any = None,
    ):
        """
        Initialize unified router.
        
        Args:
            internal_executor: InternalPluginExecutor instance (for FUNCTIONAL plugin dispatch)
            external_executor_registry: Dict of external executors (executor_id -> ExecutorCandidate)
            plugin_layer: Reference to PluginLayer (if not provided via internal_executor)
            transcript_store: Optional audit event store for persistent auditing (Phase F)
        """
        self.internal_executor = internal_executor or InternalPluginExecutor(plugin_layer)
        self.external_executor_registry = external_executor_registry or {}
        self.transcript_store = transcript_store
        self._execution_history: List[DispatchResult] = []
        self._router_decisions: List[DispatchDecision] = []
    
    async def get_dispatch_decision(
        self,
        subtask: SubtaskIntent,
        task_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DispatchDecision:
        """
        Phase B2: Main routing decision logic - internal first, external fallback.
        
        Implements the core routing priority: internal plugins → external executors.
        """
        context = context or {}
        candidate_pool: List[ExecutorCandidate] = []
        selected_executor: Optional[ExecutorCandidate] = None
        decision_logic = ""
        fallback_chain: List[str] = []
        
        try:
            # === PHASE B2: INTERNAL PRIORITY ===
            # Step 1: Try to find internal functional plugins
            if True:  # Always try internal first
                internal_candidates = await self.internal_executor.get_matching_plugins_for_subtask(subtask)
                candidate_pool.extend(internal_candidates)
                
                if internal_candidates:
                    # Select best internal candidate
                    selected_executor = internal_candidates[0]
                    decision_logic = "internal_match"
                    
                    # Build fallback chain: other internal plugins + external best
                    fallback_chain = [c.executor_id for c in internal_candidates[1:3]]  # Up to 2 backups
                    
                    logger.info(
                        f"Routed task {task_id} to internal plugin {selected_executor.executor_id} "
                        f"(match_score={selected_executor.capability_match_score:.2f})"
                    )
                    
                    # Short-circuit: found internal match, no need to query external
                    decision = DispatchDecision(
                        task_id=task_id,
                        selected_executor=selected_executor,
                        candidate_pool=candidate_pool,
                        decision_logic=decision_logic,
                        fallback_chain=fallback_chain,
                        allowed_executor_types=subtask.required_capabilities and [ExecutorType.INTERNAL_PLUGIN],
                        required_capabilities=subtask.required_capabilities or [],
                    )
                    self._record_decision_audit(decision)
                    return decision
            
            # === PHASE B2+: EXTERNAL FALLBACK ===
            # Step 2: If no internal match, try external executors
            external_candidates = await self._get_external_candidates(subtask)
            candidate_pool.extend(external_candidates)
            
            if external_candidates:
                # Select best external candidate
                selected_executor = external_candidates[0]
                decision_logic = "external_best"
                
                # Build fallback chain: other external candidates (ranked by quality)
                fallback_chain = [c.executor_id for c in external_candidates[1:3]]
                
                logger.info(
                    f"Routed task {task_id} to external executor {selected_executor.executor_id} "
                    f"(type={selected_executor.executor_type}, credit={selected_executor.credit_score:.2f})"
                )
                
                decision = DispatchDecision(
                    task_id=task_id,
                    selected_executor=selected_executor,
                    candidate_pool=candidate_pool,
                    decision_logic=decision_logic,
                    fallback_chain=fallback_chain,
                    allowed_executor_types=None,  # No type constraint if external
                    required_capabilities=subtask.required_capabilities or [],
                )
                self._record_decision_audit(decision)
                return decision
            
            # === ESCALATION CASE ===
            # Step 3: No candidates found - escalate to supervision layer
            logger.warning(
                f"No matching executors for task {task_id} "
                f"(required_capabilities={subtask.required_capabilities})"
            )
            raise NoMatchingExecutorError(
                task_id=task_id,
                required_capabilities=subtask.required_capabilities or [],
            )
        
        except NoMatchingExecutorError:
            raise
        except Exception as e:
            logger.error(f"Error in routing decision for task {task_id}: {e}", exc_info=True)
            raise DispatchRoutingError(
                f"Routing decision failed for task {task_id}: {e}"
            ) from e
    
    async def _get_external_candidates(
        self,
        subtask: SubtaskIntent,
    ) -> List[ExecutorCandidate]:
        """Phase B2: Get external executor candidates ranked by quality."""
        candidates = []
        
        required_caps = set(subtask.required_capabilities) if subtask.required_capabilities else set()
        
        for executor_id, candidate in self.external_executor_registry.items():
            # Check capability match
            if required_caps:
                executor_caps = set(candidate.required_capabilities or [])
                if not (required_caps <= executor_caps):
                    continue  # Skip if doesn't have required capabilities
            
            candidates.append(candidate)
        
        # Sort external candidates by quality: is_healthy → credit_score → success_rate
        candidates.sort(
            key=lambda c: (
                -int(c.is_healthy),
                -c.credit_score,
                -c.success_rate,
            ),
        )
        
        return candidates
    
    async def record_execution_result(
        self,
        result: DispatchResult,
    ) -> None:
        """
        Phase B2+: Record execution outcome and update executor credit scores.
        
        Updates executor metrics for future routing decisions.
        """
        self._execution_history.append(result)
        
        # Update executor credit based on outcome
        if result.succeeded:
            credit_delta = 0.1  # Boost for success
            logger.debug(f"Task {result.task_id} succeeded on {result.executor_id}; +0.1 credit")
        else:
            credit_delta = -0.05  # Penalty for failure
            logger.debug(f"Task {result.task_id} failed on {result.executor_id}; -0.05 credit")
        
        # Apply credit update to internal or external executor.  The decision
        # recorded for the real task is the source of truth; constructing a
        # synthetic SubtaskIntent here is invalid because routing contracts
        # require a concrete task_type.
        selected_type = None
        for decision in reversed(self._router_decisions):
            if (
                decision.task_id == result.task_id
                and decision.selected_executor.executor_id == result.executor_id
            ):
                selected_type = decision.selected_executor.executor_type
                break

        if selected_type == ExecutorType.INTERNAL_PLUGIN or (
            selected_type is None and result.executor_id not in self.external_executor_registry
        ):
            # Internal plugin
            self.internal_executor.update_plugin_credit_score(result.executor_id, credit_delta)
        else:
            # External executor
            if result.executor_id in self.external_executor_registry:
                candidate = self.external_executor_registry[result.executor_id]
                candidate.credit_score = max(0.1, min(10.0, candidate.credit_score + credit_delta))
    
    async def get_executor_health_snapshot(self) -> Dict[str, Any]:
        """Phase B2: Get current health of all executors."""
        health = {
            "internal_plugins": {},
            "external_executors": {},
            "timestamp": time.time(),
        }
        
        # Collect internal plugin health
        for plugin_id, metrics in self.internal_executor._plugin_metrics.items():
            health["internal_plugins"][plugin_id] = {
                "is_healthy": metrics.get("is_healthy", True),
                "success_rate": metrics.get("success_rate", 0.5),
                "times_selected": metrics.get("times_selected", 0),
                "credit_score": self.internal_executor._plugin_credit_scores.get(plugin_id, 1.0),
            }
        
        # Collect external executor health
        for executor_id, candidate in self.external_executor_registry.items():
            health["external_executors"][executor_id] = {
                "is_healthy": candidate.is_healthy,
                "success_rate": candidate.success_rate,
                "times_selected": candidate.times_selected,
                "credit_score": candidate.credit_score,
                "executor_type": candidate.executor_type,
            }
        
        return health
    
    async def register_executor(
        self,
        executor_id: str,
        executor_type: ExecutorType,
        executor_name: str,
        initial_credit_score: float = 1.0,
    ) -> None:
        """Phase B2: Register new executor in routing system."""
        if executor_type == ExecutorType.INTERNAL_PLUGIN:
            # Register with internal executor
            self.internal_executor._plugin_credit_scores[executor_id] = initial_credit_score
            self.internal_executor._plugin_metrics[executor_id] = {
                "is_healthy": True,
                "success_rate": 0.5,
                "times_selected": 0,
                "times_succeeded": 0,
                "avg_execution_time_seconds": 0.0,
            }
            logger.debug(f"Registered internal plugin {executor_id} with credit {initial_credit_score}")
        else:
            # Register as external executor
            candidate = ExecutorCandidate(
                executor_id=executor_id,
                executor_type=executor_type,
                executor_name=executor_name,
                has_required_capabilities=True,
                capability_match_score=1.0,
                is_healthy=True,
                success_rate=0.5,
                credit_score=initial_credit_score,
                times_selected=0,
                times_succeeded=0,
                priority_rank=int(executor_type != ExecutorType.INTERNAL_PLUGIN),
                routing_reason=f"Registered {executor_type} executor",
            )
            self.external_executor_registry[executor_id] = candidate
            logger.debug(f"Registered external executor {executor_id} ({executor_type}) with credit {initial_credit_score}")
    
    async def list_candidates_for_subtask(
        self,
        subtask: SubtaskIntent,
    ) -> List[ExecutorCandidate]:
        """Phase B2: List all candidates (internal + external) for a subtask."""
        internal_candidates = await self.internal_executor.get_matching_plugins_for_subtask(subtask)
        external_candidates = await self._get_external_candidates(subtask)
        return internal_candidates + external_candidates
    
    async def update_executor_capability(
        self,
        executor_id: str,
        capability: str,
        is_supported: bool,
    ) -> None:
        """Phase B2: Update executor's supported capabilities."""
        if executor_id in self.external_executor_registry:
            candidate = self.external_executor_registry[executor_id]
            if is_supported:
                if capability not in candidate.required_capabilities:
                    candidate.required_capabilities.append(capability)
            else:
                if capability in candidate.required_capabilities:
                    candidate.required_capabilities.remove(capability)
            logger.debug(f"Updated executor {executor_id} capability {capability}: {is_supported}")

    def _record_decision_audit(self, decision: DispatchDecision) -> None:
        """Phase F: Persistently record dispatch decision logic of a task."""
        self._router_decisions.append(decision)
        if self.transcript_store:
            try:
                from uuid import uuid4
                from zentex.kernel import AuditEventType
                
                self.transcript_store.write_entry(
                    session_id="task-routing-audit",
                    turn_id=str(uuid4()),
                    entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
                    source="UnifiedTaskRouter",
                    trace_id=f"task-audit:{decision.task_id}:task_dispatched",
                    payload=decision.model_dump(mode="json")
                )
            except Exception as e:
                logger.error(f"Failed to record dispatch audit for task {decision.task_id}: {e}")
