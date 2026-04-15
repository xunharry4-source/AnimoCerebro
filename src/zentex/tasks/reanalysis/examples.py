"""
Task Reanalysis Usage Examples

This module demonstrates how to use the task reanalysis functionality
for handling partial completion and improvement opportunities.
"""

from zentex.tasks.service import TaskManagementService
from zentex.tasks.reanalysis import PartialCompletionReason, ReanalysisService


async def example_1_handle_partial_completion():
    """
    Example 1: Task gets stuck mid-execution, detect and plan continuation.
    
    Scenario:
    - User starts a 5-step ETL task
    - Step 1-2 complete successfully
    - Step 3 (transform) times out after 30s
    - Automatically detect: 40% done, blocked on timeout
    - Generate plan to continue with different approach
    """
    
    # Get the task management service
    # (In real app: injected or from context)
    service: TaskManagementService
    
    # Assume task is running and executor reports partial completion
    task_id = "etl-task-001"
    subtask_statuses = [
        {"local_id": "extract", "status": "done", "output": {"rows": 50000}},
        {"local_id": "validate", "status": "done", "output": {"valid": 49500}},
        {"local_id": "transform", "status": "failed"},  # Timed out
        {"local_id": "load", "status": "pending"},
        {"local_id": "verify", "status": "pending"},
    ]
    
    # Handle partial completion
    result = await service.handle_task_partial_completion(
        task_id=task_id,
        subtask_statuses=subtask_statuses,
        failed_subtask_index=2,
        stop_reason="executor_timeout",
        error_message="Transform step exceeded 30s timeout; 25% of data processed",
        execution_time_seconds=35.0,
    )
    
    if result:
        # result contains:
        # - partial_completion: What was accomplished, why it stopped
        # - continuation_plan: How to proceed
        # - bypass_strategies: Ways to avoid same issue
        # - recommend_auto_retry: Should we retry or need intervention?
        
        partial = result["partial_completion"]
        print(f"Task {task_id} is {partial.completion_percentage:.1f}% complete")
        print(f"Stopped at: {partial.stopped_at_local_id}")
        print(f"Reason: {partial.stop_reason}")
        
        # Get strategies for next attempt
        strategies = result["bypass_strategies"]
        print(f"Try these approaches: {strategies}")
        
        # Optionally create continuation task
        if result["recommend_auto_retry"]:
            # Generate new decomposition from stop point
            new_task_id = await service.create_task_from_reanalysis(
                reanalysis_plan=result["continuation_plan"],
                original_task_details={
                    "title": "ETL Task - Continuation",
                    "content": "Continue from transform step",
                    "parent_task_id": task_id,
                }
            )
            print(f"Created continuation task: {new_task_id}")


async def example_2_detect_improvement_opportunities():
    """
    Example 2: After task completion, identify and execute improvements.
    
    Scenario:
    - User completes a data analysis task (took 90 seconds, 12 subtasks all sequential)
    - Analysis shows: could parallelize steps 3-8 and run 2x faster
    - Confidence 78% that parallelization is safe
    - Automatically suggest creating improvement task
    """
    
    service: TaskManagementService
    
    task_id = "analysis-task-001"
    
    # Task just completed - analyze for improvements
    result = await service.detect_task_improvement_opportunities(
        task_id=task_id,
        execution_metrics={
            "execution_time_seconds": 90,
            "success_rate": 0.96,
            "quality_score": 0.88,
        },
        completion_output={
            "analysis_id": "ana-123",
            "sections": ["overview", "trends", "anomalies", "recommendations"],
        },
    )
    
    if result:
        suggestion = result["improvement_suggestion"]
        print(f"Improvement identified: {suggestion.suggestion_type}")
        print(f"Description: {suggestion.description}")
        print(f"Confidence: {suggestion.confidence_score:.0%}")
        print(f"Expected benefit: {suggestion.expected_benefit}")
        print(f"Effort needed: {suggestion.estimated_additional_effort}")
        
        # If high confidence, create improvement task
        if result["recommend_generate_task"]:
            improvement_task_id = await service.create_task_from_reanalysis(
                reanalysis_plan=result["improvement_plan"],
                original_task_details={
                    "title": f"[IMPROVEMENT] {suggestion.suggestion_type}",
                    "content": suggestion.description,
                    "parent_task_id": task_id,
                }
            )
            print(f"Created improvement task: {improvement_task_id}")
            print(f"User can review and approve it before execution")


