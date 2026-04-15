"""Event Bus Contract (In-Process Pub/Sub)

Defines the event-driven interface for state changes, replacing
direct manipulation of runtime.nine_question_router.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field


class EventPublishResult(BaseModel):
    """Result of event publication"""

    event_id: str
    event_type: str
    subscriptions_notified: int
    errors: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt-abc123",
                "event_type": "nine_question.state_changed",
                "subscriptions_notified": 3,
                "errors": [],
            }
        }


class Subscription:
    """Subscription handle for event unsubscribe"""

    def __init__(self, subscription_id: str, event_type: str, handler: Callable):
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.handler = handler


class EventBus(ABC):
    """In-process event bus for state changes
    
    Provides pub/sub messaging for state changes within a single process.
    Replaces: runtime.nine_question_router.publish()
    
    Design: Simple dict-based routing with async handler support.
    Scope: Single process only (no RPC/distributed messaging).
    """

    # Event type constants
    NINE_QUESTION_STATE_CHANGED = "nine_question.state_changed"
    NINE_QUESTION_EVENT_PUBLISHED = "nine_question.event_published"
    SESSION_CREATED = "session.created"
    SESSION_CLOSED = "session.closed"
    TRANSCRIPT_ENTRY_ADDED = "transcript.entry_added"

    @abstractmethod
    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: str | None = None,
    ) -> EventPublishResult:
        """Publish an event to all subscribers
        
        Args:
            event_type: Event type identifier (e.g., "nine_question.state_changed")
            payload: Event data (arbitrary dict)
            session_id: Optional session context
            
        Returns:
            EventPublishResult with notification count and any errors
            
        Note: Handlers are called asynchronously; this method returns
              after all handlers complete or fail.
        """
        pass

    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to events of a given type
        
        Args:
            event_type: Event type to listen for
            handler: Async callable that handles the event
            
        Returns:
            Subscription handle (use to unsubscribe later)
            
        Example:
            async def on_state_changed(payload):
                print(payload["new_state"])
            
            sub = bus.subscribe("nine_question.state_changed", on_state_changed)
            bus.unsubscribe(sub.subscription_id)  # Later
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from an event
        
        Args:
            subscription_id: Subscription handle from subscribe()
        """
        pass
