"""
Phase E: Experience/Memory Integration System

This package integrates historical task experiences into:
1. E1: Decomposition prompt injection (lessons learned from similar tasks)
2. E2: Dispatch ranking enhancement (executor competency based on history)
"""

from .models import (
    TaskOutcomeType,
    LessonCategory,
    ConfidenceLevel,
    ExperienceRecord,
    LessonLearned,
    ExecutorPerformanceStats,
    ExperienceContext,
)
from .extractor import ExperienceExtractor
from .ranker import ExperienceRanker

__all__ = [
    "TaskOutcomeType",
    "LessonCategory",
    "ConfidenceLevel",
    "ExperienceRecord",
    "LessonLearned",
    "ExecutorPerformanceStats",
    "ExperienceContext",
    "ExperienceExtractor",
    "ExperienceRanker",
]
