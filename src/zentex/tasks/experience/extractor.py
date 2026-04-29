from __future__ import annotations

"""
Phase E1: Experience Extractor

Extracts experiences from memory/reflection systems and formats them
for injection into decomposition prompts.
"""

import logging
import inspect
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from statistics import mean, stdev

from .models import (
    ExperienceRecord,
    LessonLearned,
    ExecutorPerformanceStats,
    ExperienceContext,
    TaskOutcomeType,
    LessonCategory,
    ConfidenceLevel,
)

logger = logging.getLogger(__name__)


class ExperienceExtractor:
    """
    Phase E1: Extract experiences from memory/reflection systems.
    
    Responsibilities:
    1. Query memory for similar past tasks
    2. Extract lessons from failures
    3. Build executor performance statistics
    4. Format context for prompt injection
    """
    
    def __init__(
        self,
        memory_service: Optional[Any] = None,
        reflection_service: Optional[Any] = None,
        task_service: Optional[Any] = None,
        similarity_threshold: float = 0.6,
        max_similar_tasks: int = 5,
    ):
        """
        Initialize extractor.
        
        Args:
            memory_service: EnhancedMemoryService instance
            reflection_service: ReflectionService instance
            task_service: TaskManagementService instance for structured task_outcomes lookup
            similarity_threshold: Minimum similarity score (0.0-1.0)
            max_similar_tasks: Maximum number of similar tasks to retrieve
        """
        self.memory_service = memory_service
        self.reflection_service = reflection_service
        self.task_service = task_service
        self.similarity_threshold = similarity_threshold
        self.max_similar_tasks = max_similar_tasks
    
    async def extract_experience_context(
        self,
        task_title: str,
        task_type: str,
        task_description: str = "",
    ) -> ExperienceContext:
        """
        Extract complete experience context for a planned task.
        
        This is the main entry point for Phase E1.
        """
        context = ExperienceContext(
            query_task_title=task_title,
            query_task_type=task_type,
        )
        
        if not self.memory_service:
            logger.warning("Memory service not configured; no experiences will be extracted")
            return context
        
        # Extract similar past tasks
        try:
            context.similar_experiences = await self.extract_similar_tasks(
                task_title, task_type, task_description
            )
            logger.info(f"Extracted {len(context.similar_experiences)} similar tasks")
        except Exception as e:
            logger.exception("Failed to extract similar tasks")
            raise RuntimeError(f"Failed to extract similar tasks: {e}") from e
        
        # Extract lessons from failures
        try:
            context.extracted_lessons = await self.extract_lessons_from_failures(
                task_type, context.similar_experiences
            )
            logger.info(f"Extracted {len(context.extracted_lessons)} lessons")
        except Exception as e:
            logger.exception("Failed to extract lessons")
            raise RuntimeError(f"Failed to extract lessons: {e}") from e
        
        # Extract executor performance stats
        try:
            context.executor_competency_map = await self.extract_executor_performance(
                task_type, context.similar_experiences
            )
            logger.info(f"Extracted performance stats for {len(context.executor_competency_map)} executors")
        except Exception as e:
            logger.exception("Failed to extract executor performance")
            raise RuntimeError(f"Failed to extract executor performance: {e}") from e
        
        # Format summary for prompt injection
        context.experience_summary = context.to_prompt_text()
        
        return context
    
    async def extract_similar_tasks(
        self,
        task_title: str,
        task_type: str,
        task_description: str = "",
    ) -> List[ExperienceRecord]:
        """Phase E1: Query memory for similar historical tasks."""
        
        if not self.memory_service:
            return []
        
        similar = []
        try:
            # Search memory for similar task records
            query = f"{task_title} {task_description}"
            search_results = await self._search_memory(
                query=query,
                limit=self.max_similar_tasks * 2,  # Retrieve extra to filter
            )
            
            for result in search_results:
                result = self._normalize_memory_result(result)
                # Simple similarity scoring (in real implementation, use embedding similarity)
                similarity = self._estimate_similarity(query, result.get("summary", "") + " " + result.get("content", ""))
                
                if similarity >= self.similarity_threshold:
                    # Map memory record to ExperienceRecord
                    record = ExperienceRecord(
                        memory_id=result.get("memory_id", "unknown"),
                        task_title=result.get("title", "Unnamed"),
                        task_description=result.get("summary", "")[:200],
                        task_type=task_type,
                        executor_id=str(result.get("target_id") or result.get("task_id") or "unknown"),
                        outcome=self._infer_outcome(result),
                        semantic_similarity=similarity,
                        completion_time_seconds=result.get("duration_seconds"),
                        timestamp=datetime.utcnow(),
                        failure_reason=result.get("failure_reason"),
                        metadata=result.get("metadata", {}),
                    )
                    similar.append(record)
            
            # Sort by similarity, keep top N
            similar.sort(key=lambda x: x.semantic_similarity, reverse=True)
            return similar[:self.max_similar_tasks]
            
        except Exception as e:
            logger.exception("Memory search failed for experience extraction")
            raise RuntimeError(f"Memory search failed for experience extraction: {e}") from e

    async def _search_memory(self, *, query: str, limit: int) -> List[Any]:
        if not self.memory_service:
            return []

        search = getattr(self.memory_service, "search", None)
        if callable(search):
            result = search(query=query, limit=limit)
            if inspect.isawaitable(result):
                result = await result
            return list(result or [])

        recall = getattr(self.memory_service, "recall", None)
        if callable(recall):
            return list(recall(query=query, limit=limit) or [])

        raise RuntimeError("Memory service exposes neither search() nor recall()")

    def _normalize_memory_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return dict(result)

        if hasattr(result, "model_dump") and callable(getattr(result, "model_dump")):
            data = result.model_dump(mode="json")
        else:
            data = {
                key: getattr(result, key)
                for key in (
                    "memory_id",
                    "title",
                    "summary",
                    "content",
                    "target_id",
                    "trace_id",
                    "tags",
                    "payload",
                    "duration_seconds",
                    "failure_reason",
                )
                if hasattr(result, key)
            }

        memory_id = data.get("memory_id")
        get_record = getattr(self.memory_service, "get_record", None) if self.memory_service else None
        if memory_id and callable(get_record):
            persisted = get_record(memory_id)
            if persisted is not None:
                persisted_data = (
                    persisted.model_dump(mode="json")
                    if hasattr(persisted, "model_dump") and callable(getattr(persisted, "model_dump"))
                    else dict(persisted)
                )
                payload = persisted_data.get("payload")
                if isinstance(payload, dict):
                    persisted_data.update({k: v for k, v in payload.items() if k not in persisted_data})
                data = {**data, **persisted_data}

        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            data.update({k: v for k, v in metadata.items() if k not in data})
        payload = data.get("payload")
        if isinstance(payload, dict):
            data.update({k: v for k, v in payload.items() if k not in data})
        return data
    
    async def extract_lessons_from_failures(
        self,
        task_type: str,
        experiences: List[ExperienceRecord],
    ) -> List[LessonLearned]:
        """Phase E1: Extract patterns and lessons from failures."""
        
        lessons = []
        
        # Lesson 1: Timeout risks
        timeout_tasks = [e for e in experiences if e.outcome == TaskOutcomeType.TIMEOUT]
        if len(timeout_tasks) >= 2:
            timeout_times = [t.completion_time_seconds for t in timeout_tasks if t.completion_time_seconds]
            if timeout_times:
                avg_time = mean(timeout_times)
                lessons.append(
                    LessonLearned(
                        category=LessonCategory.TIMING_INSIGHT,
                        title=f"Timeout risk on {task_type} tasks",
                        content=f"Similar {task_type} tasks have timed out. Consider setting timeout > {int(avg_time * 1.5)}s",
                        confidence=ConfidenceLevel.MEDIUM,
                        source_records=[e.record_id for e in timeout_tasks[:3]],
                        sample_count=len(timeout_tasks),
                        applicable_task_types=[task_type],
                        anti_pattern=False,
                        recommendation=f"Increase timeout threshold for {task_type} to {int(avg_time * 1.5)}+ seconds",
                        estimated_impact=0.4,
                    )
                )
        
        # Lesson 2: Failure anti-patterns
        failed_tasks = [e for e in experiences if e.outcome == TaskOutcomeType.FAILURE]
        if len(failed_tasks) >= 1:
            failure_reasons = [e.failure_reason for e in failed_tasks if e.failure_reason]
            if failure_reasons:
                common_reason = max(set(failure_reasons), key=failure_reasons.count) if failure_reasons else "unknown"
                lessons.append(
                    LessonLearned(
                        category=LessonCategory.ANTI_PATTERN,
                        title=f"Common failure mode: {common_reason}",
                        content=f"Similar tasks frequently fail due to {common_reason}. Review failure handling.",
                        confidence=ConfidenceLevel.MEDIUM,
                        source_records=[e.record_id for e in failed_tasks[:3]],
                        sample_count=len(failed_tasks),
                        applicable_task_types=[task_type],
                        anti_pattern=True,
                        recommendation=f"Add explicit handling for {common_reason} failure mode",
                        estimated_impact=0.5,
                    )
                )
        
        # Lesson 3: Success best practice (if high success rate)
        successful_tasks = [e for e in experiences if e.outcome == TaskOutcomeType.SUCCESS]
        if len(successful_tasks) >= 2 and successful_tasks:
            success_times = [t.completion_time_seconds for t in successful_tasks if t.completion_time_seconds]
            timing_clause = ""
            if success_times:
                avg_time = mean(success_times)
                timing_clause = f" within {int(avg_time)}s"
            lessons.append(
                LessonLearned(
                    category=LessonCategory.BEST_PRACTICE,
                    title=f"Proven success pattern",
                    content=f"Similar {task_type} tasks typically succeed{timing_clause} when well-structured.",
                    confidence=ConfidenceLevel.MEDIUM,
                    source_records=[e.record_id for e in successful_tasks[:3]],
                    sample_count=len(successful_tasks),
                    applicable_task_types=[task_type],
                    anti_pattern=False,
                    recommendation="Follow the successful task decomposition patterns observed",
                    estimated_impact=0.3,
                )
            )
        
        return lessons
    
    async def extract_executor_performance(
        self,
        task_type: str,
        experiences: List[ExperienceRecord],
    ) -> Dict[str, ExecutorPerformanceStats]:
        """Phase E1: Build executor competency statistics."""
        
        executor_stats: Dict[str, int] = {}
        executor_details: Dict[str, Dict[str, Any]] = {}
        
        # Aggregate outcomes by executor
        for exp in experiences:
            executor_id = exp.executor_id
            if executor_id not in executor_stats:
                executor_stats[executor_id] = {"success": 0, "failed": 0, "timeout": 0, "partial": 0, "total": 0, "times": []}
                executor_details[executor_id] = {}
            
            executor_stats[executor_id]["total"] += 1
            if exp.outcome == TaskOutcomeType.SUCCESS:
                executor_stats[executor_id]["success"] += 1
            elif exp.outcome == TaskOutcomeType.FAILURE:
                executor_stats[executor_id]["failed"] += 1
            elif exp.outcome == TaskOutcomeType.TIMEOUT:
                executor_stats[executor_id]["timeout"] += 1
            elif exp.outcome == TaskOutcomeType.PARTIAL_SUCCESS:
                executor_stats[executor_id]["partial"] += 1
            
            if exp.completion_time_seconds:
                executor_stats[executor_id]["times"].append(exp.completion_time_seconds)
        
        # Convert to ExecutorPerformanceStats objects
        result = {}
        for executor_id, stats in executor_stats.items():
            total = stats["total"]
            success_rate = stats["success"] / total if total > 0 else 0.0
            
            # Calculate confidence interval (simple binomial)
            z = 1.96  # 95% confidence
            p = success_rate
            n = total
            margin = z * ((p * (1 - p) / n) ** 0.5) if n > 0 else 0.1
            
            times = stats["times"]
            avg_time = mean(times) if times else None
            p95_time = sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else avg_time
            
            result[executor_id] = ExecutorPerformanceStats(
                executor_id=executor_id,
                task_type=task_type,
                total_attempts=stats["total"],
                successful_attempts=stats["success"],
                failed_attempts=stats["failed"],
                timeout_attempts=stats["timeout"],
                partial_success_attempts=stats["partial"],
                success_rate=success_rate,
                avg_completion_time_seconds=avg_time,
                p95_completion_time_seconds=p95_time,
                competency_score=success_rate * 10.0,  # Scale to 0-10
                confidence_interval_lower=max(0.0, success_rate - margin),
                confidence_interval_upper=min(1.0, success_rate + margin),
                last_updated=datetime.utcnow(),
            )
        
        return result
    
    def _estimate_similarity(self, text1: str, text2: str) -> float:
        """
        Estimate textual similarity (simple token overlap).
        
        In production, use embedding-based similarity or ML model.
        """
        # Filter out very common words
        stop_words = {"the", "a", "is", "are", "and", "or", "to", "for", "of", "in", "on"}
        
        tokens1 = set(t for t in text1.lower().split() if t and t not in stop_words)
        tokens2 = set(t for t in text2.lower().split() if t and t not in stop_words)
        
        if not tokens1 or not tokens2:
            # Fall back to substring matching if one is empty
            if text1.lower() in text2.lower() or text2.lower() in text1.lower():
                return 0.7
            return 0.0
        
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        
        # Jaccard similarity, minimum 0.6 if any overlap
        similarity = intersection / union if union > 0 else 0.0
        
        # Boost if there's keyword match
        if intersection > 0:
            similarity = max(similarity, 0.65)
        
        return similarity
    
    def _infer_outcome(self, memory_record: Dict[str, Any]) -> TaskOutcomeType:
        """Infer outcome from structured task outcome evidence, not keywords."""
        task_outcome = self._resolve_task_outcome(memory_record)
        if task_outcome:
            return self._outcome_from_structured_payload(task_outcome)

        direct_outcome = self._outcome_from_structured_payload(memory_record)
        if direct_outcome is not TaskOutcomeType.UNKNOWN:
            return direct_outcome

        return TaskOutcomeType.UNKNOWN

    def _resolve_task_outcome(self, memory_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        embedded = memory_record.get("task_outcome")
        if isinstance(embedded, dict):
            return embedded

        task_id = (
            memory_record.get("task_id")
            or memory_record.get("target_id")
            or memory_record.get("related_task_id")
        )
        if not task_id:
            return None
        if not self.task_service:
            return None
        get_task_outcome = getattr(self.task_service, "get_task_outcome", None)
        if not callable(get_task_outcome):
            raise RuntimeError("Task service does not expose get_task_outcome()")
        return get_task_outcome(str(task_id))

    def _outcome_from_structured_payload(self, payload: Dict[str, Any]) -> TaskOutcomeType:
        outcome_type = str(payload.get("outcome_type") or payload.get("outcome") or "").strip().lower()
        if outcome_type in {item.value for item in TaskOutcomeType}:
            return TaskOutcomeType(outcome_type)

        verification = payload.get("verification_result")
        verification = verification if isinstance(verification, dict) else payload
        status = str(verification.get("overall_status") or verification.get("status") or "").strip().lower()
        failure = verification.get("failure_classification")
        failure = failure if isinstance(failure, dict) else {}
        failure_type = str(failure.get("failure_type") or "").strip().lower()
        recommendation = str(verification.get("recommendation") or "").strip().lower()

        if status == "timeout" or "timeout" in failure_type:
            return TaskOutcomeType.TIMEOUT
        if verification.get("overall_passed") is True or payload.get("overall_passed") is True:
            return TaskOutcomeType.SUCCESS
        if verification.get("overall_passed") is False or payload.get("overall_passed") is False:
            if status == "partial" or recommendation == "partial":
                return TaskOutcomeType.PARTIAL_SUCCESS
            return TaskOutcomeType.FAILURE
        return TaskOutcomeType.UNKNOWN
