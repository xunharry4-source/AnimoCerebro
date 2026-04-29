from __future__ import annotations

"""WorkingMemoryController for Feature 52.

The controller keeps the legacy bounded slot API while adding the formal
WorkingMemoryFrame / AttentionItem model required by the product spec.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

UTC = timezone.utc


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class FocusBudget:
    max_active_focus: int = 3
    max_suspended_focus: int = 8
    max_revisit_refs: int = 50
    overflow_policy: str = "suspend_noncritical"

    def __post_init__(self) -> None:
        if self.max_active_focus <= 0:
            raise ValueError("max_active_focus must be positive")
        if self.max_suspended_focus < 0:
            raise ValueError("max_suspended_focus must be non-negative")
        if self.max_revisit_refs <= 0:
            raise ValueError("max_revisit_refs must be positive")
        allowed = {"drop_lowest", "compress_oldest", "suspend_noncritical"}
        if self.overflow_policy not in allowed:
            raise ValueError(f"overflow_policy must be one of {sorted(allowed)}")

    @classmethod
    def from_payload(cls, payload: Optional[dict[str, Any]]) -> "FocusBudget":
        if not payload:
            return cls()
        defaults = cls()
        return cls(
            max_active_focus=int(payload.get("max_active_focus", defaults.max_active_focus)),
            max_suspended_focus=int(payload.get("max_suspended_focus", defaults.max_suspended_focus)),
            max_revisit_refs=int(payload.get("max_revisit_refs", defaults.max_revisit_refs)),
            overflow_policy=str(payload.get("overflow_policy", defaults.overflow_policy)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_active_focus": self.max_active_focus,
            "max_suspended_focus": self.max_suspended_focus,
            "max_revisit_refs": self.max_revisit_refs,
            "overflow_policy": self.overflow_policy,
        }


@dataclass
class AttentionItem:
    focus_id: str
    focus_type: str
    title: str
    summary: str
    source_ref: str
    priority: float
    urgency: float
    uncertainty: float
    blocked: bool = False
    interruptible: bool = True
    resume_hint: str = ""
    risk_interrupt: bool = False
    created_at: str = field(default_factory=_now)
    last_touched_at: str = field(default_factory=_now)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AttentionItem":
        if not isinstance(payload, dict):
            raise ValueError("attention item must be an object")
        focus_id = str(payload.get("focus_id") or f"focus-{uuid4().hex}")
        source_ref = str(payload.get("source_ref") or "").strip()
        if not source_ref:
            raise ValueError("attention item source_ref is required")
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("attention item title is required")
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise ValueError("attention item summary is required")
        return cls(
            focus_id=focus_id,
            focus_type=str(payload.get("focus_type") or "agenda"),
            title=title,
            summary=summary,
            source_ref=source_ref,
            priority=float(payload.get("priority", 1)),
            urgency=float(payload.get("urgency", 1)),
            uncertainty=float(payload.get("uncertainty", 1)),
            blocked=bool(payload.get("blocked", False)),
            interruptible=bool(payload.get("interruptible", True)),
            resume_hint=str(payload.get("resume_hint") or ""),
            risk_interrupt=bool(payload.get("risk_interrupt", False)),
            created_at=str(payload.get("created_at") or _now()),
            last_touched_at=str(payload.get("last_touched_at") or _now()),
        )

    @property
    def score(self) -> float:
        return self.priority * self.urgency * self.uncertainty

    def touch(self) -> None:
        self.last_touched_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus_id": self.focus_id,
            "focus_type": self.focus_type,
            "title": self.title,
            "summary": self.summary,
            "source_ref": self.source_ref,
            "priority": self.priority,
            "urgency": self.urgency,
            "uncertainty": self.uncertainty,
            "score": self.score,
            "blocked": self.blocked,
            "interruptible": self.interruptible,
            "resume_hint": self.resume_hint,
            "risk_interrupt": self.risk_interrupt,
            "created_at": self.created_at,
            "last_touched_at": self.last_touched_at,
        }


@dataclass
class AttentionShiftEvent:
    event_id: str
    from_focus_id: str | None
    to_focus_id: str | None
    shift_reason: str
    created_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls,
        *,
        from_focus_id: str | None,
        to_focus_id: str | None,
        shift_reason: str,
    ) -> "AttentionShiftEvent":
        return cls(
            event_id=f"attention-shift-{uuid4().hex}",
            from_focus_id=from_focus_id,
            to_focus_id=to_focus_id,
            shift_reason=shift_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "from_focus_id": self.from_focus_id,
            "to_focus_id": self.to_focus_id,
            "shift_reason": self.shift_reason,
            "created_at": self.created_at,
        }


@dataclass
class WorkingMemoryFrame:
    frame_id: str
    tick_id: str
    active_focus_ids: list[str] = field(default_factory=list)
    suspended_focus_ids: list[str] = field(default_factory=list)
    recently_considered_refs: list[str] = field(default_factory=list)
    attention_budget: FocusBudget = field(default_factory=FocusBudget)
    context_summary: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, tick_id: str, budget: FocusBudget) -> "WorkingMemoryFrame":
        return cls(
            frame_id=f"wm-frame-{uuid4().hex}",
            tick_id=tick_id,
            attention_budget=budget,
        )

    def touch(self, *, tick_id: str | None = None) -> None:
        if tick_id:
            self.tick_id = tick_id
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "tick_id": self.tick_id,
            "active_focus_ids": list(self.active_focus_ids),
            "suspended_focus_ids": list(self.suspended_focus_ids),
            "recently_considered_refs": list(self.recently_considered_refs),
            "attention_budget": self.attention_budget.to_dict(),
            "context_summary": self.context_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WorkingMemoryController:
    """Bounded working memory with attention scheduling semantics."""

    def __init__(self, max_slots: int = 16) -> None:
        self._slots: list[dict[str, Any]] = []
        self._max_slots = max_slots
        self._lock = threading.Lock()
        self._frame: WorkingMemoryFrame | None = None
        self._items: dict[str, AttentionItem] = {}
        self._shift_events: list[AttentionShiftEvent] = []

    # ------------------------------------------------------------------
    # Legacy slot API
    # ------------------------------------------------------------------

    def write(self, key: str, value: dict[str, Any], priority: int = 5) -> bool:
        """Insert or update a legacy slot.

        Returns True when no existing slot was evicted.
        """
        with self._lock:
            for slot in self._slots:
                if slot["key"] == key:
                    slot["value"] = value
                    slot["priority"] = priority
                    return True

            evicted = False
            if len(self._slots) >= self._max_slots:
                victim = min(
                    self._slots,
                    key=lambda slot: (slot["priority"], slot["added_at"]),
                )
                self._slots.remove(victim)
                evicted = True

            self._slots.append(
                {
                    "key": key,
                    "value": value,
                    "priority": priority,
                    "added_at": _now(),
                }
            )
            return not evicted

    def read(self, key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            for slot in self._slots:
                if slot["key"] == key:
                    return dict(slot["value"])
            return None

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(slot) for slot in self._slots]

    def slot_count(self) -> int:
        with self._lock:
            return len(self._slots)

    def budget_remaining(self) -> int:
        with self._lock:
            return self._max_slots - len(self._slots)

    def clear(self) -> None:
        """Clear legacy slots only; Feature 52 frame persists across turns."""
        with self._lock:
            self._slots.clear()

    # ------------------------------------------------------------------
    # Feature 52 frame API
    # ------------------------------------------------------------------

    def update_frame(
        self,
        *,
        tick_id: str,
        new_candidates: list[dict[str, Any]],
        attention_budget: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not str(tick_id or "").strip():
            raise ValueError("tick_id is required")
        if not isinstance(new_candidates, list):
            raise ValueError("new_candidates must be a list")

        with self._lock:
            frame = self._ensure_frame(tick_id=tick_id, budget=FocusBudget.from_payload(attention_budget))
            if attention_budget:
                frame.attention_budget = FocusBudget.from_payload(attention_budget)

            accepted: list[str] = []
            rejected: list[dict[str, Any]] = []
            events_before = len(self._shift_events)
            items = [AttentionItem.from_payload(candidate) for candidate in new_candidates]
            items.sort(key=lambda item: item.score, reverse=True)

            for item in items:
                if item.source_ref in frame.recently_considered_refs:
                    rejected.append(
                        {
                            "focus_id": item.focus_id,
                            "source_ref": item.source_ref,
                            "reason": "recently_considered_ref",
                        }
                    )
                    continue
                existing_id = self._focus_id_by_source_ref(item.source_ref)
                if existing_id:
                    self._items[existing_id].touch()
                    rejected.append(
                        {
                            "focus_id": item.focus_id,
                            "existing_focus_id": existing_id,
                            "source_ref": item.source_ref,
                            "reason": "already_tracked",
                        }
                    )
                    continue
                self._items[item.focus_id] = item
                placement = self._place_candidate(frame, item)
                if placement["accepted"]:
                    accepted.append(item.focus_id)
                else:
                    rejected.append(
                        {
                            "focus_id": item.focus_id,
                            "source_ref": item.source_ref,
                            "reason": placement["reason"],
                        }
                    )
                    self._items.pop(item.focus_id, None)

            frame.context_summary = self._build_context_summary(frame)
            frame.touch(tick_id=tick_id)
            return self._operation_result(
                operation="update_frame",
                accepted_focus_ids=accepted,
                rejected_candidates=rejected,
                new_events=self._shift_events[events_before:],
            )

    def interrupt(self, *, high_risk_item: dict[str, Any], tick_id: str) -> dict[str, Any]:
        item = AttentionItem.from_payload({**high_risk_item, "risk_interrupt": True})
        with self._lock:
            frame = self._ensure_frame(tick_id=tick_id, budget=FocusBudget())
            existing_id = self._focus_id_by_source_ref(item.source_ref)
            if existing_id:
                self._items[existing_id].touch()
                return self._operation_result(
                    operation="interrupt",
                    accepted_focus_ids=[],
                    rejected_candidates=[
                        {
                            "focus_id": item.focus_id,
                            "existing_focus_id": existing_id,
                            "source_ref": item.source_ref,
                            "reason": "already_tracked",
                        }
                    ],
                    new_events=[],
                )
            self._items[item.focus_id] = item
            events_before = len(self._shift_events)
            placement = self._place_candidate(frame, item)
            if not placement["accepted"]:
                self._items.pop(item.focus_id, None)
                raise ValueError(f"high risk interrupt failed: {placement['reason']}")
            frame.context_summary = self._build_context_summary(frame)
            frame.touch(tick_id=tick_id)
            return self._operation_result(
                operation="interrupt",
                accepted_focus_ids=[item.focus_id],
                rejected_candidates=[],
                new_events=self._shift_events[events_before:],
            )

    def resume(self, *, focus_id: str, tick_id: str) -> dict[str, Any]:
        with self._lock:
            frame = self._require_frame()
            if focus_id not in frame.suspended_focus_ids:
                raise KeyError(f"suspended focus not found: {focus_id}")
            item = self._items.get(focus_id)
            if item is None:
                raise KeyError(f"attention item not found: {focus_id}")
            if item.blocked:
                raise ValueError(f"suspended focus is blocked: {focus_id}")

            events_before = len(self._shift_events)
            if len(frame.active_focus_ids) >= frame.attention_budget.max_active_focus:
                victim = self._lowest_active_interruptible(frame)
                if victim is None:
                    raise ValueError("no interruptible active focus available for resume")
                self._suspend_focus(frame, victim, reason="resume_made_room")

            frame.suspended_focus_ids.remove(focus_id)
            frame.active_focus_ids.append(focus_id)
            item.touch()
            self._shift_events.append(
                AttentionShiftEvent.create(
                    from_focus_id=None,
                    to_focus_id=focus_id,
                    shift_reason="resume_condition_met",
                )
            )
            frame.context_summary = self._build_context_summary(frame)
            frame.touch(tick_id=tick_id)
            return self._operation_result(
                operation="resume",
                accepted_focus_ids=[focus_id],
                rejected_candidates=[],
                new_events=self._shift_events[events_before:],
            )

    def mark_considered(self, *, ref_id: str, tick_id: str | None = None) -> dict[str, Any]:
        ref = str(ref_id or "").strip()
        if not ref:
            raise ValueError("ref_id is required")
        with self._lock:
            frame = self._require_frame()
            if ref in frame.recently_considered_refs:
                frame.recently_considered_refs.remove(ref)
            frame.recently_considered_refs.append(ref)
            overflow = len(frame.recently_considered_refs) - frame.attention_budget.max_revisit_refs
            if overflow > 0:
                del frame.recently_considered_refs[:overflow]
            frame.context_summary = self._build_context_summary(frame)
            frame.touch(tick_id=tick_id)
            return self._operation_result(
                operation="mark_considered",
                accepted_focus_ids=[],
                rejected_candidates=[],
                new_events=[],
            )

    def compress_context(self) -> str:
        with self._lock:
            frame = self._require_frame()
            frame.context_summary = self._build_context_summary(frame)
            frame.touch()
            return frame.context_summary

    def frame_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._frame_payload(self._require_frame())

    def shift_events_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.to_dict() for event in self._shift_events]

    # ------------------------------------------------------------------
    # Internal scheduling helpers
    # ------------------------------------------------------------------

    def _ensure_frame(self, *, tick_id: str, budget: FocusBudget) -> WorkingMemoryFrame:
        if self._frame is None:
            self._frame = WorkingMemoryFrame.create(tick_id=tick_id, budget=budget)
        return self._frame

    def _require_frame(self) -> WorkingMemoryFrame:
        if self._frame is None:
            raise KeyError("working memory frame not found")
        return self._frame

    def _place_candidate(self, frame: WorkingMemoryFrame, item: AttentionItem) -> dict[str, Any]:
        if item.blocked:
            return {"accepted": False, "reason": "candidate_blocked"}
        if len(frame.active_focus_ids) < frame.attention_budget.max_active_focus:
            frame.active_focus_ids.append(item.focus_id)
            self._shift_events.append(
                AttentionShiftEvent.create(
                    from_focus_id=None,
                    to_focus_id=item.focus_id,
                    shift_reason="candidate_activated",
                )
            )
            return {"accepted": True}
        if item.risk_interrupt:
            victim = self._lowest_active_interruptible(frame)
            if victim is None:
                return {"accepted": False, "reason": "no_interruptible_active_focus"}
            self._suspend_focus(frame, victim, reason="high_risk_interrupt")
            frame.active_focus_ids.append(item.focus_id)
            self._shift_events.append(
                AttentionShiftEvent.create(
                    from_focus_id=victim.focus_id,
                    to_focus_id=item.focus_id,
                    shift_reason="high_risk_interrupt",
                )
            )
            return {"accepted": True}
        return self._handle_overflow(frame, item)

    def _handle_overflow(self, frame: WorkingMemoryFrame, item: AttentionItem) -> dict[str, Any]:
        policy = frame.attention_budget.overflow_policy
        if policy == "drop_lowest":
            victim = self._lowest_active(frame)
            if victim is not None and item.score > victim.score and victim.interruptible:
                frame.active_focus_ids.remove(victim.focus_id)
                self._items.pop(victim.focus_id, None)
                frame.active_focus_ids.append(item.focus_id)
                self._shift_events.append(
                    AttentionShiftEvent.create(
                        from_focus_id=victim.focus_id,
                        to_focus_id=item.focus_id,
                        shift_reason="overflow_drop_lowest",
                    )
                )
                return {"accepted": True}
            return {"accepted": False, "reason": "overflow_drop_lowest_rejected"}
        if policy == "compress_oldest":
            victim = self._oldest_active(frame)
            if victim is None or not victim.interruptible:
                return {"accepted": False, "reason": "overflow_no_compressible_focus"}
            self._suspend_focus(frame, victim, reason="overflow_compress_oldest")
            frame.active_focus_ids.append(item.focus_id)
            self._shift_events.append(
                AttentionShiftEvent.create(
                    from_focus_id=victim.focus_id,
                    to_focus_id=item.focus_id,
                    shift_reason="overflow_compress_oldest",
                )
            )
            return {"accepted": True}
        if self._append_suspended(frame, item):
            return {"accepted": True}
        return {"accepted": False, "reason": "suspended_focus_budget_exhausted"}

    def _suspend_focus(self, frame: WorkingMemoryFrame, item: AttentionItem, *, reason: str) -> None:
        if item.focus_id in frame.active_focus_ids:
            frame.active_focus_ids.remove(item.focus_id)
        if not item.resume_hint:
            item.resume_hint = f"Resume after {reason} is cleared."
        item.touch()
        if item.focus_id not in frame.suspended_focus_ids:
            if not self._append_suspended(frame, item):
                self._trim_suspended_for_required_item(frame, item)

    def _append_suspended(self, frame: WorkingMemoryFrame, item: AttentionItem) -> bool:
        if item.focus_id in frame.suspended_focus_ids:
            return True
        if len(frame.suspended_focus_ids) >= frame.attention_budget.max_suspended_focus:
            return False
        frame.suspended_focus_ids.append(item.focus_id)
        return True

    def _trim_suspended_for_required_item(self, frame: WorkingMemoryFrame, item: AttentionItem) -> None:
        if frame.attention_budget.max_suspended_focus <= 0:
            raise ValueError("cannot suspend interrupted focus when max_suspended_focus is 0")
        removable_ids = [focus_id for focus_id in frame.suspended_focus_ids if focus_id != item.focus_id]
        if removable_ids:
            victim_id = min(
                removable_ids,
                key=lambda focus_id: (
                    self._items[focus_id].score if focus_id in self._items else 0,
                    self._items[focus_id].last_touched_at if focus_id in self._items else "",
                ),
            )
            frame.suspended_focus_ids.remove(victim_id)
            self._items.pop(victim_id, None)
        if item.focus_id not in frame.suspended_focus_ids:
            frame.suspended_focus_ids.append(item.focus_id)

    def _lowest_active(self, frame: WorkingMemoryFrame) -> AttentionItem | None:
        active = [self._items[focus_id] for focus_id in frame.active_focus_ids if focus_id in self._items]
        if not active:
            return None
        return min(active, key=lambda item: (item.score, item.last_touched_at))

    def _lowest_active_interruptible(self, frame: WorkingMemoryFrame) -> AttentionItem | None:
        active = [
            self._items[focus_id]
            for focus_id in frame.active_focus_ids
            if focus_id in self._items and self._items[focus_id].interruptible
        ]
        if not active:
            return None
        return min(active, key=lambda item: (item.score, item.last_touched_at))

    def _oldest_active(self, frame: WorkingMemoryFrame) -> AttentionItem | None:
        active = [self._items[focus_id] for focus_id in frame.active_focus_ids if focus_id in self._items]
        if not active:
            return None
        return min(active, key=lambda item: item.created_at)

    def _focus_id_by_source_ref(self, source_ref: str) -> str | None:
        for item in self._items.values():
            if item.source_ref == source_ref:
                return item.focus_id
        return None

    def _build_context_summary(self, frame: WorkingMemoryFrame) -> str:
        active_titles = [
            self._items[focus_id].title
            for focus_id in frame.active_focus_ids
            if focus_id in self._items
        ]
        suspended_titles = [
            self._items[focus_id].title
            for focus_id in frame.suspended_focus_ids
            if focus_id in self._items
        ]
        return (
            f"active={len(active_titles)}:{' | '.join(active_titles)}; "
            f"suspended={len(suspended_titles)}:{' | '.join(suspended_titles)}; "
            f"recent_refs={len(frame.recently_considered_refs)}"
        )

    def _operation_result(
        self,
        *,
        operation: str,
        accepted_focus_ids: list[str],
        rejected_candidates: list[dict[str, Any]],
        new_events: list[AttentionShiftEvent],
    ) -> dict[str, Any]:
        frame = self._require_frame()
        return {
            "feature_code": "B1-52",
            "operation": operation,
            "working_memory_status": "updated",
            "frame": self._frame_payload(frame),
            "accepted_focus_ids": accepted_focus_ids,
            "rejected_candidates": rejected_candidates,
            "attention_shift_events": [event.to_dict() for event in new_events],
            "event_count": len(new_events),
        }

    def _frame_payload(self, frame: WorkingMemoryFrame) -> dict[str, Any]:
        active_items = [self._items[focus_id].to_dict() for focus_id in frame.active_focus_ids if focus_id in self._items]
        suspended_items = [
            self._items[focus_id].to_dict()
            for focus_id in frame.suspended_focus_ids
            if focus_id in self._items
        ]
        return {
            **frame.to_dict(),
            "active_items": active_items,
            "suspended_items": suspended_items,
            "attention_shift_event_count": len(self._shift_events),
        }

    def __repr__(self) -> str:
        return f"WorkingMemoryController(slots={self.slot_count()}/{self._max_slots})"
