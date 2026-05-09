"""Web API for G32 emergency notifications."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from zentex.safety.notifications import (
    EmergencyNotificationSystem,
    NotificationChannelProfile,
    NotificationReceiptStore,
    RiskNotificationEvent,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class QuickActionRequest(BaseModel):
    """Notification quick action request."""

    model_config = ConfigDict(extra="forbid")

    action: str
    actor: str


def _system(request: Request) -> EmergencyNotificationSystem:
    system = getattr(request.app.state, "emergency_notification_system", None)
    if system is None:
        system = EmergencyNotificationSystem(store=NotificationReceiptStore())
        request.app.state.emergency_notification_system = system
    return system


@router.post("/profiles")
def upsert_profile(payload: NotificationChannelProfile, request: Request) -> dict[str, Any]:
    """Create or replace a channel profile."""

    return _system(request).upsert_profile(payload).model_dump(mode="json")


@router.get("/profiles")
def list_profiles(request: Request) -> list[dict[str, Any]]:
    """Return channel profiles."""

    return [row.model_dump(mode="json") for row in _system(request).list_profiles()]


@router.post("/events")
def emit_event(payload: RiskNotificationEvent, request: Request) -> list[dict[str, Any]]:
    """Route a risk event and return persisted receipts."""

    return [row.model_dump(mode="json") for row in _system(request).emit_event(payload)]


@router.get("/receipts")
def list_receipts(request: Request, event_id: str | None = None) -> list[dict[str, Any]]:
    """Return notification receipts."""

    return [row.model_dump(mode="json") for row in _system(request).store.list_receipts(event_id)]


@router.get("/inbox")
def list_inbox(request: Request) -> list[dict[str, Any]]:
    """Return web notification inbox."""

    return _system(request).list_inbox()


@router.post("/events/{event_id}/actions")
def quick_action(event_id: str, payload: QuickActionRequest, request: Request) -> dict[str, Any]:
    """Record a quick action from a notification."""

    return _system(request).quick_action(event_id, payload.action, actor=payload.actor).model_dump(mode="json")


@router.get("/actions")
def list_actions(request: Request, event_id: str | None = None) -> list[dict[str, Any]]:
    """Return quick action receipts."""

    return [row.model_dump(mode="json") for row in _system(request).store.list_actions(event_id)]
