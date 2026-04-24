from __future__ import annotations
"""
Phase B2: ExecutorRegistry for managing external executors.
Stores and indexes executors by type, capability, and quality metrics.
"""

import logging
from typing import Any, Dict, List, Optional
from zentex.tasks.dispatch.models import (
    ExecutorCandidate,
    ExecutorType,
)

logger = logging.getLogger(__name__)


class ExecutorRegistry:
    """
    Phase B2: Registry for managing external executors.
    Supports lookup by type, capability, and quality metrics.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._executors: Dict[str, ExecutorCandidate] = {}  # executor_id -> candidate
        self._by_type: Dict[ExecutorType, List[str]] = {  # executor_type -> [executor_ids]
            ExecutorType.EXTERNAL_MCP: [],
            ExecutorType.EXTERNAL_AGENT: [],
            ExecutorType.EXTERNAL_CLI: [],
        }
        self._by_capability: Dict[str, List[str]] = {}  # capability -> [executor_ids]
    
    def register(
        self,
        executor: ExecutorCandidate,
    ) -> None:
        """
        Phase B2: Register a new executor in the registry.
        
        Args:
            executor: ExecutorCandidate with all metadata
        """
        if executor.executor_id in self._executors:
            logger.warning(f"Executor {executor.executor_id} already registered; updating")
        
        self._executors[executor.executor_id] = executor
        
        # Index by type
        if executor.executor_type in self._by_type:
            if executor.executor_id not in self._by_type[executor.executor_type]:
                self._by_type[executor.executor_type].append(executor.executor_id)
        
        # Index by capability
        for cap in executor.required_capabilities or []:
            if cap not in self._by_capability:
                self._by_capability[cap] = []
            if executor.executor_id not in self._by_capability[cap]:
                self._by_capability[cap].append(executor.executor_id)
        
        logger.debug(f"Registered external executor {executor.executor_id} ({executor.executor_type})")
    
    def unregister(self, executor_id: str) -> bool:
        """
        Phase B2: Unregister an executor.
        
        Returns:
            True if executor was found and unregistered, False otherwise
        """
        if executor_id not in self._executors:
            return False
        
        executor = self._executors.pop(executor_id)
        
        # Remove from type index
        for executor_type in self._by_type:
            if executor_id in self._by_type[executor_type]:
                self._by_type[executor_type].remove(executor_id)
        
        # Remove from capability index
        for cap in executor.required_capabilities or []:
            if cap in self._by_capability and executor_id in self._by_capability[cap]:
                self._by_capability[cap].remove(executor_id)
        
        logger.debug(f"Unregistered executor {executor_id}")
        return True
    
    def get(self, executor_id: str) -> Optional[ExecutorCandidate]:
        """Get executor by ID."""
        return self._executors.get(executor_id)
    
    def get_by_type(self, executor_type: ExecutorType) -> List[ExecutorCandidate]:
        """Get all executors of a specific type."""
        executor_ids = self._by_type.get(executor_type, [])
        return [self._executors[eid] for eid in executor_ids if eid in self._executors]
    
    def get_by_capability(self, capability: str) -> List[ExecutorCandidate]:
        """Get all executors with a specific capability."""
        executor_ids = self._by_capability.get(capability, [])
        return [self._executors[eid] for eid in executor_ids if eid in self._executors]
    
    def get_by_capabilities(self, capabilities: List[str]) -> List[ExecutorCandidate]:
        """Get executors that have ALL specified capabilities."""
        if not capabilities:
            return list(self._executors.values())
        
        # Find intersection of executors for each capability
        candidate_sets = [set(self.get_by_capability(cap)) for cap in capabilities]
        common_executors = set.intersection(*candidate_sets) if candidate_sets else set()
        return list(common_executors)
    
    def get_best_by_quality(
        self,
        executor_type: Optional[ExecutorType] = None,
        required_capabilities: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[ExecutorCandidate]:
        """
        Phase B2: Get best executors ranked by quality metrics.
        
        Ranking: is_healthy → credit_score → success_rate
        
        Args:
            executor_type: Filter by type (None = all types)
            required_capabilities: Filter by capabilities (None = any capabilities)
            top_k: Number of results to return
        
        Returns:
            List of up to top_k ExecutorCandidate sorted by quality
        """
        # Filter by type
        if executor_type:
            candidates = self.get_by_type(executor_type)
        else:
            candidates = list(self._executors.values())
        
        # Filter by capabilities
        if required_capabilities:
            cap_candidates = set(self.get_by_capabilities(required_capabilities))
            candidates = [c for c in candidates if c in cap_candidates]
        
        # Sort by quality
        candidates.sort(
            key=lambda c: (
                -int(c.is_healthy),
                -c.credit_score,
                -c.success_rate,
            ),
        )
        
        return candidates[:top_k]
    
    def get_all(self) -> List[ExecutorCandidate]:
        """Get all registered executors."""
        return list(self._executors.values())
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get summary of registry health."""
        all_executors = self.get_all()
        healthy_count = sum(1 for e in all_executors if e.is_healthy)
        
        return {
            "total_executors": len(all_executors),
            "healthy_executors": healthy_count,
            "by_type": {
                t: len(self.get_by_type(t))
                for t in ExecutorType
            },
            "avg_success_rate": (
                sum(e.success_rate for e in all_executors) / len(all_executors)
                if all_executors else 0.0
            ),
            "avg_credit_score": (
                sum(e.credit_score for e in all_executors) / len(all_executors)
                if all_executors else 0.0
            ),
        }
