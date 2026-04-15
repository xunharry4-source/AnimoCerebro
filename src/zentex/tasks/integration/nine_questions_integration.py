"""
Task Orchestration - Nine Questions Integration

Integrates task execution events from phases A-F with the 9-question
reflection framework to enable experience-driven decision making.
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any, List
from uuid import uuid4

from zentex.reflection.models import ReflectionType, ReflectionTrigger


# ============================================================================
# EVENT DEFINITIONS
# ============================================================================

class TaskOrchestrationEventType(str, Enum):
    """Events from task orchestration pipeline that trigger reflection."""
    
    # Phase A: Decomposition events
    DECOMPOSITION_COMPLETE = "decomposition_complete"
    
    # Phase B: Dispatch events
    DISPATCH_DECISION_MADE = "dispatch_decision_made"
    DISPATCH_INTERNAL_SELECTED = "dispatch_internal_selected"
    DISPATCH_EXTERNAL_SELECTED = "dispatch_external_selected"
    
    # Phase C: Verification events
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    FAILURE_CLASSIFIED = "failure_classified"
    
    # Phase D: Supervision events
    SUPERVISION_ACTION_TAKEN = "supervision_action_taken"
    SUPERVISION_SUCCESS = "supervision_success"
    SUPERVISION_FAILURE = "supervision_failure"
    
    # Phase E: Experience events
    EXPERIENCE_EXTRACTED = "experience_extracted"
    LESSON_LEARNED = "lesson_learned"
    
    # System events
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass
class TaskOrchestrationEvent:
    """Event from task orchestration system."""
    
    event_id: str
    event_type: TaskOrchestrationEventType
    task_id: str
    timestamp: datetime
    
    # Phase-specific data
    phase: str  # A, B, C, D, E, F
    context: Dict[str, Any]
    
    # Reflection mapping
    reflection_type: Optional[ReflectionType] = None
    reflection_subject: Optional[str] = None


# ============================================================================
# EVENT TO 9-QUESTION MAPPING
# ============================================================================

class NineQuestionEventMapper:
    """Maps task orchestration events to 9-question reflection triggers."""
    
    def __init__(self):
        """Initialize event mapper."""
        self.event_to_questions = {
            # Phase B: Dispatch events → Q4 (What can I do)
            TaskOrchestrationEventType.DISPATCH_DECISION_MADE: {
                "questions": [4],  # Q4: What can I do (executor capabilities)
                "subject": "Executor dispatch decision",
                "reflection_type": ReflectionType.DECISION_REFLECTION,
            },
            TaskOrchestrationEventType.DISPATCH_INTERNAL_SELECTED: {
                "questions": [4],
                "subject": "Internal plugin selected for execution",
                "reflection_type": ReflectionType.DECISION_REFLECTION,
            },
            TaskOrchestrationEventType.DISPATCH_EXTERNAL_SELECTED: {
                "questions": [4, 5],  # Q4 (capability) + Q5 (allowed)
                "subject": "External executor selected",
                "reflection_type": ReflectionType.DECISION_REFLECTION,
            },
            
            # Phase C: Verification events → Q2/Q6 (What went wrong, consequences)
            TaskOrchestrationEventType.VERIFICATION_FAILED: {
                "questions": [2, 6],  # Q2 (who/what failed) + Q6 (consequences)
                "subject": "Task execution verification failed",
                "reflection_type": ReflectionType.ERROR_REFLECTION,
            },
            TaskOrchestrationEventType.FAILURE_CLASSIFIED: {
                "questions": [2, 6],
                "subject": "Failure classified and analyzed",
                "reflection_type": ReflectionType.ERROR_REFLECTION,
            },
            
            # Phase D: Supervision events → Q8/Q9 (What to do now, how to act)
            TaskOrchestrationEventType.SUPERVISION_ACTION_TAKEN: {
                "questions": [8, 9],  # Q8 (what to do) + Q9 (how to act)
                "subject": "Supervision action executed",
                "reflection_type": ReflectionType.ACTION_REFLECTION,
            },
            TaskOrchestrationEventType.SUPERVISION_SUCCESS: {
                "questions": [9],  # Q9 (how to act - successful pattern)
                "subject": "Supervision action succeeded",
                "reflection_type": ReflectionType.SUCCESS_REFLECTION,
            },
            TaskOrchestrationEventType.SUPERVISION_FAILURE: {
                "questions": [8],  # Q8 (what to do - try again)
                "subject": "Supervision action failed",
                "reflection_type": ReflectionType.ERROR_REFLECTION,
            },
            
            # Phase E: Experience events → Q4/Q7 (What can I do, what else)
            TaskOrchestrationEventType.EXPERIENCE_EXTRACTED: {
                "questions": [4, 7],  # Q4 (capability) + Q7 (what else)
                "subject": "Experience extracted from execution",
                "reflection_type": ReflectionType.LEARNING_REFLECTION,
            },
            TaskOrchestrationEventType.LESSON_LEARNED: {
                "questions": [7],  # Q7 (what else can I do)
                "subject": "Lesson learned from task execution",
                "reflection_type": ReflectionType.LEARNING_REFLECTION,
            },
            
            # System events → Q1 (where am I)
            TaskOrchestrationEventType.TASK_COMPLETED: {
                "questions": [1, 3],  # Q1 (context) + Q3 (what I have)
                "subject": "Task execution completed",
                "reflection_type": ReflectionType.OUTCOME_REFLECTION,
            },
            TaskOrchestrationEventType.TASK_FAILED: {
                "questions": [1, 2, 6],  # Q1 (context) + Q2 (what) + Q6 (consequence)
                "subject": "Task execution failed",
                "reflection_type": ReflectionType.ERROR_REFLECTION,
            },
        }
    
    def map_event_to_questions(
        self, event: TaskOrchestrationEvent
    ) -> Optional[Dict[str, Any]]:
        """
        Map task orchestration event to 9-question reflections.
        
        Returns mapping dict with questions and reflection metadata.
        """
        mapping = self.event_to_questions.get(event.event_type)
        if not mapping:
            return None
        
        return {
            "event_id": event.event_id,
            "task_id": event.task_id,
            "questions": mapping["questions"],
            "subject": mapping["subject"],
            "reflection_type": mapping["reflection_type"],
            "trigger": ReflectionTrigger.AUTOMATIC,
            "context": event.context,
            "timestamp": event.timestamp,
        }


# ============================================================================
# ORCHESTRATION-REFLECTION BRIDGE
# ============================================================================

class TaskReflectionBridge:
    """
    Bridge between task orchestration and reflection systems.
    
    Routes task events to appropriate 9-question reflections.
    """
    
    def __init__(self, reflection_service: Optional[Any] = None):
        """
        Initialize bridge.
        
        Args:
            reflection_service: ReflectionService instance
        """
        self.reflection_service = reflection_service
        self.event_mapper = NineQuestionEventMapper()
        self.event_queue: List[TaskOrchestrationEvent] = []
    
    def record_event(
        self,
        event_type: TaskOrchestrationEventType,
        task_id: str,
        phase: str,
        context: Dict[str, Any],
        auto_reflect: bool = True,
    ) -> str:
        """
        Record a task orchestration event.
        
        Args:
            event_type: Type of event
            task_id: ID of task
            phase: Which phase (A, B, C, D, E, F)
            context: Event context data
            auto_reflect: Whether to auto-trigger reflection
        
        Returns:
            Event ID
        """
        event_id = str(uuid4())
        
        event = TaskOrchestrationEvent(
            event_id=event_id,
            event_type=event_type,
            task_id=task_id,
            timestamp=datetime.utcnow(),
            phase=phase,
            context=context,
        )
        
        self.event_queue.append(event)
        
        # Auto-trigger reflection if service available
        if auto_reflect and self.reflection_service:
            self._trigger_reflection(event)
        
        return event_id
    
    def _trigger_reflection(self, event: TaskOrchestrationEvent) -> None:
        """
        Trigger 9-question reflections for an event.
        """
        mapping = self.event_mapper.map_event_to_questions(event)
        if not mapping:
            return
        
        try:
            # Generate reflections for each mapped question
            for question_id in mapping["questions"]:
                self.reflection_service.generate_reflection(
                    subject=f"{mapping['subject']} (Task: {event.task_id})",
                    reflection_type=mapping["reflection_type"],
                    context={
                        "event_type": event.event_type.value,
                        "event_id": event.event_id,
                        "task_id": event.task_id,
                        "phase": event.phase,
                        "question_id": question_id,
                        **mapping["context"],
                    },
                    trigger=mapping["trigger"],
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to trigger reflection for event {event.event_id}: {e}")
    
    def get_event_history(self, task_id: str) -> List[TaskOrchestrationEvent]:
        """Get all events for a task."""
        return [e for e in self.event_queue if e.task_id == task_id]
    
    def export_events_as_reflection_context(
        self, task_id: str
    ) -> Dict[str, Any]:
        """Export task events as reflection context."""
        events = self.get_event_history(task_id)
        
        return {
            "task_id": task_id,
            "total_events": len(events),
            "events": [
                {
                    "event_type": e.event_type.value,
                    "phase": e.phase,
                    "timestamp": e.timestamp.isoformat(),
                    "context": e.context,
                }
                for e in events
            ],
            "phases_involved": sorted(set(e.phase for e in events)),
        }


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def create_dispatch_decision_event(
    task_id: str,
    selected_executor_id: str,
    selected_executor_name: str,
    all_candidates: List[Dict[str, Any]],
    confidence: float,
) -> TaskOrchestrationEvent:
    """Create dispatch decision event."""
    return TaskOrchestrationEvent(
        event_id=str(uuid4()),
        event_type=TaskOrchestrationEventType.DISPATCH_DECISION_MADE,
        task_id=task_id,
        timestamp=datetime.utcnow(),
        phase="B",
        context={
            "selected_executor_id": selected_executor_id,
            "selected_executor_name": selected_executor_name,
            "candidates_count": len(all_candidates),
            "confidence": confidence,
        },
    )


def create_verification_failure_event(
    task_id: str,
    failure_type: str,
    failure_severity: str,
    evidence: str,
) -> TaskOrchestrationEvent:
    """Create verification failure event."""
    return TaskOrchestrationEvent(
        event_id=str(uuid4()),
        event_type=TaskOrchestrationEventType.VERIFICATION_FAILED,
        task_id=task_id,
        timestamp=datetime.utcnow(),
        phase="C",
        context={
            "failure_type": failure_type,
            "failure_severity": failure_severity,
            "evidence": evidence,
        },
    )


def create_supervision_action_event(
    task_id: str,
    action_type: str,
    action_reason: str,
    action_executed: bool,
) -> TaskOrchestrationEvent:
    """Create supervision action event."""
    return TaskOrchestrationEvent(
        event_id=str(uuid4()),
        event_type=TaskOrchestrationEventType.SUPERVISION_ACTION_TAKEN,
        task_id=task_id,
        timestamp=datetime.utcnow(),
        phase="D",
        context={
            "action_type": action_type,
            "action_reason": action_reason,
            "action_executed": action_executed,
        },
    )


def create_experience_extracted_event(
    task_id: str,
    lessons_extracted: List[str],
    executor_competency: Dict[str, float],
) -> TaskOrchestrationEvent:
    """Create experience extracted event."""
    return TaskOrchestrationEvent(
        event_id=str(uuid4()),
        event_type=TaskOrchestrationEventType.EXPERIENCE_EXTRACTED,
        task_id=task_id,
        timestamp=datetime.utcnow(),
        phase="E",
        context={
            "lessons_extracted": lessons_extracted,
            "executor_competency": executor_competency,
        },
    )
