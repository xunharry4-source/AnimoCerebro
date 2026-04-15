"""
Task Reanalysis Service - Handles task continuation and improvement analysis.
Detects partial completions and generates new tasks for optimization.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from zentex.tasks.reanalysis.models import (
    PartialCompletion,
    PartialCompletionReason,
    ImprovementSuggestion,
    ReanalysisPlan,
    ReanalysisResult,
)

logger = logging.getLogger(__name__)


class ReanalysisService:
    """
    Service for detecting and handling task reanalysis scenarios:
    1. Partial completion (task stuck mid-execution)
    2. Post-completion improvement analysis
    3. New task generation for continuation/improvement
    """
    
    def __init__(self, decomposer: Any = None, service: Any = None):
        """
        Initialize reanalysis service.
        
        Args:
            decomposer: Decomposer to use for new task generation (can be mock/llm/sk)
            service: Reference to TaskManagementService for creating new tasks
        """
        self.decomposer = decomposer
        self.service = service
        self._partial_completions: Dict[str, PartialCompletion] = {}
        self._improvement_suggestions: Dict[str, ImprovementSuggestion] = {}
    
    def detect_partial_completion(
        self,
        task_id: str,
        mission_id: str,
        subtask_statuses: List[Dict[str, Any]],  # [{"local_id": "step-1", "status": "done"}, ...]
        failed_subtask_index: int,
        stop_reason: PartialCompletionReason,
        error_message: Optional[str] = None,
        execution_time_seconds: float = 0.0,
    ) -> PartialCompletion:
        """
        Detect and record a task that stopped mid-execution.
        
        Args:
            task_id: Task ID that stopped
            mission_id: Parent mission ID
            subtask_statuses: List of {"local_id", "status"} for all subtasks
            failed_subtask_index: Index where execution stopped
            stop_reason: Why it stopped (timeout, unavailable executor, etc.)
            error_message: Optional error details
            execution_time_seconds: How long it ran
        
        Returns:
            PartialCompletion record for this stop event
        """
        total_count = len(subtask_statuses)
        completed_count = sum(1 for s in subtask_statuses if s.get("status") == "done")
        
        partial = PartialCompletion(
            task_id=task_id,
            mission_id=mission_id,
            completed_subtask_count=completed_count,
            total_subtask_count=total_count,
            completion_percentage=(completed_count / total_count * 100) if total_count > 0 else 0,
            stopped_at_subtask_index=failed_subtask_index,
            stopped_at_local_id=subtask_statuses[failed_subtask_index].get("local_id", f"step-{failed_subtask_index}"),
            stop_reason=stop_reason,
            last_successful_subtask_index=failed_subtask_index - 1,
            completed_output={
                "completed_subtasks": [
                    s["local_id"] for s in subtask_statuses 
                    if s.get("status") == "done"
                ],
                "last_output": subtask_statuses[failed_subtask_index - 1].get("output") if failed_subtask_index > 0 else None,
            },
            error_context=error_message,
            total_execution_time_seconds=execution_time_seconds,
        )
        
        self._partial_completions[task_id] = partial
        
        logger.info(
            f"Detected partial completion: task {task_id} stopped at {failed_subtask_index}/{total_count} "
            f"({partial.completion_percentage:.1f}%) - reason: {stop_reason}"
        )
        
        return partial
    
    def analyze_completion_for_improvement(
        self,
        task_id: str,
        mission_id: str,
        task_description: str,
        execution_metrics: Dict[str, Any],  # {"success_rate": 0.9, "time_seconds": 120, ...}
        completion_output: Dict[str, Any],
        original_requirements: Optional[List[str]] = None,
    ) -> Optional[ImprovementSuggestion]:
        """
        Analyze a completed task to identify improvement opportunities.
        
        Analysis checks:
        1. Execution efficiency - could it run faster?
        2. Scope expansion - could it accomplish more?
        3. Accuracy/quality - could results be more accurate?
        4. Alternative approaches - different decomposition?
        
        Args:
            task_id: Completed task ID
            mission_id: Parent mission ID
            task_description: Original task description
            execution_metrics: Performance data from execution
            completion_output: What task produced
            original_requirements: What was requested
        
        Returns:
            ImprovementSuggestion if improvements identified, None otherwise
        """
        improvements = []
        
        # Check 1: Efficiency improvement
        if execution_metrics.get("execution_time_seconds", 0) > 60:
            improvements.append({
                "type": "optimization",
                "angle": "parallelization",
                "description": "Some sequential subtasks could run in parallel",
                "benefit": "Faster execution",
                "effort": "minimal",
                "confidence": 0.7,
            })
        
        # Check 2: Scope expansion
        if "analysis" in task_description.lower() or "check" in task_description.lower():
            improvements.append({
                "type": "extension",
                "angle": "verification_step",
                "description": "Add verification/validation step after main task",
                "benefit": "Higher confidence in results",
                "effort": "moderate",
                "confidence": 0.6,
            })
        
        # Check 3: Alternative approach
        if execution_metrics.get("success_rate", 1.0) < 0.95:
            improvements.append({
                "type": "refinement",
                "angle": "error_handling",
                "description": "Add explicit error handling and retry logic",
                "benefit": "More robust results",
                "effort": "moderate",
                "confidence": 0.8,
            })
        
        # Check 4: Quality assurance
        if len(completion_output) > 0 and "quality_score" in execution_metrics:
            if execution_metrics.get("quality_score", 1.0) < 0.85:
                improvements.append({
                    "type": "refinement",
                    "angle": "quality_assurance",
                    "description": "Add quality checks and result validation",
                    "benefit": "Higher quality results",
                    "effort": "minimal",
                    "confidence": 0.75,
                })
        
        if not improvements:
            logger.debug(f"No improvements identified for task {task_id}")
            return None
        
        # Pick best improvement by confidence
        best_improvement = max(improvements, key=lambda x: x["confidence"])
        
        suggestion = ImprovementSuggestion(
            task_id=task_id,
            mission_id=mission_id,
            suggestion_type=best_improvement["type"],
            confidence_score=best_improvement["confidence"],
            description=best_improvement["description"],
            expected_benefit=best_improvement["benefit"],
            suggested_new_subtasks=[
                {
                    "title": f"Add {best_improvement['angle']} step",
                    "objective": best_improvement["description"],
                    "task_type": "COGNITIVE_STEP",
                    "content": f"Implement {best_improvement['angle']} to improve task quality",
                }
            ],
            estimated_additional_effort=best_improvement["effort"],
            related_execution_metrics=execution_metrics,
        )
        
        self._improvement_suggestions[task_id] = suggestion
        
        logger.info(
            f"Identified improvement opportunity for task {task_id}: "
            f"{best_improvement['type']} ({best_improvement['angle']}) - confidence: {best_improvement['confidence']}"
        )
        
        return suggestion
    
    async def create_continuation_plan(
        self,
        partial_completion: PartialCompletion,
    ) -> ReanalysisPlan:
        """
        Create a plan to continue a partially completed task.
        
        Args:
            partial_completion: PartialCompletion record from detect_partial_completion
        
        Returns:
            ReanalysisPlan for generating new subtasks from stop point
        """
        plan = ReanalysisPlan(
            original_task_id=partial_completion.task_id,
            original_mission_id=partial_completion.mission_id,
            reanalysis_type="continue_from_stop",
            decision_reason=f"Task blocked at subtask {partial_completion.stopped_at_local_id} "
                           f"({partial_completion.completion_percentage:.1f}% complete) - {partial_completion.stop_reason}",
            completed_context=partial_completion.completed_output,
            failure_analysis={
                "stop_reason": partial_completion.stop_reason,
                "error": partial_completion.error_context,
                "strategies_to_try": self._suggest_bypass_strategies(partial_completion.stop_reason),
            },
            improvement_goals=[
                "Resume execution from stop point",
                "Avoid previous failure reason",
                "Use alternative executor if needed",
            ],
            reuse_completed_results=True,
            max_new_subtasks=None,  # No limit, regenerate remaining
        )
        
        logger.debug(f"Created continuation plan for task {partial_completion.task_id}")
        return plan
    
    async def create_improvement_plan(
        self,
        improvement_suggestion: ImprovementSuggestion,
    ) -> ReanalysisPlan:
        """
        Create a plan to improve a completed task.
        
        Args:
            improvement_suggestion: ImprovementSuggestion from analyze_completion_for_improvement
        
        Returns:
            ReanalysisPlan for generating new improvement subtasks
        """
        plan = ReanalysisPlan(
            original_task_id=improvement_suggestion.task_id,
            original_mission_id=improvement_suggestion.mission_id,
            reanalysis_type="improve_completion",
            decision_reason=f"Post-completion analysis identified {improvement_suggestion.suggestion_type}: "
                           f"{improvement_suggestion.description}",
            completed_context={"original_output": improvement_suggestion.related_execution_metrics},
            improvement_goals=[
                f"Add {improvement_suggestion.suggestion_type} step",
                improvement_suggestion.expected_benefit,
            ],
            reuse_completed_results=False,  # Create sibling task
            max_new_subtasks=len(improvement_suggestion.suggested_new_subtasks) + 2,
            related_improvement_suggestion_id=improvement_suggestion.task_id,
        )
        
        logger.debug(f"Created improvement plan for task {improvement_suggestion.task_id}")
        return plan
    
    async def generate_reanalysis_result(
        self,
        plan: ReanalysisPlan,
        original_task_details: Dict[str, Any],
    ) -> ReanalysisResult:
        """
        Generate new decomposition based on reanalysis plan.
        
        This calls the decomposer to create new subtasks considering:
        - For continuation: start from stop point, reuse completed output
        - For improvement: augment original task with new steps
        
        Args:
            plan: ReanalysisPlan with reanalysis goals
            original_task_details: Original task title, content, etc.
        
        Returns:
            ReanalysisResult with new subtasks and continuation/improvement specs
        """
        if not self.decomposer:
            logger.error("No decomposer available for reanalysis")
            raise ValueError("ReanalysisService.decomposer not configured")
        
        # Build context for decomposer
        reanalysis_context_prompt = f"""
