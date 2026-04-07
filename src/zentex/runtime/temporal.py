from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


AgendaStatus = Literal["open", "watching", "blocked", "review_now", "overdue", "expired"]


class CognitiveReminderRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_interval_seconds: float = Field(default=900.0, gt=0.0)
    cooldown_seconds: float = Field(default=300.0, ge=0.0)
    grace_period_seconds: float = Field(default=60.0, ge=0.0)
    expire_after_seconds: float = Field(default=3600.0, gt=0.0)
    staleness_scale_seconds: float = Field(default=900.0, gt=0.0)


class CognitiveAgendaItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: AgendaStatus
    priority: int = Field(default=0, ge=0)
    next_review_condition: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    last_reviewed_at: Optional[datetime] = None
    last_resurfaced_at: Optional[datetime] = None
    review_count: int = Field(default=0, ge=0)
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)
    uncertainty_score: float = Field(default=0.5, ge=0.0, le=1.0)
    delay_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    watching: bool = False
    reminder_rule: CognitiveReminderRule = Field(default_factory=CognitiveReminderRule)


class TemporalAgendaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: str
    items: List[CognitiveAgendaItem] = Field(default_factory=list)
    open_item_ids: List[str] = Field(default_factory=list)
    watching_item_ids: List[str] = Field(default_factory=list)
    blocked_item_ids: List[str] = Field(default_factory=list)
    overdue_item_ids: List[str] = Field(default_factory=list)
    expired_item_ids: List[str] = Field(default_factory=list)
    review_now_item_ids: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TemporalAgendaState":
        return cls.model_validate(payload)


