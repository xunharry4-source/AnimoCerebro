from __future__ import annotations
"""FlowAudit — lightweight cross-module audit context.

Design principles:
  • Zero external dependencies — pure dataclass.
  • Every module entry point accepts ``audit: Optional[FlowAudit] = None``.
    If None the module creates a fresh one; if provided the caller already
    grouped this operation into an existing audit flow.
  • ``FlowAudit.as_payload()`` returns a small dict that is merged into any
    existing transcript/event payload.  The audit infrastructure then extracts
    ``audit_id`` automatically — no new storage needed.

Typical call flow:

    # 1. Nine-questions bootstrap creates the root flow
    audit = FlowAudit.new("nine_questions", source_module="nine_questions.service")
    state = await nq_service.execute_all(audit=audit)

    # 2. Reflection continues *in the same audit flow*
    ref_audit = audit.spawn("reflection", source_module="reflection.service")
    reflection_svc.generate_reflection(..., audit=ref_audit)

    # 3. Learning also chains in
    learn_audit = audit.spawn("learning", source_module="learning.engine")
    await start_learning(..., audit=learn_audit)

    # Later — query everything under one audit_id
    store.list_audit_entries_by_audit_id(audit.audit_id)
"""


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4


@dataclass
class FlowAudit:
    """Carries cross-module audit identity for one logical operation flow."""

    # ------------------------------------------------------------------ #
    # Fields                                                               #
    # ------------------------------------------------------------------ #

    audit_id: str
    """Unique identifier that groups all operations in this flow."""

    flow_type: str
    """
    Human-readable category of the flow.
    Conventional values: ``"nine_questions"`` | ``"reflection"`` | ``"learning"``
    | ``"task_generation"``.
    """

    source_module: str
    """Dotted module name that initiated this flow, e.g. ``"nine_questions.service"``."""

    question_driver_refs: list[str] = field(default_factory=list)
    """Which nine-question IDs (q1…q9) drove or are relevant to this flow."""

    parent_audit_id: Optional[str] = None
    """Set when this flow was spawned from a parent; enables tree traversal."""

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------ #
    # Constructors                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def new(
        cls,
        flow_type: str,
        *,
        source_module: str = "",
        question_driver_refs: list[Optional[str]] = None,
    ) -> "FlowAudit":
        """Create a fresh audit flow with a unique ``audit_id``."""
        return cls(
            audit_id=uuid4().hex,
            flow_type=flow_type,
            source_module=source_module,
            question_driver_refs=list(question_driver_refs or []),
        )

    def spawn(self, flow_type: str, *, source_module: str = "") -> "FlowAudit":
        """Create a child flow linked to this flow by ``parent_audit_id``."""
        return FlowAudit(
            audit_id=uuid4().hex,
            flow_type=flow_type,
            source_module=source_module,
            question_driver_refs=list(self.question_driver_refs),
            parent_audit_id=self.audit_id,
        )

    # ------------------------------------------------------------------ #
    # Payload helper                                                       #
    # ------------------------------------------------------------------ #

    def as_payload(self) -> dict[str, Any]:
        """Return a small dict to be merged into any transcript entry payload.

        Example usage inside a module::

            store.write_entry(
                ...
                payload={"kind": "cycle_started", **audit.as_payload()},
            )

        The audit infrastructure extracts ``audit_id`` from the payload and
        indexes it automatically — callers need nothing else.
        """
        d: dict[str, Any] = {
            "audit_id": self.audit_id,
            "flow_type": self.flow_type,
            "source_module": self.source_module,
        }
        if self.question_driver_refs:
            d["question_driver_refs"] = self.question_driver_refs
        if self.parent_audit_id:
            d["parent_audit_id"] = self.parent_audit_id
        return d
