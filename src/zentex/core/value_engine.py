from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubjectiveWeightProfile(BaseModel):
    """
    User-defined or emergent weighting for decision criteria.
    """
    profile_id: str = Field(default_factory=lambda: f"vwp-{uuid4().hex[:8]}")
    name: str
    weights: Dict[str, float] = Field(..., description="e.g., {'safety': 0.9, 'utility': 0.1}")
    drift_history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ValueEngine:
    """
    Engine to score solutions based on ValueWeightProfiles.
    """
    def __init__(self):
        self._profiles: Dict[str, SubjectiveWeightProfile] = {}
        self._default_profile_id: Optional[str] = None

    def add_profile(self, profile: SubjectiveWeightProfile, is_default: bool = False):
        self._profiles[profile.profile_id] = profile
        if is_default:
            self._default_profile_id = profile.profile_id
        logger.info(f"Added value profile: {profile.name} ({profile.profile_id})")

    def score_solution(self, solution_metrics: Dict[str, float], profile_id: Optional[str] = None) -> float:
        """
        Calculate a weighted score for a solution.
        """
        pid = profile_id or self._default_profile_id
        if not pid or pid not in self._profiles:
             # Fallback to equal weighting if no profile found
             if not solution_metrics: return 0.0
             return sum(solution_metrics.values()) / len(solution_metrics)
             
        profile = self._profiles[pid]
        total_score = 0.0
        total_weight = 0.0
        
        for criterion, weight in profile.weights.items():
            value = solution_metrics.get(criterion, 0.0)
            total_score += value * weight
            total_weight += weight
            
        return total_score / total_weight if total_weight > 0 else 0.0


class ConflictArbiter:
    """
    Arbitrates between conflicting value profiles.
    """
    def arbitrate(self, metrics: Dict[str, float], profiles: List[SubjectiveWeightProfile]) -> Dict[str, Any]:
        """
        Produce a consensus score and identified hotspots of value conflict.
        """
        scores = {}
        for p in profiles:
            score = self._calculate_score(metrics, p)
            scores[p.profile_id] = score
            
        consensus = sum(scores.values()) / len(scores) if scores else 0.0
        variance = (sum((s - consensus)**2 for s in scores.values()) / len(scores))**0.5 if scores else 0.0
        
        return {
            "consensus_score": consensus,
            "variance": variance,
            "hotspots": [c for c, v in metrics.items() if v < 0.3], # Low performing areas
            "conflict_level": "high" if variance > 0.2 else "low"
        }

    def _calculate_score(self, metrics: Dict[str, float], profile: SubjectiveWeightProfile) -> float:
        total = 0.0
        weight_sum = 0.0
        for c, w in profile.weights.items():
            total += metrics.get(c, 0.5) * w
            weight_sum += w
        return total / weight_sum if weight_sum > 0 else 0.5
