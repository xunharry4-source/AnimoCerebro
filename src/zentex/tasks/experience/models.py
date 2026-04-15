"""
Phase E: Experience/Memory Data Models

Defines data structures for extracting, storing, and applying
historical task experiences to decomposition and dispatch.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskOutcomeType(str, Enum):
    """Outcome classification for historical tasks."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL_SUCCESS = "partial_success"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class LessonCategory(str, Enum):
    """Training category for lessons from experiences."""
    BEST_PRACTICE = "best_practice"
    ANTI_PATTERN = "anti_pattern"
    TIMING_INSIGHT = "timing_insight"
    DEPENDENCY_RISK = "dependency_risk"
    CAPABILITY_LIMIT = "capability_limit"
    EXECUTOR_COMPETENCY = "executor_competency"


class ConfidenceLevel(str, Enum):
    """Confidence in extracted experience/lesson."""
    HIGH = "high"  # >5 samples, consistent pattern
    MEDIUM = "medium"  # 2-5 samples, reasonably clear
    LOW = "low"  # 1 sample or unclear pattern


class ExperienceRecord(BaseModel):
    """Represents a historical task outcome from memory."""
    
    record_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique ID for this experience record")
    memory_id: str = Field(description="Source memory record ID")
    task_title: str = Field(description="Title of the historical task")
    task_description: str = Field(description="Description/content of the historical task")
    task_type: str = Field(description="Type of task (cognitive_step, agent_delegation, etc.)")
    executor_id: str = Field(description="Who executed this task")
    outcome: TaskOutcomeType = Field(description="Final outcome")
    semantic_similarity: float = Field(ge=0.0, le=1.0, description="Cosine similarity to current task (0.0-1.0)")
    completion_time_seconds: Optional[int] = Field(default=None, description="How long it took to complete")
    timestamp: datetime = Field(description="When this was recorded")
    failure_reason: Optional[str] = Field(default=None, description="If failed, why?")
    success_criteria_met: int = Field(default=0, description="How many success criteria were met")
    total_success_criteria: int = Field(default=1, description="Total success criteria")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class LessonLearned(BaseModel):
    """Extracted insight/pattern from one or more experiences."""
    
    lesson_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique lesson ID")
    category: LessonCategory = Field(description="Type of lesson")
    title: str = Field(description="Short lesson title")
    content: str = Field(description="Detailed lesson content (max 500 chars)")
    confidence: ConfidenceLevel = Field(description="How confident is this lesson?")
    source_records: List[str] = Field(description="Which experience records support this lesson")
    sample_count: int = Field(description="Number of supporting examples")
    applicable_task_types: List[str] = Field(default_factory=list, description="Task types this applies to")
    anti_pattern: bool = Field(default=False, description="Is this a pattern to AVOID?")
    recommendation: str = Field(description="Actionable recommendation")
    estimated_impact: float = Field(ge=0.0, le=1.0, description="Expected improvement (0.0-1.0)")
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExecutorPerformanceStats(BaseModel):
    """Performance statistics for an executor on a task type."""
    
    executor_id: str = Field(description="ID of the executor")
    task_type: str = Field(description="Task type these stats apply to")
    total_attempts: int = Field(ge=0, description="Total number of attempts on this type")
    successful_attempts: int = Field(ge=0, description="Number of successful attempts")
    failed_attempts: int = Field(ge=0, description="Number of failed attempts")
    timeout_attempts: int = Field(ge=0, description="Number of timeout attempts")
    partial_success_attempts: int = Field(ge=0, description="Number of partial successes")
    success_rate: float = Field(ge=0.0, le=1.0, description="Overall success rate (0.0-1.0)")
    avg_completion_time_seconds: Optional[float] = Field(default=None, description="Average time to completion")
    p95_completion_time_seconds: Optional[float] = Field(default=None, description="95th percentile completion time")
    competency_score: float = Field(ge=0.0, le=10.0, description="Competency rating (0.0-10.0)")
    confidence_interval_lower: float = Field(ge=0.0, le=1.0, description="Confidence band lower bound")
    confidence_interval_upper: float = Field(ge=0.0, le=1.0, description="Confidence band upper bound")
    last_updated: datetime = Field(description="When was this last computed?")


class ExperienceContext(BaseModel):
    """Context bundle for prompt injection or ranking enhancement."""
    
    context_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique context ID")
    query_task_title: str = Field(description="The task we're planning for")
    query_task_type: str = Field(description="Type of task we're planning")
    
    # Phase E1: For decomposition prompt injection
    similar_experiences: List[ExperienceRecord] = Field(default_factory=list, description="Similar historical tasks")
    extracted_lessons: List[LessonLearned] = Field(default_factory=list, description="Relevant lessons")
    experience_summary: str = Field(default="", description="Formatted summary for prompt injection")
    
    # Phase E2: For dispatch ranking enhancement
    executor_competency_map: Dict[str, ExecutorPerformanceStats] = Field(
        default_factory=dict, description="Executor competency for this task type"
    )
    recommended_executor_by_experience: Optional[str] = Field(default=None, description="Best executor by history")
    
    # Metadata
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_memory_records_searched: int = Field(default=0, description="How many memory records were reviewed?")
    
    def has_experience_data(self) -> bool:
        """Check if context has meaningful experience data."""
        return bool(self.similar_experiences or self.extracted_lessons or self.executor_competency_map)
    
    def to_prompt_text(self) -> str:
        """
        Format experience context for injection into decomposition prompt.
        
        Returns compact, structured text suitable for LLM prompts.
        """
        if not self.has_experience_data():
            return ""
        
        lines = [
            "\n=== EXPERIENCE CONTEXT ===",
            f"Task Type: {self.query_task_type}",
            f"Similar Past Tasks: {len(self.similar_experiences)}",
            ""
        ]
        
        if self.similar_experiences:
            lines.extend([
                "Success Rate from History:",
                "  " + ", ".join(
                    f"{r.task_title}: {r.outcome.value}"
                    for r in self.similar_experiences[:3]
                ),
                ""
            ])
        
        if self.extracted_lessons:
            lines.extend([
                "Key Lessons:",
                "  " + "; ".join(
                    f"{l.title} (confidence: {l.confidence.value})"
                    for l in self.extracted_lessons[:3]
                ),
                ""
            ])
        
        lines.append("=== END EXPERIENCE CONTEXT ===\n")
        return "\n".join(lines)
