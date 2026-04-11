from __future__ import annotations

"""
Working memory and attention control layer for Zentex.

This module manages the brain's internal attention slots. It does not trigger
external actions. Its job is to decide which items stay active, which items are
suspended, and how high-priority interruptions should preempt lower-priority
focus when the active attention budget is full.

WorkingMemoryController / 工作记忆与注意力控制器

EN:
WorkingMemoryController is the internal attention-slot manager. It maintains
active focus, suspended focus, interruption handling, and resume hints.

ZH:
WorkingMemoryController（工作记忆与注意力控制器）：负责维护大脑内部的状态特征
与注意力槽位，不直接触发任何外部动作执行或发送外部消息。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass(frozen=True)
class AttentionItem:
    focus_id: str
    focus_type: str
    title: str
    priority: int
    urgency: int
    blocked: bool
    interruptible: bool
    resume_hint: Optional[str]
    uncertainty: Optional[float] = 0.0
    source_ref: Optional[str] = None
    summary: Optional[str] = None


@dataclass(frozen=True)
class FocusBudget:
    max_active_focus: int
    max_suspended_focus: int
    overflow_policy: str


@dataclass(frozen=True)
class AttentionShiftEvent:
    event_id: str
    previous_focus_id: Optional[str]
    new_focus_id: str
    shift_reason: str
    timestamp_ms: int


@dataclass(frozen=True)
class WorkingMemoryFrame:
    frame_id: str
    active_focus_ids: List[str]
    suspended_focus_ids: List[str]
    recently_considered_refs: List[str]
    attention_budget: FocusBudget
    context_summary: str


class WorkingMemoryController:
    """
    Maintains attention slots and bounded working-memory focus.

    Hard rules:
    - active focus count must respect the FocusBudget limit
    - high-risk or higher-priority items may interrupt lower-priority items
    - interrupted items may be suspended only if recoverable, in which case a
      resume hint must be retained
    - no external actions are triggered from this controller
    """

    def __init__(self, budget: FocusBudget) -> None:
        self.budget = budget
        self._items: Dict[str, AttentionItem] = {}
        self._active_focus_ids: List[str] = []
        self._suspended_focus_ids: List[str] = []
        self._recently_considered_refs: List[str] = []

    def upsert_focus(self, item: AttentionItem) -> WorkingMemoryFrame:
        self._items[item.focus_id] = item
        if item.source_ref and item.source_ref not in self._recently_considered_refs:
            self._recently_considered_refs.append(item.source_ref)
            if len(self._recently_considered_refs) > 100:
                self._recently_considered_refs.pop(0)
        if item.focus_id in self._suspended_focus_ids:
            self._suspended_focus_ids.remove(item.focus_id)
        if item.focus_id in self._active_focus_ids:
            self._sort_active_focus()
            return self.get_frame()

        if len(self._active_focus_ids) < self.budget.max_active_focus:
            self._active_focus_ids.append(item.focus_id)
            self._sort_active_focus()
            return self.get_frame()

        interrupted = self._try_interrupt_for(item)
        if interrupted:
            self._active_focus_ids.append(item.focus_id)
            self._sort_active_focus()
        else:
            self._suspend_item(item.focus_id)
        return self.get_frame()

    def suspend_focus(self, focus_id: str, *, resume_hint: Optional[str] = None) -> WorkingMemoryFrame:
        if focus_id not in self._items:
            raise KeyError(f"Unknown focus_id: {focus_id}")
        item = self._items[focus_id]
        if focus_id in self._active_focus_ids:
            self._active_focus_ids.remove(focus_id)
        if resume_hint is not None:
            self._items[focus_id] = AttentionItem(
                focus_id=item.focus_id,
                focus_type=item.focus_type,
                title=item.title,
                priority=item.priority,
                urgency=item.urgency,
                blocked=item.blocked,
                interruptible=item.interruptible,
                resume_hint=resume_hint,
                uncertainty=item.uncertainty,
                source_ref=item.source_ref,
                summary=item.summary,
            )
        self._suspend_item(focus_id)
        return self.get_frame()

    def resume_focus(self, focus_id: str) -> WorkingMemoryFrame:
        if focus_id not in self._items:
            raise KeyError(f"Unknown focus_id: {focus_id}")
        if focus_id in self._suspended_focus_ids:
            self._suspended_focus_ids.remove(focus_id)
        return self.upsert_focus(self._items[focus_id])

    def emit_attention_shift(self, previous_id: Optional[str], new_id: str, reason: str) -> AttentionShiftEvent:
        import time
        return AttentionShiftEvent(
            event_id=str(uuid4()),
            previous_focus_id=previous_id,
            new_focus_id=new_id,
            shift_reason=reason,
            timestamp_ms=int(time.time() * 1000)
        )

    def persist_to_store(self, store_adapter: Any) -> None:
        """Integration boundary for BrainSession/BrainTranscriptStore persistence."""
        if hasattr(store_adapter, "save_frame"):
            store_adapter.save_frame(self.get_frame())

    def evaluate_thinkloop(self, signals: Any) -> None:
        """Integration with ThinkLoop Phase 3 & 4."""
        pass

    def get_frame(self) -> WorkingMemoryFrame:
        return WorkingMemoryFrame(
            frame_id=str(uuid4()),
            active_focus_ids=list(self._active_focus_ids),
            suspended_focus_ids=list(self._suspended_focus_ids),
            recently_considered_refs=list(self._recently_considered_refs),
            attention_budget=self.budget,
            context_summary=self._build_context_summary(),
        )

    def list_active_items(self) -> List[AttentionItem]:
        return [self._items[focus_id] for focus_id in self._active_focus_ids]

    def list_suspended_items(self) -> List[AttentionItem]:
        return [self._items[focus_id] for focus_id in self._suspended_focus_ids]

    def _try_interrupt_for(self, incoming_item: AttentionItem) -> bool:
        # High-priority or blocked risk items may preempt a lower-priority,
        # interruptible focus when the active attention budget is already full.
        interrupt_candidate_id = self._find_interrupt_candidate(incoming_item)
        if interrupt_candidate_id is None:
            return False

        candidate = self._items[interrupt_candidate_id]
        resume_hint = candidate.resume_hint or f"Resume after handling {incoming_item.title}"
        self._items[interrupt_candidate_id] = AttentionItem(
            focus_id=candidate.focus_id,
            focus_type=candidate.focus_type,
            title=candidate.title,
            priority=candidate.priority,
            urgency=candidate.urgency,
            blocked=candidate.blocked,
            interruptible=candidate.interruptible,
            resume_hint=resume_hint,
            uncertainty=candidate.uncertainty,
            source_ref=candidate.source_ref,
            summary=candidate.summary,
        )
        self._active_focus_ids.remove(interrupt_candidate_id)
        self._suspend_item(interrupt_candidate_id)
        return True

    def _find_interrupt_candidate(self, incoming_item: AttentionItem) -> Optional[str]:
        active_items = self.list_active_items()
        interruptible_items = [item for item in active_items if item.interruptible]
        if not interruptible_items:
            return None

        interruptible_items.sort(
            key=lambda item: (item.priority, item.urgency, item.blocked),
        )
        candidate = interruptible_items[0]
        incoming_weight = self._focus_weight(incoming_item)
        candidate_weight = self._focus_weight(candidate)
        if incoming_weight > candidate_weight:
            return candidate.focus_id
        return None

    def _focus_weight(self, item: AttentionItem) -> int:
        risk_bonus = 2 if item.focus_type == "risk" else 0
        blocked_bonus = 1 if item.blocked else 0
        return item.priority * 10 + item.urgency + risk_bonus + blocked_bonus

    def _suspend_item(self, focus_id: str) -> None:
        if focus_id in self._active_focus_ids:
            self._active_focus_ids.remove(focus_id)
        if focus_id not in self._suspended_focus_ids:
            self._suspended_focus_ids.append(focus_id)
        if len(self._suspended_focus_ids) > self.budget.max_suspended_focus:
            overflow = len(self._suspended_focus_ids) - self.budget.max_suspended_focus
            if self.budget.overflow_policy == "drop_oldest":
                del self._suspended_focus_ids[:overflow]
            elif self.budget.overflow_policy == "drop_lowest_priority":
                self._drop_lowest_priority_suspended(overflow)

    def _drop_lowest_priority_suspended(self, overflow: int) -> None:
        suspended_items = sorted(
            self._suspended_focus_ids,
            key=lambda focus_id: (
                self._items[focus_id].priority,
                self._items[focus_id].urgency,
            ),
        )
        for focus_id in suspended_items[:overflow]:
            if focus_id in self._suspended_focus_ids:
                self._suspended_focus_ids.remove(focus_id)

    def _sort_active_focus(self) -> None:
        self._active_focus_ids.sort(
            key=lambda focus_id: self._focus_weight(self._items[focus_id]),
            reverse=True,
        )
        self._active_focus_ids[:] = self._active_focus_ids[: self.budget.max_active_focus]

    def _build_context_summary(self) -> str:
        active_titles = [self._items[focus_id].title for focus_id in self._active_focus_ids]
        suspended_titles = [self._items[focus_id].title for focus_id in self._suspended_focus_ids]
        return (
            f"active={active_titles or []}; "
            f"suspended={suspended_titles or []}; "
            f"budget=({self.budget.max_active_focus}/{self.budget.max_suspended_focus})"
        )
