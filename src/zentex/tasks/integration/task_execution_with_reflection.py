"""
Task Orchestration with 9-Question Reflection Integration - Practical Example

This module demonstrates how to integrate the 9-question reflection framework
into a complete task execution workflow from Phase A to Phase F.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from zentex.tasks.verification.engine import VerificationEngine
from zentex.tasks.supervision.executor import SupervisionExecutor
from zentex.tasks.experience.extractor import ExperienceExtractor
from zentex.tasks.reflection_integration import ReflectionServiceTaskIntegration
from zentex.reflection.models import ReflectionType, ReflectionTrigger


logger = logging.getLogger(__name__)


class TaskExecutionWithReflection:
    """
    Complete task execution pipeline with integrated 9-question reflection.
    
    Demonstrates how to:
    1. Record events throughout the execution pipeline
    2. Automatically trigger reflections on key events
    3. Extract learning from the full execution history
    """
    
    def __init__(
        self,
        reflection_service,
        verification_engine: VerificationEngine,
        supervision_executor: SupervisionExecutor,
        experience_extractor: ExperienceExtractor,
    ):
        """
        Initialize task execution with reflection integration.
        
        Args:
            reflection_service: ReflectionService instance
            verification_engine: VerificationEngine for Phase C
            supervision_executor: SupervisionExecutor for Phase D
            experience_extractor: ExperienceExtractor for Phase E
        """
        self.reflection_integration = ReflectionServiceTaskIntegration(
            reflection_service
        )
        self.verification_engine = verification_engine
        self.supervision_executor = supervision_executor
        self.experience_extractor = experience_extractor
        self.task_id: Optional[str] = None
    
    def execute_task(
        self,
        task_id: str,
        decomposed_context: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        selected_executor: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute complete task with reflection integration.
        
        Flow:
        1. Record dispatch decision (Phase B)
        2. Execute task
        3. Verify result (Phase C)
        4. Apply supervision if needed (Phase D)
        5. Extract experience (Phase E)
        6. Record completion (Phase F)
        """
        self.task_id = task_id
        logger.info(f"Starting task execution: {task_id}")
        
        # Phase A: Context already established in decomposed_context
        
        # Phase B: Dispatch Decision
        self._record_dispatch_phase(task_id, selected_executor, candidates)
        
        # Execute the task (implementation-specific)
        execution_result = self._run_executor(selected_executor)
        
        # Phase C: Verification
        verification_result = self._verify_result(task_id, execution_result)
        
        # Phase D: Supervision (if needed)
        if not verification_result["passed"]:
            supervision_result = self._apply_supervision(task_id, verification_result)
            execution_result = supervision_result
        else:
            self.reflection_integration.record_verification_passed(task_id)
        
        # Phase E: Experience Extraction
        self._extract_experience(task_id, execution_result)
        
        # Phase F: Task Completion
        self._record_task_completion(task_id, execution_result)
        
        logger.info(f"Task execution completed: {task_id}")
        return execution_result
    
    def _record_dispatch_phase(
        self,
        task_id: str,
        selected_executor: Dict[str, Any],
        all_candidates: List[Dict[str, Any]],
    ) -> None:
        """
        Record Phase B: Dispatch Decision
        
        Triggers Q4 reflection: "What can I do?" (executor capabilities)
        """
        logger.info(f"[Phase B] Recording dispatch decision for {task_id}")
        
        confidence = selected_executor.get("confidence", 0.0)
        
        # Record dispatch decision - automatically triggers Q4 reflection
        self.reflection_integration.record_dispatch_decision(
            task_id=task_id,
            selected_executor_id=selected_executor["executor_id"],
            selected_executor_name=selected_executor["executor_name"],
            all_candidates=all_candidates,
            confidence=confidence,
        )
        
        logger.debug(
            f"Dispatch decision recorded: "
            f"selected={selected_executor['executor_name']}, "
            f"confidence={confidence}"
        )
    
    def _run_executor(self, executor: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the selected executor (implementation-specific).
        """
        logger.info(f"Executing task with {executor['executor_name']}")
        
        # Placeholder for actual execution
        return {
            "executor_id": executor["executor_id"],
            "executor_name": executor["executor_name"],
            "output": "execution_output",
            "execution_time": 1.5,
            "success": True,
        }
    
    def _verify_result(
        self,
        task_id: str,
        execution_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Phase C: Verification
        
        Triggers Q2+Q6 reflection on failure:
        - Q2: "What happened?" (what failed)
        - Q6: "What happens?" (consequences)
        """
        logger.info(f"[Phase C] Verifying result for {task_id}")
        
        # Use verification engine to classify result
        verification = self.verification_engine.verify(execution_result)
        
        if verification["is_valid"]:
            logger.info(f"[Phase C] Verification passed for {task_id}")
            self.reflection_integration.record_verification_passed(task_id)
            return {"passed": True}
        else:
            logger.warning(f"[Phase C] Verification failed for {task_id}")
            
            # Record failure - triggers Q2+Q6 reflection
            self.reflection_integration.record_verification_failed(
                task_id=task_id,
                failure_type=verification.get("failure_type", "unknown"),
                failure_severity=verification.get("severity", "medium"),
                evidence=verification.get("evidence", ""),
                lessons=verification.get("auto_lessons", []),
            )
            
            return {
                "passed": False,
                "failure_type": verification.get("failure_type"),
                "severity": verification.get("severity"),
                "evidence": verification.get("evidence"),
            }
    
    def _apply_supervision(
        self,
        task_id: str,
        verification_failure: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Phase D: Supervision
        
        Triggers Q8+Q9 reflection:
        - Q8: "What should I do?" (decision)
        - Q9: "How should I act?" (execution)
        """
        logger.info(f"[Phase D] Applying supervision for {task_id}")
        
        failure_type = verification_failure["failure_type"]
        
        # Determine supervision action
        action = self.supervision_executor.determine_action(failure_type)
        
        # Record action - triggers Q8+Q9 reflection
        self.reflection_integration.record_supervision_action(
            task_id=task_id,
            action_type=action["action_type"],
            action_reason=f"Response to {failure_type}",
            action_executed=True,
            action_details={
                "max_retries": action.get("max_retries", 3),
                "backoff_strategy": action.get("backoff_strategy", "exponential"),
            },
        )
        
        # Execute the action
        result = self.supervision_executor.execute(action)
        
        if result["success"]:
            logger.info(f"[Phase D] Supervision succeeded for {task_id}")
            self.reflection_integration.record_supervision_success(
                task_id=task_id,
                final_status="completed_after_supervision",
                actions_taken=[action["action_type"]],
            )
        else:
            logger.error(f"[Phase D] Supervision failed for {task_id}")
            self.reflection_integration.record_supervision_failure(
                task_id=task_id,
                final_status="failed_after_supervision",
                actions_attempted=[action["action_type"]],
            )
        
        return result
    
    def _extract_experience(
        self,
        task_id: str,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Phase E: Experience Extraction
        
        Triggers Q4+Q7 reflection:
        - Q4: "What can I do?" (capability assessment)
        - Q7: "What else?" (alternative approaches)
        """
        logger.info(f"[Phase E] Extracting experience for {task_id}")
        
        # Extract lessons and competency scores
        experience = self.experience_extractor.extract(execution_result)
        
        # Record experience extraction - triggers Q4+Q7 reflection
        self.reflection_integration.record_experience_extracted(
            task_id=task_id,
            lessons=experience.get("lessons", []),
            executor_competency=experience.get("competency_scores", {}),
        )
        
        # Record individual lessons
        for lesson in experience.get("lessons", []):
            self.reflection_integration.record_lesson_learned(
                task_id=task_id,
                lesson=lesson,
                lesson_category=experience.get("lesson_category", "general"),
                confidence=experience.get("confidence", 0.8),
            )
        
        logger.debug(
            f"Experience extracted: "
            f"{len(experience.get('lessons', []))} lessons, "
            f"{len(experience.get('competency_scores', {}))} competency scores"
        )
    
    def _record_task_completion(
        self,
        task_id: str,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Phase F: Task Completion
        
        Triggers Q1+Q3 reflection on success:
        - Q1: "Where am I?" (context)
        - Q3: "What do I have?" (results and resources)
        """
        logger.info(f"[Phase F] Recording task completion for {task_id}")
        
        if execution_result.get("success", False):
            self.reflection_integration.record_task_completed(
                task_id=task_id,
                final_result="success",
                phases_executed=["A", "B", "C", "D", "E", "F"],
            )
        else:
            self.reflection_integration.record_task_failed(
                task_id=task_id,
                failure_reason=execution_result.get("error", "Unknown"),
                phases_executed=["A", "B", "C", "D", "E"],
                last_action=execution_result.get("last_action", "verify"),
            )
    
    def get_task_reflection_summary(self, task_id: str) -> Dict[str, Any]:
        """
        Get complete reflection context for a task.
        
        Returns:
            Dictionary with complete execution history and reflection context
        """
        return self.reflection_integration.get_task_reflection_context(task_id)
    
    def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get all events recorded for a task.
        
        Returns:
            List of events with timestamps and context
        """
        return self.reflection_integration.get_task_event_history(task_id)


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def example_usage():
    """
    Example of complete task execution with 9-question reflection integration.
    """
    from zentex.reflection.service import ReflectionService
    
    # Initialize services
    reflection_service = ReflectionService()
    verification_engine = VerificationEngine()
    supervision_executor = SupervisionExecutor()
    experience_extractor = ExperienceExtractor()
    
    # Create task executor with reflection
    executor = TaskExecutionWithReflection(
        reflection_service=reflection_service,
        verification_engine=verification_engine,
        supervision_executor=supervision_executor,
        experience_extractor=experience_extractor,
    )
    
    # Execute a task
    task_id = "example_task_001"
    
    decomposed_context = {
        "task_description": "Process user request",
        "required_capabilities": ["data_processing", "api_integration"],
    }
    
    candidates = [
        {
            "executor_id": "plugin_primary",
            "executor_name": "Primary Plugin",
            "competency": 0.95,
        },
        {
            "executor_id": "plugin_fallback",
            "executor_name": "Fallback Plugin",
            "competency": 0.75,
        },
    ]
    
    selected_executor = {
        "executor_id": "plugin_primary",
        "executor_name": "Primary Plugin",
        "confidence": 0.95,
    }
    
    # Execute with integrated reflection
    result = executor.execute_task(
        task_id=task_id,
        decomposed_context=decomposed_context,
        candidates=candidates,
        selected_executor=selected_executor,
    )
    
    # Get reflection summary
    reflection_context = executor.get_task_reflection_summary(task_id)
    
    print(f"Task execution completed: {result}")
    print(f"Reflection context: {reflection_context}")
    
    # Get event history
    events = executor.get_task_events(task_id)
    print(f"Events recorded: {len(events)}")
    for event in events:
        print(f"  - {event['event_type']}: {event['phase']}")


if __name__ == "__main__":
    example_usage()
