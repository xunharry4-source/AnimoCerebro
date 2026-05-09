"""Emergency notification and proactive outreach system for G32."""

from __future__ import annotations

import json
import smtplib
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class NotificationChannelProfile(BaseModel):
    """Delivery profile for web, webhook, or email notifications."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(default_factory=lambda: f"profile-{uuid4().hex[:12]}")
    channel: str = Field(pattern="^(web|webhook|email)$")
    enabled: bool = True
    endpoint: str = ""
    token: str = ""
    min_severity: str = "low"
    max_retries: int = 1


class RiskNotificationEvent(BaseModel):
    """Risk event that needs proactive outreach."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"risk-event-{uuid4().hex[:12]}")
    event_type: str
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    description: str
    suggested_actions: list[str] = Field(default_factory=lambda: ["open_console"])
    source_ref: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationReceipt(BaseModel):
    """Persisted delivery receipt for one notification attempt."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(default_factory=lambda: f"receipt-{uuid4().hex[:12]}")
    event_id: str
    profile_id: str
    channel: str
    status: str
    attempts: int
    detail: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuickActionReceipt(BaseModel):
    """User quick action result embedded from a notification."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: f"quick-action-{uuid4().hex[:12]}")
    event_id: str
    action: str = Field(pattern="^(approve|reject|snooze|open_console)$")
    actor: str
    result: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationReceiptStore:
    """SQLite receipt and audit store for proactive notifications."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def save_receipt(self, receipt: NotificationReceipt) -> NotificationReceipt:
        with self._conn:
            self._conn.execute(
                "INSERT INTO notification_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt.receipt_id,
                    receipt.event_id,
                    receipt.profile_id,
                    receipt.channel,
                    receipt.status,
                    receipt.attempts,
                    receipt.detail,
                    receipt.created_at.isoformat(),
                ),
            )
        return receipt

    def save_action(self, action: QuickActionReceipt) -> QuickActionReceipt:
        with self._conn:
            self._conn.execute(
                "INSERT INTO notification_actions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action.action_id,
                    action.event_id,
                    action.action,
                    action.actor,
                    action.result,
                    action.created_at.isoformat(),
                ),
            )
        return action

    def list_receipts(self, event_id: str | None = None) -> list[NotificationReceipt]:
        params: tuple[Any, ...] = ((event_id,) if event_id else ())
        where = "WHERE event_id = ?" if event_id else ""
        rows = self._conn.execute(f"SELECT * FROM notification_receipts {where} ORDER BY created_at ASC", params).fetchall()
        return [
            NotificationReceipt(
                receipt_id=row["receipt_id"],
                event_id=row["event_id"],
                profile_id=row["profile_id"],
                channel=row["channel"],
                status=row["status"],
                attempts=int(row["attempts"]),
                detail=row["detail"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def list_actions(self, event_id: str | None = None) -> list[QuickActionReceipt]:
        params: tuple[Any, ...] = ((event_id,) if event_id else ())
        where = "WHERE event_id = ?" if event_id else ""
        rows = self._conn.execute(f"SELECT * FROM notification_actions {where} ORDER BY created_at ASC", params).fetchall()
        return [
            QuickActionReceipt(
                action_id=row["action_id"],
                event_id=row["event_id"],
                action=row["action"],
                actor=row["actor"],
                result=row["result"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_actions (
                    action_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )


@dataclass
class EmergencyNotificationSystem:
    """Routes risk events across web, webhook, and email with receipts."""

    store: NotificationReceiptStore
    quiet_window_seconds: int = 60

    def __post_init__(self) -> None:
        self._profiles: dict[str, NotificationChannelProfile] = {}
        self._inbox: list[dict[str, Any]] = []
        self._last_sent: dict[str, float] = {}

    def upsert_profile(self, profile: NotificationChannelProfile) -> NotificationChannelProfile:
        """Create or replace a delivery profile."""

        self._profiles[profile.profile_id] = profile
        return profile

    def emit_event(self, event: RiskNotificationEvent) -> list[NotificationReceipt]:
        """Route and send one risk event, then persist receipts."""

        event_key = f"{event.event_type}:{event.source_ref}:{event.severity}"
        now = time.time()
        if now - self._last_sent.get(event_key, 0) < self.quiet_window_seconds:
            receipt = NotificationReceipt(
                event_id=event.event_id,
                profile_id="quiet-window",
                channel="web",
                status="suppressed",
                attempts=0,
                detail="quiet_window_active",
            )
            return [self.store.save_receipt(receipt)]
        self._last_sent[event_key] = now
        receipts: list[NotificationReceipt] = []
        for profile in self._matching_profiles(event):
            receipts.append(self.store.save_receipt(self._deliver(profile, event)))
        return receipts

    def quick_action(self, event_id: str, action: str, *, actor: str) -> QuickActionReceipt:
        """Record a notification quick action."""

        result = "console_opened" if action == "open_console" else f"{action}_recorded"
        return self.store.save_action(QuickActionReceipt(event_id=event_id, action=action, actor=actor, result=result))

    def list_inbox(self) -> list[dict[str, Any]]:
        """Return web-channel inbox entries."""

        return list(self._inbox)

    def list_profiles(self) -> list[NotificationChannelProfile]:
        """Return configured profiles."""

        return list(self._profiles.values())

    def _matching_profiles(self, event: RiskNotificationEvent) -> list[NotificationChannelProfile]:
        target_channels = {"web"} if event.severity == "low" else {"web", "webhook"} if event.severity == "medium" else {"web", "webhook", "email"}
        return [
            profile
            for profile in self._profiles.values()
            if profile.enabled
            and profile.channel in target_channels
            and SEVERITY_ORDER[event.severity] >= SEVERITY_ORDER[profile.min_severity]
        ]

    def _deliver(self, profile: NotificationChannelProfile, event: RiskNotificationEvent) -> NotificationReceipt:
        attempts = 0
        last_error = ""
        for attempt in range(profile.max_retries + 1):
            attempts = attempt + 1
            try:
                if profile.channel == "web":
                    self._inbox.append({"event": event.model_dump(mode="json"), "profile_id": profile.profile_id})
                elif profile.channel == "webhook":
                    self._send_webhook(profile, event)
                elif profile.channel == "email":
                    self._send_email(profile, event)
                return NotificationReceipt(event_id=event.event_id, profile_id=profile.profile_id, channel=profile.channel, status="sent", attempts=attempts)
            except Exception as exc:
                last_error = str(exc)
        return NotificationReceipt(
            event_id=event.event_id,
            profile_id=profile.profile_id,
            channel=profile.channel,
            status="dead_letter",
            attempts=attempts,
            detail=last_error,
        )

    @staticmethod
    def _send_webhook(profile: NotificationChannelProfile, event: RiskNotificationEvent) -> None:
        body = json.dumps({"event": event.model_dump(mode="json"), "quick_actions": event.suggested_actions}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if profile.token:
            headers["Authorization"] = f"Bearer {profile.token}"
        request = urllib_request.Request(profile.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                if int(response.status) >= 400:
                    raise RuntimeError(f"webhook status {response.status}")
        except urllib_error.HTTPError as exc:
            raise RuntimeError(f"webhook status {exc.code}") from exc

    @staticmethod
    def _send_email(profile: NotificationChannelProfile, event: RiskNotificationEvent) -> None:
        endpoint = profile.endpoint
        if "://" in endpoint:
            endpoint = endpoint.split("://", 1)[1]
        host_port, _, to_addr = endpoint.partition("/")
        host, _, port_text = host_port.partition(":")
        if not host or not port_text or not to_addr:
            raise ValueError("email endpoint must be smtp://host:port/to@example.com")
        message = EmailMessage()
        message["Subject"] = f"Zentex {event.severity} alert: {event.event_type}"
        message["From"] = "zentex-alerts@example.local"
        message["To"] = to_addr
        message.set_content(f"{event.description}\nActions: {', '.join(event.suggested_actions)}")
        with smtplib.SMTP(host, int(port_text), timeout=5) as smtp:
            smtp.send_message(message)