Reanalysis Context:
- Type: {plan.reanalysis_type}
- Reason: {plan.decision_reason}
- Goals: {'; '.join(plan.improvement_goals)}
- Completed So Far: {plan.completed_context}

Original Task: {original_task_details.get('title', 'Unknown')}
Original Content: {original_task_details.get('content', 'Unknown')[:500]}
        """
        
        # Call decomposer with reanalysis context
        new_subtasks = await self.decomposer.decompose_mission(
            mission_title=f"Reanalysis: {original_task_details.get('title', 'Unknown')}",
            mission_content=reanalysis_context_prompt,
            context=None,  # Can add DecompositionContext if needed
        )
        
        result = ReanalysisResult(
            original_task_id=plan.original_task_id,
            reanalysis_plan_id=plan.original_task_id,  # Simplified for now
            new_subtasks=new_subtasks,
            resume_from_index=(
                plan.original_task_id.split("-")[-1] if plan.reanalysis_type == "continue_from_stop"
                else None
            ),
            continuation_handoff_data=plan.completed_context,
            relationship_to_original="child" if plan.reanalysis_type == "continue_from_stop" else "sibling",
            decomposer_used="mock",  # Simplified; could track actual decomposer
        )
        
        logger.info(
            f"Generated reanalysis result for {plan.original_task_id}: "
            f"{len(new_subtasks)} new subtasks ({plan.reanalysis_type})"
        )
        
        return result
    
    def _suggest_bypass_strategies(self, stop_reason: PartialCompletionReason) -> List[str]:
        """Suggest strategies to avoid the same failure in continuation."""
        strategies = {
            PartialCompletionReason.EXECUTOR_TIMEOUT: [
                "Try executor with longer timeout",
                "Break into smaller steps",
                "Use parallel execution instead of sequential",
            ],
            PartialCompletionReason.EXECUTOR_UNAVAILABLE: [
                "Try different executor type (MCP/AGENT/CLI)",
                "Check executor health and retry",
                "Queue for later execution",
            ],
            PartialCompletionReason.DEPENDENCY_BLOCKED: [
                "Reorder subtasks",
                "Add error recovery step",
                "Use fallback approach",
            ],
            PartialCompletionReason.CAPABILITY_MISMATCH: [
                "Find executor with required capability",
                "Break into simpler sub-steps",
                "Manual intervention required",
            ],
            PartialCompletionReason.RESOURCE_EXHAUSTED: [
                "Reduce batch size",
                "Execute in phases",
                "Cleanup intermediate results",
            ],
            PartialCompletionReason.MANUAL_SUSPENSION: [
                "Resume from suspension with updated context",
                "Review and adjust plan if needed",
            ],
            PartialCompletionReason.CASCADING_FAILURE: [
                "Fix root cause from earlier step",
                "Add error compensation logic",
                "Implement circuit breaker",
            ],
        }
        return strategies.get(stop_reason, ["Retry with updated plan"])
    
    def get_partial_completion(self, task_id: str) -> Optional[PartialCompletion]:
        """Retrieve recorded partial completion for a task."""
        return self._partial_completions.get(task_id)
    
    def get_improvement_suggestion(self, task_id: str) -> Optional[ImprovementSuggestion]:
        """Retrieve improvement suggestion for a task."""
        return self._improvement_suggestions.get(task_id)