async def example_3_manual_partial_completion_handling():
    """
    Example 3: Manual handling of partial completion (operator intervention).
    
    Scenario:
    - Task blocked due to missing executor capability
    - System cannot auto-continue (no alternative approach available)
    - Need manual intervention: select alternative executor, manual input, configuration
    """
    
    service: TaskManagementService
    
    task_id = "custom-task-002"
    
    # Detect what happened
    result = await service.handle_task_partial_completion(
        task_id=task_id,
        subtask_statuses=[
            {"local_id": "setup", "status": "done"},
            {"local_id": "process", "status": "failed"},
        ],
        failed_subtask_index=1,
        stop_reason="capability_mismatch",
        error_message="Required capability 'image_processing' not available on selected executor",
        execution_time_seconds=15.0,
    )
    
    if result:
        partial = result["partial_completion"]
        strategies = result["bypass_strategies"]
        
        # Escalate to manual intervention
        print("⚠️  Escalation Required")
        print(f"Task blocked: {partial.stop_reason}")
        print(f"Recovery options:")
        for i, strategy in enumerate(strategies, 1):
            print(f"  {i}. {strategy}")
        
        # Operator can:
        # 1. Select different executor with required capability
        # 2. Break task into simpler substeps
        # 3. Provide manual input/override


async def example_4_reanalysis_service_direct_usage():
    """
    Example 4: Using ReanalysisService directly for advanced use cases.
    """
    
    from zentex.tasks.reanalysis import ReanalysisService
    
    # Initialize service
    reanalysis_service = ReanalysisService(
        decomposer=None,  # Can inject decomposer for custom logic
        service=None,     # Can inject task service for task creation
    )
    
    # === Scenario A: Partial Completion ===
    
    partial = reanalysis_service.detect_partial_completion(
        task_id="qa-task-001",
        mission_id="qa-mission",
        subtask_statuses=[
            {"local_id": "t1", "status": "done"},
            {"local_id": "t2", "status": "done"},
            {"local_id": "t3", "status": "blocked"},
        ],
        failed_subtask_index=2,
        stop_reason=PartialCompletionReason.DEPENDENCY_BLOCKED,
        error_message="t3 blocked on t2 output format mismatch",
        execution_time_seconds=30.0,
    )
    
    print(f"Partial completion at {partial.completion_percentage}%")
    print(f"Last successful output: {partial.completed_output}")
    
    # Get bypass suggestions
    strategies = reanalysis_service._suggest_bypass_strategies(partial.stop_reason)
    print(f"Bypass strategies: {strategies}")
    
    # === Scenario B: Improvement Analysis ===
    
    suggestion = reanalysis_service.analyze_completion_for_improvement(
        task_id="report-002",
        mission_id="reporting",
        task_description="Generate quarterly business report with multiple sections",
        execution_metrics={
            "execution_time_seconds": 120,
            "success_rate": 0.92,
        },
        completion_output={"report": "complete"},
    )
    
    if suggestion:
        print(f"\n✨ Improvement Opportunity:")
        print(f"  Type: {suggestion.suggestion_type}")
        print(f"  Confidence: {suggestion.confidence_score:.0%}")
        print(f"  Description: {suggestion.description}")


async def example_5_cascading_scenarios():
    """
    Example 5: Handling cascading/dependent tasks.
    
    Scenario:
    - Task A (parent) decomposes to [A1, A2, A3]
    - A1 completes, A2 fails mid-execution (60% done)
    - A3 is blocked waiting for A2's output
    - System should:
      1. Detect A2's partial completion
      2. Create continuation plan for A2
      3. Once A2 reanalyzed, check if A3 can proceed
    """
    
    service: TaskManagementService
    
    # Detect that subtask A2 is partially complete
    result_a2 = await service.handle_task_partial_completion(
        task_id="subtask-a2",
        subtask_statuses=[
            {"local_id": "a2-step1", "status": "done"},
            {"local_id": "a2-step2", "status": "done"},
            {"local_id": "a2-step3", "status": "failed", "error": "timeout"},
        ],
        failed_subtask_index=2,
        stop_reason="executor_timeout",
        error_message="A2 transformed 60% of dataset before timeout",
        execution_time_seconds=40.0,
    )
    
    if result_a2:
        partial = result_a2["partial_completion"]
        
        # After handling A2's partial completion, check dependent task A3
        print(f"Subtask A2 is {partial.completion_percentage}% complete")
        print("Subtask A3 is blocked waiting for A2 output")
        
        # Options:
        # 1. Continue A2 with partial output (60% data)
        # 2. Use completed 60% as interim result, let A3 proceed with that
        # 3. Wait for A2 to be fully fixed, then run A3


# Usage:
# python task_reanalysis_examples.py

if __name__ == "__main__":
    import asyncio
    
    print("Task Reanalysis Examples\n" + "="*50 + "\n")
    
    print("Example scenarios are provided above as async functions.")
    print("To run them, integrate with actual TaskManagementService instance.\n")
    
    print("Key concepts:")
    print("1. Partial Completion: Detect when task stops mid-execution")
    print("2. Improvement Detection: Identify optimization opportunities after completion")
    print("3. Continuation Planning: Auto-generate plan to resume or improve")
    print("4. Bypass Strategies: Suggest ways to avoid same failure")
    print("5. New Task Generation: Create sibling/child tasks for continuation/improvement")
