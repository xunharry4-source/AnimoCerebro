"""
Phase E2: Experience-Based Dispatch Ranker

Enhances dispatch routing by incorporating historical executor performance
and task-specific competency data.
"""

import logging
from typing import Dict, List, Optional, Tuple

from .models import ExecutorPerformanceStats, ExperienceContext

logger = logging.getLogger(__name__)


class ExperienceRanker:
    """
    Phase E2: Enhance dispatch ranking with experience data.
    
    Current dispatch ranking:
        is_healthy → credit_score → success_rate
    
    Enhanced ranking:
        is_healthy → experience_weighted_credit → success_rate + executor_competency
    """
    
    def __init__(
        self,
        experience_weight: float = 0.3,
        confidence_threshold: float = 0.7,
    ):
        """
        Initialize ranker.
        
        Args:
            experience_weight: How much to weight experience in final score (0.0-1.0)
            confidence_threshold: Minimum confidence to apply experience adjustment
        """
        self.experience_weight = experience_weight
        self.confidence_threshold = confidence_threshold
    
    def adjust_executor_scores(
        self,
        candidates: List[Dict],
        experience_context: ExperienceContext,
    ) -> List[Dict]:
        """
        Phase E2: Apply experience-based adjustments to executor scores.
        
        Takes a list of candidates (from dispatch router) and adjusts their
        credit_score based on historical performance for this task type.
        
        Args:
            candidates: List of executor candidate dicts with 'executor_id', 'credit_score', etc.
            experience_context: ExperienceContext with executor_competency_map
        
        Returns:
            Modified candidates list with adjusted credit_score and experience metadata
        """
        
        if not experience_context.executor_competency_map:
            logger.debug("No executor competency data; skipping experience adjustment")
            return candidates
        
        adjusted_candidates = []
        
        for candidate in candidates:
            executor_id = candidate.get("executor_id")
            original_credit = candidate.get("credit_score", 1.0)
            
            # Look up executor performance for this task type
            perf_stats = experience_context.executor_competency_map.get(executor_id)
            
            if perf_stats:
                # Calculate experience boost
                confidence_band_width = (
                    perf_stats.confidence_interval_upper - perf_stats.confidence_interval_lower
                )
                confidence = 1.0 - confidence_band_width  # Higher width = lower confidence
                
                # Only apply adjustment if confidence is sufficient
                if confidence >= self.confidence_threshold:
                    # Map success_rate (0.0-1.0) to credit_score adjustment
                    # Scale: convert success_rate to 0-10.0 credit range, centered at 5.0
                    # 0.0 success = 1.0 credit, 0.5 success = 5.0 credit, 1.0 success = 9.0 credit
                    experience_adjustment = 1.0 + (perf_stats.success_rate * 8.0)
                    
                    # Blend original credit with experience
                    blended_credit = (
                        original_credit * (1.0 - self.experience_weight)
                        + experience_adjustment * self.experience_weight
                    )
                    
                    # Ensure plausible range (0.1-10.0)
                    blended_credit = max(0.1, min(10.0, blended_credit))
                    
                    adjusted_candidate = candidate.copy()
                    adjusted_candidate["original_credit_score"] = original_credit
                    adjusted_candidate["credit_score"] = blended_credit
                    adjusted_candidate["experience_adjustment"] = experience_adjustment
                    adjusted_candidate["experience_confidence"] = confidence
                    adjusted_candidate["executor_success_rate"] = perf_stats.success_rate
                    adjusted_candidate["executor_sample_count"] = perf_stats.total_attempts
                    
                    logger.debug(
                        f"Executor {executor_id}: credit {original_credit:.2f} → {blended_credit:.2f} "
                        f"(success_rate={perf_stats.success_rate:.2f}, confidence={confidence:.2f})"
                    )
                    
                    adjusted_candidates.append(adjusted_candidate)
                else:
                    logger.debug(
                        f"Executor {executor_id}: low confidence ({confidence:.2f}); "
                        "skipping experience adjustment"
                    )
                    adjusted_candidates.append(candidate)
            else:
                # No historical data for this executor
                logger.debug(f"No historical data for executor {executor_id}")
                adjusted_candidates.append(candidate)
        
        return adjusted_candidates
    
    def suggest_best_executor_by_experience(
        self,
        task_type: str,
        experience_context: ExperienceContext,
    ) -> Optional[str]:
        """
        Phase E2: Recommend best executor based solely on historical performance.
        
        Args:
            task_type: Type of task to find best executor for
            experience_context: ExperienceContext with competency data
        
        Returns:
            Editor ID with highest success rate for this task type, or None
        """
        
        if not experience_context.executor_competency_map:
            return None
        
        best_executor = None
        best_score = -1.0
        
        for executor_id, perf_stats in experience_context.executor_competency_map.items():
            # Score based on success rate and sample size
            # Higher sample size = more confident
            confidence_weight = min(1.0, perf_stats.total_attempts / 10.0)  # Saturate at 10
            adjusted_score = perf_stats.success_rate * confidence_weight
            
            if adjusted_score > best_score:
                best_score = adjusted_score
                best_executor = executor_id
        
        if best_executor:
            logger.info(
                f"Best executor by experience for {task_type}: {best_executor} "
                f"(success_rate={experience_context.executor_competency_map[best_executor].success_rate:.2f})"
            )
        
        return best_executor
    
    def build_executor_rankings(
        self,
        candidates: List[Dict],
        experience_context: ExperienceContext,
    ) -> List[Tuple[str, float, Dict]]:
        """
        Phase E2: Build comprehensive executor rankings with all metadata.
        
        Args:
            candidates: List of executor candidates
            experience_context: Experience context with competency data
        
        Returns:
            List of (executor_id, final_score, metadata) tuples, sorted by score DESC
        """
        
        rankings = []
        
        for candidate in candidates:
            executor_id = candidate.get("executor_id", "unknown")
            base_score = candidate.get("credit_score", 1.0)
            
            perf_stats = experience_context.executor_competency_map.get(executor_id)
            
            metadata = {
                "base_score": base_score,
                "health": candidate.get("is_healthy", True),
                "executor_type": candidate.get("executor_type", "unknown"),
            }
            
            if perf_stats:
                # Calculate weighted score
                confidence = 1.0 - (
                    perf_stats.confidence_interval_upper - perf_stats.confidence_interval_lower
                )
                
                if confidence >= self.confidence_threshold:
                    experience_bonus = 1.0 + (perf_stats.success_rate * 8.0)
                    final_score = (
                        base_score * (1.0 - self.experience_weight)
                        + experience_bonus * self.experience_weight
                    )
                    final_score = max(0.1, min(10.0, final_score))
                else:
                    final_score = base_score
                
                metadata.update({
                    "success_rate": perf_stats.success_rate,
                    "attempts": perf_stats.total_attempts,
                    "avg_time": perf_stats.avg_completion_time_seconds,
                    "experience_confidence": confidence,
                })
            else:
                final_score = base_score
            
            rankings.append((executor_id, final_score, metadata))
        
        # Sort by final score (descending)
        rankings.sort(key=lambda x: x[1], reverse=True)
        
        return rankings
    
    def calculate_experience_factor(
        self,
        executor_id: str,
        experience_context: ExperienceContext,
    ) -> float:
        """
        Calculate experience-based adjustment factor for executor.
        
        Args:
            executor_id: ID of executor
            experience_context: Experience context
        
        Returns:
            Adjustment factor (0.0 = bad, 1.0 = neutral, >1.0 = good)
        """
        
        perf_stats = experience_context.executor_competency_map.get(executor_id)
        
        if not perf_stats:
            return 1.0  # Neutral for unknown executors
        
        confidence_band_width = (
            perf_stats.confidence_interval_upper - perf_stats.confidence_interval_lower
        )
        confidence = 1.0 - confidence_band_width
        
        if confidence < self.confidence_threshold:
            return 1.0  # Neutral for low-confidence data
        
        # Map success rate to factor
        # 0.0 success = 0.5 factor (very bad)
        # 0.5 success = 1.0 factor (neutral)
        # 1.0 success = 1.5 factor (excellent)
        return 0.5 + (perf_stats.success_rate * 1.0)
