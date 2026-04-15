"""
Phase B1: TaskRouter interface defining the contract for dispatch logic.
Responsible for selecting executors (internal/external) for subtasks.

Routing Policy (per requirements):
- Internal: PluginLayer.FUNCTIONAL plugins (highest priority)
- External: MCP/AGENT/CLI executors (ranked by credit/quality evidence)
- Fallback Chain: Try internal first; if no match, fall back to external ranked by quality
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from zentex.tasks.models import SubtaskIntent
from zentex.tasks.dispatch.models import (
    ExecutorCandidate,
    DispatchDecision,
    DispatchResult,
    ExecutorType,
)


class TaskRouter(ABC):
    """
    Abstract interface for task routing and executor selection.
    Concrete implementations handle internal vs external dispatch logic.
    """
    
    @abstractmethod
    async def get_dispatch_decision(
        self,
        subtask: SubtaskIntent,
        task_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DispatchDecision:
        """
        Phase B1: Select executor for a subtask.
        
        Args:
            subtask: The subtask to dispatch (has required_capabilities, allowed_executors, etc.)
            task_id: Physical task ID in task management system
            context: Optional routing context (e.g. previous failures, executor health snapshot)
        
        Returns:
            DispatchDecision with selected executor and fallback chain.
        
        Routing Algorithm:
            1. Query internal .FUNCTIONAL plugins matching required_capabilities
            2. If found, return highest-ranked internal candidate
            3. If no internal match, query external executors (MCP/AGENT/CLI)
            4. Rank external candidates by credit_score, success_rate, health
            5. Return best external candidate
            6. If no candidates at all, escalate with empty decision (caller handles escalation)
        
        Raises:
            ValueError: If subtask has no required_capabilities and no default routing policy
        """
        pass
    
    @abstractmethod
    async def record_execution_result(
        self,
        result: DispatchResult,
    ) -> None:
        """
        Phase B1+: Record task execution outcome for credit/quality feedback.
        
        Updates executor credit scores, success rates, and other metrics
        used for future executor ranking.
        
        Args:
            result: Execution outcome with success/failure and executor_id
        
        Raises:
            ValueError: If result references non-existent executor_id
        """
        pass
    
    @abstractmethod
    async def get_executor_health_snapshot(self) -> Dict[str, Any]:
        """
        Phase B1: Get current health status of all available executors.
        
        Returns:
            Dict with executor_id -> {is_healthy, success_rate, times_selected, credit_score}
        """
        pass
    
    @abstractmethod
    async def register_executor(
        self,
        executor_id: str,
        executor_type: ExecutorType,
        executor_name: str,
        initial_credit_score: float = 1.0,
    ) -> None:
        """
        Phase B1: Register a new executor in the routing system.
        
        Args:
            executor_id: Unique identifier for the executor
            executor_type: INTERNAL_PLUGIN, EXTERNAL_MCP, EXTERNAL_AGENT, or EXTERNAL_CLI
            executor_name: Human-readable name
            initial_credit_score: Starting credit score (default 1.0)
        """
        pass
    
    @abstractmethod
    async def list_candidates_for_subtask(
        self,
        subtask: SubtaskIntent,
    ) -> List[ExecutorCandidate]:
        """
        Phase B1: List all candidate executors for a subtask (before ranking/selection).
        
        Useful for debugging, manual routing override, or audit trail.
        
        Returns:
            Unranked list of ExecutorCandidate matching subtask requirements.
        """
        pass
    
    @abstractmethod
    async def update_executor_capability(
        self,
        executor_id: str,
        capability: str,
        is_supported: bool,
    ) -> None:
        """
        Phase B1: Dynamically update executor's supported capabilities.
        
        Args:
            executor_id: Executor to update
            capability: Capability tag to add/remove
            is_supported: True to add, False to remove
        """
        pass