class CognitiveTemporalEngine:
    """
    Deterministic internal agenda engine.

    Hard redline:
    - only reorder attention and review priority
    - never call execution adapters
    - never emit outbound notifications
    """

    def __init__(self, initial_items: List[Dict[str, Any] | CognitiveAgendaItem] | None = None) -> None:
        self._items: List[CognitiveAgendaItem] = []
        self._last_state: Optional[TemporalAgendaState] = None
        if initial_items:
            self.load_items(initial_items)

    def load_items(self, items: List[Dict[str, Any] | CognitiveAgendaItem]) -> None:
        self._items = [self._coerce_item(item) for item in items]

    def snapshot(self) -> TemporalAgendaState:
        if self._last_state is None:
            now = datetime.now(timezone.utc)
            self._last_state = TemporalAgendaState(
                state_id=str(uuid4()),
                items=[],
                created_at=now,
                updated_at=now,
            )
        return self._last_state

    def tick_agenda(
        self,
        current_time: datetime,
        current_agenda_items: List[Any],
    ) -> TemporalAgendaState:
        now = self._normalize_datetime(current_time)
        self.load_items(current_agenda_items)
        computed_items: List[CognitiveAgendaItem] = []

        for item in self._items:
            computed_items.append(self._evaluate_item(item, now))

        state = TemporalAgendaState(
            state_id=str(uuid4()),
            items=computed_items,
            open_item_ids=sorted(
                item.item_id
                for item in computed_items
                if item.status in {"open", "watching", "review_now", "overdue"}
            ),
            watching_item_ids=sorted(item.item_id for item in computed_items if item.status == "watching"),
            blocked_item_ids=sorted(item.item_id for item in computed_items if item.status == "blocked"),
            overdue_item_ids=sorted(item.item_id for item in computed_items if item.status == "overdue"),
            expired_item_ids=sorted(item.item_id for item in computed_items if item.status == "expired"),
            review_now_item_ids=sorted(item.item_id for item in computed_items if item.status == "review_now"),
            created_at=now,
            updated_at=now,
        )
        self._items = computed_items
        self._last_state = state
        return state

    def evaluate(self, now: Optional[datetime] = None) -> TemporalAgendaState:
        return self.tick_agenda(now or datetime.now(timezone.utc), self._items)

    def get_review_now_items(self) -> List[CognitiveAgendaItem]:
        return [item for item in self.snapshot().items if item.status == "review_now"]

    def _evaluate_item(self, item: CognitiveAgendaItem, now: datetime) -> CognitiveAgendaItem:
        reminder_rule = item.reminder_rule
        created_at = self._normalize_datetime(item.created_at)
        updated_at = self._normalize_datetime(item.updated_at)
        last_reviewed_at = self._normalize_datetime(item.last_reviewed_at) if item.last_reviewed_at else None
        last_resurfaced_at = (
            self._normalize_datetime(item.last_resurfaced_at) if item.last_resurfaced_at else None
        )

        reference_time = last_reviewed_at or updated_at
        next_review_due_at = reference_time + timedelta(seconds=reminder_rule.review_interval_seconds)
        overdue_at = next_review_due_at + timedelta(seconds=reminder_rule.grace_period_seconds)
        expire_at = created_at + timedelta(seconds=reminder_rule.expire_after_seconds)

        idle_seconds = max(0.0, (now - reference_time).total_seconds())
        staleness_score = min(1.0, idle_seconds / reminder_rule.staleness_scale_seconds)
        delay_risk_score = round(
            (staleness_score * 0.45) + (item.impact_score * 0.35) + (item.uncertainty_score * 0.20),
            4,
        )

        in_cooldown = False
        if last_resurfaced_at is not None:
            in_cooldown = (now - last_resurfaced_at).total_seconds() < reminder_rule.cooldown_seconds

        if now > expire_at:
            return item.model_copy(
                update={
                    "status": "expired",
                    "delay_risk_score": delay_risk_score,
                    "updated_at": now,
                }
            )

        next_status: AgendaStatus = "watching" if item.watching or item.status == "watching" else item.status
        priority = item.priority
        next_last_resurfaced_at = last_resurfaced_at

        if item.status == "blocked":
            next_status = "blocked"
        elif not in_cooldown and (delay_risk_score >= 0.7 or now >= next_review_due_at):
            next_status = "overdue" if now > overdue_at else "review_now"
            priority = max(priority, 100 if next_status == "review_now" else 90)
            next_last_resurfaced_at = now
        elif in_cooldown:
            next_status = "watching" if item.watching or item.status == "watching" else "open"

        return item.model_copy(
            update={
                "status": next_status,
                "priority": priority,
                "updated_at": now,
                "delay_risk_score": delay_risk_score,
                "last_resurfaced_at": next_last_resurfaced_at,
            }
        )

    def _coerce_item(self, item: Dict[str, Any] | CognitiveAgendaItem) -> CognitiveAgendaItem:
        if isinstance(item, CognitiveAgendaItem):
            return item

        reminder_rule_payload = item.get("reminder_rule") or item.get("review_window") or {}
        if "cooldown_seconds" not in reminder_rule_payload and "reminder_cooldown" in item:
            reminder_rule_payload = {
                **reminder_rule_payload,
                **self._coerce_dict(item.get("reminder_cooldown")),
            }
        review_interval = reminder_rule_payload.get(
            "review_interval_seconds",
            item.get("review_interval_seconds", self._default_interval(item.get("window_kind"))),
        )
        reminder_rule = CognitiveReminderRule.model_validate(
            {
                "review_interval_seconds": review_interval,
                "cooldown_seconds": reminder_rule_payload.get("cooldown_seconds", item.get("cooldown_seconds", 300.0)),
                "grace_period_seconds": reminder_rule_payload.get(
                    "grace_period_seconds", item.get("grace_period_seconds", max(60.0, float(review_interval) * 0.25))
                ),
                "expire_after_seconds": reminder_rule_payload.get(
                    "expire_after_seconds", item.get("expire_after_seconds", max(float(review_interval) * 4, 1200.0))
                ),
                "staleness_scale_seconds": reminder_rule_payload.get(
                    "staleness_scale_seconds", review_interval
                ),
            }
        )
        return CognitiveAgendaItem.model_validate(
            {
                "item_id": item.get("item_id") or item.get("id"),
                "title": item.get("title") or item.get("item_id") or item.get("id"),
                "status": item.get("status", "open"),
                "priority": item.get("priority", 0),
                "next_review_condition": item.get("next_review_condition", "manual_review_required"),
                "created_at": self._normalize_datetime(item.get("created_at")),
                "updated_at": self._normalize_datetime(item.get("updated_at") or item.get("created_at")),
                "last_reviewed_at": self._normalize_datetime(item.get("last_reviewed_at")),
                "last_resurfaced_at": self._normalize_datetime(
                    self._coerce_dict(item.get("reminder_cooldown")).get("last_resurfaced_at")
                    or item.get("last_resurfaced_at")
                ),
                "review_count": item.get("review_count", 0),
                "impact_score": item.get("impact_score", 0.5),
                "uncertainty_score": item.get("uncertainty_score", 0.5),
                "delay_risk_score": item.get("delay_risk_score", 0.0),
                "watching": item.get("watching", False) or str(item.get("status")) == "watching",
                "reminder_rule": reminder_rule,
            }
        )

    def _coerce_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _default_interval(self, window_kind: Any) -> float:
        defaults = {
            "immediate": 60.0,
            "short_term": 900.0,
            "mid_term": 3600.0,
            "long_term": 21600.0,
        }
        return defaults.get(str(window_kind or "short_term"), 900.0)

    def _normalize_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        if value is None:
            return datetime.now(timezone.utc)
        raise TypeError(f"Unsupported datetime value: {value!r}")
