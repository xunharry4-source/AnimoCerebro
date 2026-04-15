"""In-Process Event Bus Implementation"""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable, Dict, List
from datetime import datetime
import logging

from ..contracts.event_bus import EventBus, EventPublishResult, Subscription

logger = logging.getLogger(__name__)


class InProcessEventBus(EventBus):
    """In-process event bus using dict-based routing
    
    Simple pub/sub implementation for single-process event distribution.
    Not suitable for distributed systems; use Redis/RabbitMQ for scale.
    """

    def __init__(self):
        # Map: event_type -> List[(subscription_id, handler)]
        self._subscribers: Dict[str, List[tuple[str, Callable]]] = {}
        # Map: subscription_id -> (event_type, handler) for unsubscribe
        self._subscriptions: Dict[str, tuple[str, Callable]] = {}

    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: str | None = None,
    ) -> EventPublishResult:
        """Publish event to all subscribers"""
        event_id = str(uuid.uuid4())
        subscribers = self._subscribers.get(event_type, [])
        errors = []

        for sub_id, handler in subscribers:
            try:
                await handler(payload)
            except Exception as e:
                logger.exception(f"Event handler {sub_id} failed for {event_type}")
                errors.append(str(e))

        return EventPublishResult(
            event_id=event_id,
            event_type=event_type,
            subscriptions_notified=len(subscribers),
            errors=errors,
        )

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to events"""
        sub_id = str(uuid.uuid4())

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append((sub_id, handler))
        self._subscriptions[sub_id] = (event_type, handler)

        return Subscription(sub_id, event_type, handler)

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events"""
        if subscription_id not in self._subscriptions:
            logger.warning(f"Subscription {subscription_id} not found")
            return

        event_type, handler = self._subscriptions.pop(subscription_id)

        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                (sub_id, h)
                for sub_id, h in self._subscribers[event_type]
                if sub_id != subscription_id
            ]
