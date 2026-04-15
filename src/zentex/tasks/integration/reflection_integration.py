"""
Reflection Service Integration with Task Orchestration

Extends the ReflectionService to handle task orchestration events
and route them through the 9-question reflection framework.
"""

from typing import Optional, Dict, Any, List, Type
import logging

from zentex.tasks.nine_questions_integration import (
    TaskReflectionBridge,
    TaskOrchestrationEventType,
    TaskOrchestrationEvent,
)
from zentex.reflection.models import ReflectionType, ReflectionTrigger


logger = logging.getLogger(__name__)


class ReflectionServiceTaskIntegration:
    """
    Mixin/extension for ReflectionService to handle task orchestration events.
    
    This integrates the 9-question reflection framework with task execution
    events from phases A-F.
    """
    
    def __init__(self, base_service: Any):
        """
        Initialize integration.
        
        Args:
            base_service: The ReflectionService instance to enhance
        """
        self.base_service = base_service
        self.task_bridge = TaskReflectionBridge(reflection_service=base_service)
    
    def record_task_event(
        self,
        event_type: TaskOrchestrationEventType,
        task_id: str,
        phase: str,
        context: Dict[str, Any],
        auto_reflect: bool = True,
    ) -> str:
        """
        Record a task orchestration event and trigger reflections.
        
        Args:
            event_type: Type of task event
            task_id: ID of the task
            phase: Phase of orchestration (A, B, C, D, E, F)
            context: Event-specific context data
            auto_reflect: Whether to auto-generate reflections
        
        Returns:
            Event ID
        """
        return self.task_bridge.record_event(
            event_type=event_type,
            task_id=task_id,
            phase=phase,
            context=context,
            auto_reflect=auto_reflect,
        )
    
    def record_dispatch_decision(
        self,
        task_id: str,
        selected_executor_id: str,
        selected_executor_name: str,
        all_candidates: List[Dict[str, Any]],
        confidence: float,
    ) -> str:
        """Record executor dispatch decision."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.DISPATCH_DECISION_MADE,
            task_id=task_id,
            phase="B",
            context={
                "selected_executor_id": selected_executor_id,
                "selected_executor_name": selected_executor_name,
                "candidates_count": len(all_candidates),
                "candidates": all_candidates,
                "confidence": confidence,
            },
        )
    
    def record_verification_passed(self, task_id: str) -> str:
        """Record successful verification."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.VERIFICATION_PASSED,
            task_id=task_id,
            phase="C",
            context={"status": "passed"},
        )
    
    def record_verification_failed(
        self,
        task_id: str,
        failure_type: str,
        failure_severity: str,
        evidence: str,
        lessons: Optional[List[str]] = None,
    ) -> str:
        """Record verification failure."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.VERIFICATION_FAILED,
            task_id=task_id,
            phase="C",
            context={
                "failure_type": failure_type,
                "failure_severity": failure_severity,
                "evidence": evidence,
                "lessons": lessons or [],
            },
        )
    
    def record_supervision_action(
        self,
        task_id: str,
        action_type: str,
        action_reason: str,
        action_executed: bool,
        action_details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record supervision action taken."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.SUPERVISION_ACTION_TAKEN,
            task_id=task_id,
            phase="D",
            context={
                "action_type": action_type,
                "action_reason": action_reason,
                "action_executed": action_executed,
                "action_details": action_details or {},
            },
        )
    
    def record_supervision_success(
        self,
        task_id: str,
        final_status: str,
        actions_taken: List[str],
    ) -> str:
        """Record successful supervision outcome."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.SUPERVISION_SUCCESS,
            task_id=task_id,
            phase="D",
            context={
                "final_status": final_status,
                "actions_taken": actions_taken,
            },
        )
    
    def record_supervision_failure(
        self,
        task_id: str,
        final_status: str,
        actions_attempted: List[str],
    ) -> str:
        """Record failed supervision."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.SUPERVISION_FAILURE,
            task_id=task_id,
            phase="D",
            context={
                "final_status": final_status,
                "actions_attempted": actions_attempted,
            },
        )
    
    def record_experience_extracted(
        self,
        task_id: str,
        lessons: List[str],
        executor_competency: Dict[str, float],
    ) -> str:
        """Record extracted experience/lessons."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.EXPERIENCE_EXTRACTED,
            task_id=task_id,
            phase="E",
            context={
                "lessons_extracted": lessons,
                "executor_competency": executor_competency,
            },
        )
    
    def record_lesson_learned(
        self,
        task_id: str,
        lesson: str,
        lesson_category: str,
        confidence: float,
    ) -> str:
        """Record individual lesson learned."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.LESSON_LEARNED,
            task_id=task_id,
            phase="E",
            context={
                "lesson": lesson,
                "lesson_category": lesson_category,
                "confidence": confidence,
            },
        )
    
    def record_task_completed(
        self,
        task_id: str,
        final_result: str,
        phases_executed: List[str],
    ) -> str:
        """Record task completion."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.TASK_COMPLETED,
            task_id=task_id,
            phase="F",
            context={
                "final_result": final_result,
                "phases_executed": phases_executed,
            },
        )
    
    def record_task_failed(
        self,
        task_id: str,
        failure_reason: str,
        phases_executed: List[str],
        last_action: str,
    ) -> str:
        """Record task failure."""
        return self.record_task_event(
            event_type=TaskOrchestrationEventType.TASK_FAILED,
            task_id=task_id,
            phase="F",
            context={
                "failure_reason": failure_reason,
                "phases_executed": phases_executed,
                "last_action": last_action,
            },
        )
    
    def get_task_event_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all events for a task."""
        events = self.task_bridge.get_event_history(task_id)
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "phase": e.phase,
                "timestamp": e.timestamp.isoformat(),
                "context": e.context,
            }
            for e in events
        ]
    
    def get_task_reflection_context(self, task_id: str) -> Dict[str, Any]:
        """
        Get comprehensive reflection context for a task.
        
        Includes all events, phases, and execution journey.
        """
        return {
            "task_id": task_id,
            "event_history": self.get_task_event_history(task_id),
            "orchestration_context": self.task_bridge.export_events_as_reflection_context(
                task_id
            ),
        }


class TaskIntegratedReflectionService:
    """
    Wrapper that provides integrated task orchestration + reflection service.
    
    Use this as drop-in replacement for reflection service when task events
    need to be tracked and reflected upon.
    """
    
    def __init__(self, base_reflection_service: Any):
        """
        Initialize integrated service.
        
        Args:
            base_reflection_service: BaseReflectionService instance
        """
        self._base = base_reflection_service
        self._integration = ReflectionServiceTaskIntegration(base_reflection_service)
    
    def __getattr__(self, name: str) -> Any:
        """Delegate to integration for task methods, base for others."""
        if name.startswith("record_") or name in [
            "get_task_event_history",
            "get_task_reflection_context",
        ]:
            return getattr(self._integration, name)
        return getattr(self._base, name)
    
    def generate_reflection(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trigger: ReflectionTrigger = ReflectionTrigger.AUTOMATIC,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate reflection - delegates to base service."""
        return self._base.generate_reflection(
            subject=subject,
            reflection_type=reflection_type,
            context=context,
            trigger=trigger,
            trace_id=trace_id,
            session_id=session_id,
        )
