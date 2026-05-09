"""
Task Reanalysis subpackage - Handles partial completions and improvement analysis.

Purpose:
1. Detect tasks that are stuck mid-execution (partial completion)
2. Analyze completed tasks for improvement opportunities
3. Generate new tasks for continuation or enhancement

Scenarios:
- Task A gets blocked at subtask 3/5 → ReanalysisService detects → generates continuation plan
- Task B completes, but analysis shows optimization opportunity → generates improvement task
- Task C blocked due to timeout → suggests alternative executor or parallelization
"""

from zentex.tasks.reanalysis.models import (
    PartialCompletionReason,
    PartialCompletion,
    ImprovementSuggestion,
    ReanalysisPlan,
    ReanalysisResult,
)
from zentex.tasks.reanalysis.analyzer import ReanalysisService

__all__ = [
    "PartialCompletionReason",
    "PartialCompletion",
    "ImprovementSuggestion",
    "ReanalysisPlan",
    "ReanalysisResult",
    "ReanalysisService",
]
