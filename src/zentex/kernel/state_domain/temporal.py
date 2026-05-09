from __future__ import annotations

"""Feature 55 CognitiveTemporalEngine.

The engine keeps legacy turn timing metrics and implements deterministic
agenda-aging rules for review windows, reminder cooldowns, expiry, and
deferred-risk resurfacing.
"""

import hashlib
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

UTC = timezone.utc


@dataclass
class TemporalAgendaState:
    state_id: str
    open_item_ids: list[str]
    watching_item_ids: list[str]
    overdue_item_ids: list[str]
    expired_item_ids: list[str]
    review_now_item_ids: list[str]
    created_at: str
    updated_at: str
    snapshot_version: int
    brain_scope: str
    agenda_ages: list[dict[str, Any]]
    review_windows: list[dict[str, Any]]
    reminder_cooldowns: list[dict[str, Any]]
    deferred_risk_scores: list[dict[str, Any]]
    suppressed_item_ids: list[str]
    resurfaced_attention_candidates: list[dict[str, Any]]
    cognitive_agenda: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgendaAge:
    item_id: str
    age_seconds: float
    idle_seconds: float
    review_count: int
    last_reviewed_at: str | None
    next_review_due_at: str
    overdue: bool
    expired: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewWindow:
    item_id: str
    window_kind: str
    review_interval_seconds: float
    grace_period_seconds: float
    expire_after_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReminderCooldown:
    item_id: str
    cooldown_seconds: float
    last_resurfaced_at: str | None
    suppressed_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeferredRiskScore:
    item_id: str
    staleness_score: float
    impact_score: float
    uncertainty_score: float
    combined_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalAgendaItem:
    item_id: str
    title: str
    summary: str
    status: str
    created_at: str
    next_review_due_at: str
    expired: bool
    deferred_risk_score: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CognitiveAgenda:
    agenda_id: str
    ordered_items: list[dict[str, Any]]
    expired_item_ids: list[str]
    review_now_item_ids: list[str]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CognitiveTemporalEngine:
    """Tracks wall-clock timing and deterministic temporal agenda state."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._session_start: datetime = datetime.now(UTC)
        self._turn_timestamps: list[tuple[str, datetime, Optional[datetime]]] = []
        self._suppressed_counts: dict[str, int] = {}
        self._snapshot_version = 0
        self._last_agenda_state: TemporalAgendaState | None = None
        self._lock = threading.Lock()

    def record_turn_start(self, turn_id: str) -> None:
        with self._lock:
            self._turn_timestamps.append((turn_id, datetime.now(UTC), None))

    def record_turn_end(self, turn_id: str) -> None:
        now = datetime.now(UTC)
        with self._lock:
            for i, (tid, start, _end) in enumerate(self._turn_timestamps):
                if tid == turn_id:
                    self._turn_timestamps[i] = (tid, start, now)
                    break

    def session_elapsed_seconds(self) -> float:
        return (datetime.now(UTC) - self._session_start).total_seconds()

    def average_turn_duration_ms(self) -> float:
        with self._lock:
            completed = [
                (end - start).total_seconds() * 1000.0
                for _tid, start, end in self._turn_timestamps
                if end is not None
            ]
        if not completed:
            return 0.0
        return sum(completed) / len(completed)

    def last_turn_gap_seconds(self) -> Optional[float]:
        with self._lock:
            starts = [start for _tid, start, _end in self._turn_timestamps]
        if len(starts) < 2:
            return None
        return (starts[-1] - starts[-2]).total_seconds()

    def tick_agenda(
        self,
        *,
        current_time: str | datetime,
        agenda_items: list[dict[str, Any]],
        brain_scope: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(agenda_items, list):
            raise ValueError("agenda_items must be a list")
        now = _parse_time(current_time)
        scope = brain_scope or self._session_id
        open_ids: list[str] = []
        watching_ids: list[str] = []
        overdue_ids: list[str] = []
        expired_ids: list[str] = []
        review_now_ids: list[str] = []
        suppressed_ids: list[str] = []
        ages: list[dict[str, Any]] = []
        windows: list[dict[str, Any]] = []
        cooldowns: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        temporal_items: list[dict[str, Any]] = []

        with self._lock:
            for item in agenda_items:
                if not isinstance(item, dict):
                    raise ValueError("agenda_items entries must be dicts")
                item_id = str(item.get("item_id") or item.get("id") or "")
                if not item_id:
                    raise ValueError("agenda item missing item_id")
                status = str(item.get("status") or "open").lower()
                created_at = _parse_time(item.get("created_at") or now)
                last_reviewed = _optional_time(
                    item.get("last_reviewed_at") or item.get("last_touched_at") or item.get("updated_at")
                )
                last_activity = last_reviewed or created_at
                review_interval = float(item.get("review_interval_seconds") or _default_review_interval(item))
                grace = float(item.get("grace_period_seconds") or 0.0)
                expire_after_raw = item.get("expire_after_seconds")
                expire_after = float(expire_after_raw) if expire_after_raw is not None else None
                cooldown_seconds = float(item.get("cooldown_seconds") or 0.0)
                last_resurfaced = _optional_time(item.get("last_resurfaced_at"))
                review_count = int(item.get("review_count") or 0)

                age_seconds = max(0.0, (now - created_at).total_seconds())
                idle_seconds = max(0.0, (now - last_activity).total_seconds())
                next_due = last_activity + timedelta(seconds=review_interval)
                overdue = now >= next_due
                expired = bool(expire_after is not None and age_seconds >= expire_after)
                window_kind = str(item.get("window_kind") or _window_kind(review_interval))

                age = AgendaAge(
                    item_id=item_id,
                    age_seconds=round(age_seconds, 4),
                    idle_seconds=round(idle_seconds, 4),
                    review_count=review_count,
                    last_reviewed_at=last_reviewed.isoformat() if last_reviewed else None,
                    next_review_due_at=next_due.isoformat(),
                    overdue=overdue,
                    expired=expired,
                )
                window = ReviewWindow(
                    item_id=item_id,
                    window_kind=window_kind,
                    review_interval_seconds=review_interval,
                    grace_period_seconds=grace,
                    expire_after_seconds=expire_after,
                )
                risk = _deferred_risk(item_id=item_id, idle_seconds=idle_seconds, review_interval=review_interval, item=item)
                suppressed_count = self._suppressed_counts.get(item_id, int(item.get("suppressed_count") or 0))
                in_cooldown = bool(
                    last_resurfaced is not None
                    and cooldown_seconds > 0
                    and (now - last_resurfaced).total_seconds() < cooldown_seconds
                )

                should_review = overdue and now >= next_due + timedelta(seconds=grace)
                threshold = float(item.get("resurface_threshold") or 0.35)
                should_resurface = bool(should_review and risk.combined_score >= threshold and not expired)
                if in_cooldown and should_resurface:
                    suppressed_count += 1
                    self._suppressed_counts[item_id] = suppressed_count
                    suppressed_ids.append(item_id)
                    should_resurface = False

                cooldown = ReminderCooldown(
                    item_id=item_id,
                    cooldown_seconds=cooldown_seconds,
                    last_resurfaced_at=last_resurfaced.isoformat() if last_resurfaced else None,
                    suppressed_count=suppressed_count,
                )

                ages.append(age.to_dict())
                windows.append(window.to_dict())
                cooldowns.append(cooldown.to_dict())
                risks.append(risk.to_dict())
                temporal_items.append(
                    TemporalAgendaItem(
                        item_id=item_id,
                        title=str(item.get("title") or item.get("summary") or item_id),
                        summary=str(item.get("summary") or item.get("title") or item_id),
                        status=status,
                        created_at=created_at.isoformat(),
                        next_review_due_at=next_due.isoformat(),
                        expired=expired,
                        deferred_risk_score=risk.to_dict(),
                    ).to_dict()
                )

                if expired:
                    expired_ids.append(item_id)
                elif status not in {"closed", "completed", "cancelled"}:
                    open_ids.append(item_id)
                    if should_resurface:
                        review_now_ids.append(item_id)
                        candidates.append(_attention_candidate(item, risk, age))
                    elif status in {"watching", "blocked", "waiting"} or not overdue:
                        watching_ids.append(item_id)
                    if overdue:
                        overdue_ids.append(item_id)

            self._snapshot_version += 1
            review_now_set = set(review_now_ids)
            suppressed_set = set(suppressed_ids)
            temporal_items.sort(
                key=lambda row: (
                    row["expired"],
                    row["item_id"] not in review_now_set,
                    row["item_id"] in suppressed_set,
                    -float(row["deferred_risk_score"]["combined_score"]),
                    row["next_review_due_at"],
                    row["item_id"],
                )
            )
            cognitive_agenda = CognitiveAgenda(
                agenda_id=_stable_id("cognitive-agenda", self._session_id, str(self._snapshot_version), now.isoformat()),
                ordered_items=temporal_items,
                expired_item_ids=expired_ids,
                review_now_item_ids=review_now_ids,
                generated_at=now.isoformat(),
            )
            state = TemporalAgendaState(
                state_id=_stable_id("temporal-agenda", self._session_id, str(self._snapshot_version), now.isoformat()),
                open_item_ids=open_ids,
                watching_item_ids=watching_ids,
                overdue_item_ids=overdue_ids,
                expired_item_ids=expired_ids,
                review_now_item_ids=review_now_ids,
                created_at=now.isoformat(),
                updated_at=now.isoformat(),
                snapshot_version=self._snapshot_version,
                brain_scope=scope,
                agenda_ages=ages,
                review_windows=windows,
                reminder_cooldowns=cooldowns,
                deferred_risk_scores=risks,
                suppressed_item_ids=suppressed_ids,
                resurfaced_attention_candidates=candidates,
                cognitive_agenda=cognitive_agenda.to_dict(),
            )
            self._last_agenda_state = state
            return state.to_dict()

    def temporal_agenda_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_agenda_state.to_dict() if self._last_agenda_state else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_turns = len(self._turn_timestamps)
            completed_turns = sum(1 for _tid, _start, end in self._turn_timestamps if end is not None)
            temporal_state = self._last_agenda_state.to_dict() if self._last_agenda_state else None
            snapshot_version = self._snapshot_version

        return {
            "session_id": self._session_id,
            "session_start": self._session_start.isoformat(),
            "session_elapsed_seconds": self.session_elapsed_seconds(),
            "total_turns": total_turns,
            "completed_turns": completed_turns,
            "average_turn_duration_ms": self.average_turn_duration_ms(),
            "last_turn_gap_seconds": self.last_turn_gap_seconds(),
            "temporal_agenda_state": temporal_state,
            "snapshot_version": snapshot_version,
        }

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"CognitiveTemporalEngine(session_id={snap['session_id']!r}, "
            f"elapsed={snap['session_elapsed_seconds']:.1f}s, turns={snap['total_turns']})"
        )


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValueError("time value must be ISO string or datetime")


def _optional_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_time(value)


def _default_review_interval(item: dict[str, Any]) -> float:
    risk = str(item.get("risk_level") or item.get("risk") or "medium").lower()
    if risk == "critical":
        return 900.0
    if risk == "high":
        return 3600.0
    if risk == "low":
        return 86400.0
    return 14400.0


def _window_kind(review_interval: float) -> str:
    if review_interval <= 900:
        return "immediate"
    if review_interval <= 6 * 3600:
        return "short_term"
    if review_interval <= 3 * 86400:
        return "mid_term"
    return "long_term"


def _deferred_risk(*, item_id: str, idle_seconds: float, review_interval: float, item: dict[str, Any]) -> DeferredRiskScore:
    denominator = max(1.0, review_interval)
    staleness = min(1.0, idle_seconds / denominator)
    impact = _clamp01(float(item.get("impact_score") if item.get("impact_score") is not None else _impact_from_risk(item)))
    uncertainty = _clamp01(float(item.get("uncertainty_score") if item.get("uncertainty_score") is not None else 0.5))
    combined = round(staleness * impact * uncertainty, 4)
    return DeferredRiskScore(
        item_id=item_id,
        staleness_score=round(staleness, 4),
        impact_score=round(impact, 4),
        uncertainty_score=round(uncertainty, 4),
        combined_score=combined,
    )


def _impact_from_risk(item: dict[str, Any]) -> float:
    risk = str(item.get("risk_level") or item.get("risk") or "medium").lower()
    return {"low": 0.25, "medium": 0.5, "high": 0.8, "critical": 1.0}.get(risk, 0.5)


def _attention_candidate(item: dict[str, Any], risk: DeferredRiskScore, age: AgendaAge) -> dict[str, Any]:
    item_id = str(item.get("item_id") or item.get("id"))
    return {
        "focus_id": f"temporal-review:{item_id}",
        "focus_type": "temporal_agenda_review",
        "title": str(item.get("title") or item.get("summary") or item_id),
        "summary": str(item.get("summary") or item.get("title") or item_id),
        "source_ref": item_id,
        "priority": max(1, int(round(risk.impact_score * 5))),
        "urgency": max(1, int(round(risk.staleness_score * 5))),
        "uncertainty": max(1, int(round(risk.uncertainty_score * 5))),
        "interruptible": True,
        "resume_hint": f"review temporal agenda item {item_id}",
        "deferred_risk_score": risk.to_dict(),
        "agenda_age": age.to_dict(),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
