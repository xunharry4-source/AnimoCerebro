from __future__ import annotations

"""
G38 — QuarantinedMemoryStore with 9-gate validation / 记忆安全隔离区。

Product spec reference
----------------------
G38 (功能 37): "记忆安全与经验包治理机制"
  - 新记忆进入 quarantine/staging 隔离区
  - 经九重校验栅栏通过后，晋升为 untrusted → tentative → verified → protected
  - 九重校验任一失败，记忆不得进入正式长期记忆主链
  - 被吊销记忆不得在 recall 中复活

Design principles
-----------------
1. Every new EnhancedMemoryRecord enters this store first, not the main chain.
2. The 9-gate validator runs synchronously; all 9 checks must pass.
3. On promotion the store returns the validated record plus a trust level upgrade.
4. On rejection the store writes a MemoryAuditEvent with the failure reason and
   the record stays in the staging area as "rejected" — it is never silently lost.
5. The 9 gates are pluggable: callers supply a list of MemoryGate instances.
   The default set covers the product-doc gates; custom gates may be added.
6. This module is NOT the consolidation engine.  It is the write-time safety
   boundary.  The consolidation engine (B8) operates on already-promoted records.

Trust levels
------------
  untrusted  → default on entry into quarantine
  tentative  → passed all 9 gates but not yet human-verified
  verified   → human-reviewed and marked trusted
  protected  → identity kernel / red-line constraints; cannot be downgraded

Mutation semantics (内外之别)
----------------------------
External systems cannot bypass this store to write directly to the main chain.
The AI's own governance pipeline (update_management_state, ConsolidationEngine)
can change a record's *status* within the main chain — those changes are all
recorded in MemoryAuditEvent so the mutation is traceable and reversible.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, List, Literal, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.memory.management.enhanced import (
    EnhancedMemoryRecord,
    MemoryAuditEvent,
    MemoryManagementState,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class GateCheckResult(BaseModel):
    """Outcome of one validation gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_id: str = Field(min_length=1)
    gate_name: str = Field(min_length=1)
    passed: bool
    reason: str = Field(min_length=1)
    details: Dict[str, Any] = Field(default_factory=dict)


class QuarantineDecision(BaseModel):
    """Final decision after all 9 gates have been evaluated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    outcome: Literal["accepted", "staged", "rejected"]
    trust_level_on_accept: str = "tentative"
    gate_results: List[GateCheckResult] = Field(default_factory=list)
    failed_gate_ids: List[str] = Field(default_factory=list)
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class StagedMemoryRecord(BaseModel):
    """A record sitting in the quarantine staging area awaiting promotion."""

    model_config = ConfigDict(extra="forbid")

    record: EnhancedMemoryRecord
    staging_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["pending", "accepted", "rejected", "promoted"] = "pending"
    decision: Optional[QuarantineDecision] = None
    staged_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Gate protocol + built-in gates
# ---------------------------------------------------------------------------

class MemoryGate(Protocol):
    """Contract for a single validation gate in the 9-gate stack."""

    gate_id: str
    gate_name: str

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        """Evaluate the gate and return a pass/fail result.

        Must NOT mutate state.  Must return within a tight timeout so the
        hot path is not stalled.
        """


@dataclass
class ContentIntegrityGate:
    """Gate 1 — 内容完整性校验.

    Verifies that the record's content_hash is present and non-empty, and
    that the hash recomputed from the record's stable fields still matches.
    Detects in-transit tampering.
    """

    gate_id: str = "G1_content_integrity"
    gate_name: str = "Content Integrity"

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        from zentex.memory.management.classification import compute_content_hash

        if not record.content_hash:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason="content_hash is absent — record may have been tampered.",
            )
        expected = compute_content_hash(
            record.memory_layer,
            record.source_kind,
            record.title,
            record.content,
        )
        if record.content_hash != expected:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason="content_hash mismatch — record content was modified after hashing.",
                details={"stored": record.content_hash, "computed": expected},
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="content_hash verified.",
        )


@dataclass
class MinimalContentGate:
    """Gate 2 — 最小内容校验.

    Rejects degenerate records: empty title, empty content, blank summary,
    or missing trace_id.  These cannot form a useful memory.
    """

    gate_id: str = "G2_minimal_content"
    gate_name: str = "Minimal Content"
    min_content_chars: int = 5

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        problems: List[str] = []
        if len(record.title.strip()) < 2:
            problems.append("title too short")
        if len(record.content.strip()) < self.min_content_chars:
            problems.append("content too short")
        if not record.trace_id.strip():
            problems.append("trace_id missing")
        if problems:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Degenerate record: {', '.join(problems)}.",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="Minimal content requirements met.",
        )


@dataclass
class MemoryLayerGate:
    """Gate 3 — 记忆层合法性校验.

    Rejects records whose memory_layer is not one of the three accepted values
    (semantic / procedural / episodic).  Unknown layers indicate misrouted or
    fabricated records.
    """

    gate_id: str = "G3_memory_layer"
    gate_name: str = "Memory Layer"
    allowed_layers: frozenset = field(
        default_factory=lambda: frozenset({"semantic", "procedural", "episodic"})
    )

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if record.memory_layer not in self.allowed_layers:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Unknown memory_layer '{record.memory_layer}'. Allowed: {sorted(self.allowed_layers)}.",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason=f"memory_layer '{record.memory_layer}' is valid.",
        )


@dataclass
class SourceKindGate:
    """Gate 4 — 来源合法性校验.

    Rejects records from unknown source kinds.  Callers configure the allowed
    set; the default covers all first-party sources.  External packages must
    declare a recognised source_kind before their memories can enter the chain.
    """

    gate_id: str = "G4_source_kind"
    gate_name: str = "Source Kind"
    allowed_kinds: frozenset = field(
        default_factory=lambda: frozenset({
            "transcript",
            "upgrade",
            "reflection",
            "consolidation",
            "operator",
            "external_import",
            "nine_question",
            "learning",
        })
    )

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if record.source_kind not in self.allowed_kinds:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Unknown source_kind '{record.source_kind}'.",
                details={"allowed": sorted(self.allowed_kinds)},
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason=f"source_kind '{record.source_kind}' is authorised.",
        )


@dataclass
class AffectBoundGate:
    """Gate 5 — 情感强度边界校验.

    Rejects records whose affect_intensity is out of the [0, 1] range.
    Pydantic already enforces this at construction time, but this gate
    provides an explicit defence-in-depth check at the security boundary.
    """

    gate_id: str = "G5_affect_bound"
    gate_name: str = "Affect Intensity Bound"

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if not (0.0 <= record.affect_intensity <= 1.0):
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"affect_intensity {record.affect_intensity} is outside [0, 1].",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="affect_intensity within bounds.",
        )


@dataclass
class ValidTierGate:
    """Gate 6 — 生命周期层合法性校验.

    Rejects records assigned to an unrecognised memory_tier.
    """

    gate_id: str = "G6_valid_tier"
    gate_name: str = "Valid Memory Tier"
    allowed_tiers: frozenset = field(
        default_factory=lambda: frozenset({"hot", "warm", "cold"})
    )

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if record.memory_tier not in self.allowed_tiers:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Unknown memory_tier '{record.memory_tier}'.",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason=f"memory_tier '{record.memory_tier}' is valid.",
        )


@dataclass
class ConflictRiskGate:
    """Gate 7 — 冲突风险预检 (pluggable).

    Checks for potential conflicts with already-promoted records.  The caller
    supplies an optional conflict checker callable; if none is provided the
    gate always passes (conflict detection is then left to the main-chain
    ingest path).

    The checker receives (record, context) and returns True if a high-risk
    conflict is detected that should block promotion.  Low-risk conflicts are
    surfaced as warnings in `details` but do not block.
    """

    gate_id: str = "G7_conflict_risk"
    gate_name: str = "Conflict Risk"
    conflict_checker: Optional[Callable[[EnhancedMemoryRecord, Dict[str, Any]], bool]] = None

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if self.conflict_checker is None:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=True,
                reason="No conflict checker configured; gate passed by default.",
            )
        try:
            has_conflict = self.conflict_checker(record, context)
        except Exception as exc:  # noqa: BLE001
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Conflict checker raised an error: {exc}",
            )
        if has_conflict:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason="High-risk conflict detected with existing trusted memory.",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="No high-risk conflict detected.",
        )


@dataclass
class IdentityBoundaryGate:
    """Gate 8 — 身份边界保护.

    Prevents external imports and low-trust sources from overwriting
    identity-kernel-level content (protected records, system constraints).
    The allowed_override_sources set lists the only source kinds that may
    propose updates to protected memories.
    """

    gate_id: str = "G8_identity_boundary"
    gate_name: str = "Identity Boundary"
    protected_tags: frozenset = field(
        default_factory=lambda: frozenset({
            "identity_kernel",
            "red_line",
            "protected",
            "system_constraint",
        })
    )
    allowed_override_sources: frozenset = field(
        default_factory=lambda: frozenset({"operator", "consolidation"})
    )

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        record_tags = set(record.tags)
        protected_hit = record_tags & self.protected_tags
        if protected_hit and record.source_kind not in self.allowed_override_sources:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=(
                    f"Record carries protected tag(s) {sorted(protected_hit)} "
                    f"but source_kind '{record.source_kind}' is not authorised to "
                    "write identity-kernel content."
                ),
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="Identity boundary check passed.",
        )


@dataclass
class BrainScopeGate:
    """Gate 9 — 脑范围归属校验.

    Validates that the record's trace_id is plausibly scoped to the current
    brain instance.  In single-instance mode this always passes.  In multi-
    brain mode the caller injects a scope_validator callable that checks the
    trace_id prefix against the known brain_scope identifiers.
    """

    gate_id: str = "G9_brain_scope"
    gate_name: str = "Brain Scope"
    scope_validator: Optional[Callable[[str], bool]] = None  # receives trace_id

    def check(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Dict[str, Any],
    ) -> GateCheckResult:
        if self.scope_validator is None:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=True,
                reason="No scope validator configured; single-instance mode assumed.",
            )
        try:
            in_scope = self.scope_validator(record.trace_id)
        except Exception as exc:  # noqa: BLE001
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"Scope validator raised an error: {exc}",
            )
        if not in_scope:
            return GateCheckResult(
                gate_id=self.gate_id,
                gate_name=self.gate_name,
                passed=False,
                reason=f"trace_id '{record.trace_id}' is outside the current brain scope.",
            )
        return GateCheckResult(
            gate_id=self.gate_id,
            gate_name=self.gate_name,
            passed=True,
            reason="trace_id is within the current brain scope.",
        )


def build_default_gates(
    *,
    conflict_checker: Optional[Callable[[EnhancedMemoryRecord, Dict[str, Any]], bool]] = None,
    scope_validator: Optional[Callable[[str], bool]] = None,
    allowed_source_kinds: Optional[frozenset] = None,
) -> List[MemoryGate]:
    """Build the default 9-gate stack.

    Pass custom callables to enable the conflict-risk and brain-scope checks.
    """
    source_gate = SourceKindGate()
    if allowed_source_kinds is not None:
        source_gate = SourceKindGate(allowed_kinds=allowed_source_kinds)

    return [
        ContentIntegrityGate(),
        MinimalContentGate(),
        MemoryLayerGate(),
        source_gate,
        AffectBoundGate(),
        ValidTierGate(),
        ConflictRiskGate(conflict_checker=conflict_checker),
        IdentityBoundaryGate(),
        BrainScopeGate(scope_validator=scope_validator),
    ]


# ---------------------------------------------------------------------------
# QuarantinedMemoryStore
# ---------------------------------------------------------------------------

class QuarantinedMemoryStore:
    """G38 — Staging and validation boundary for incoming memory records.

    All new EnhancedMemoryRecord objects must pass through this store before
    they can enter the main memory chain.  The store:

      1. Stages the record in an internal quarantine list.
      2. Runs all 9 gates synchronously.
      3. On success: returns the record with trust_level="tentative" and
         writes a PROMOTED audit event.
      4. On failure: marks the record "rejected", writes a REJECTED audit
         event, and raises MemoryRejectedError.  The record remains in the
         quarantine list for forensic review.

    Thread safety: the staging list is protected by a threading.Lock.  Gate
    checks are run outside the lock so slow gates cannot block concurrent
    staging operations.
    """

    def __init__(
        self,
        gates: Optional[List[MemoryGate]] = None,
        *,
        audit_sink: Optional[List[MemoryAuditEvent]] = None,
    ) -> None:
        """
        Args:
            gates: Ordered list of MemoryGate instances.  Defaults to the
                   product-doc 9-gate stack via ``build_default_gates()``.
            audit_sink: Optional external list to receive MemoryAuditEvent
                        records produced by this store.  Useful for wiring up
                        the existing MemoryAuditStore.
        """
        self._gates: List[MemoryGate] = gates if gates is not None else build_default_gates()
        self._staged: Dict[str, StagedMemoryRecord] = {}
        self._lock = Lock()
        self._audit_sink: Optional[List[MemoryAuditEvent]] = audit_sink

    # ── public API ───────────────────────────────────────────────────────

    def validate_and_promote(
        self,
        record: EnhancedMemoryRecord,
        *,
        context: Optional[Dict[str, Any]] = None,
        operator: str = "system",
    ) -> tuple[EnhancedMemoryRecord, QuarantineDecision]:
        """Stage, validate, and attempt to promote a record.

        Returns:
            (record, decision) on success.

        Raises:
            MemoryRejectedError: if any gate fails.  The record is kept in
                the quarantine list as "rejected".
        """
        ctx = context or {}

        # Stage the record first (outside the lock — construction is cheap)
        staged = StagedMemoryRecord(record=record)
        with self._lock:
            self._staged[staged.staging_id] = staged

        # Run all gates outside the lock
        gate_results: List[GateCheckResult] = []
        for gate in self._gates:
            result = gate.check(record, context=ctx)
            gate_results.append(result)
            if not result.passed:
                # Fail-fast: abort remaining gates
                break

        failed = [r for r in gate_results if not r.passed]
        all_passed = len(failed) == 0

        outcome: Literal["accepted", "staged", "rejected"] = (
            "accepted" if all_passed else "rejected"
        )
        decision = QuarantineDecision(
            memory_id=record.memory_id,
            content_hash=record.content_hash,
            outcome=outcome,
            gate_results=gate_results,
            failed_gate_ids=[r.gate_id for r in failed],
        )

        # Update staged record
        now = datetime.now(timezone.utc)
        with self._lock:
            self._staged[staged.staging_id] = StagedMemoryRecord(
                record=record,
                staging_id=staged.staging_id,
                status="accepted" if all_passed else "rejected",
                decision=decision,
                staged_at=staged.staged_at,
                resolved_at=now,
            )

        # Write audit event
        action = "quarantine_promoted" if all_passed else "quarantine_rejected"
        reason = (
            "All 9 gates passed."
            if all_passed
            else f"Gate(s) failed: {', '.join(decision.failed_gate_ids)}. "
                 f"Reason: {failed[0].reason}"
        )
        audit_evt = MemoryAuditEvent(
            memory_id=record.memory_id,
            action=action,
            reason=reason,
            operator=operator,
            details={
                "staging_id": staged.staging_id,
                "decision_id": decision.decision_id,
                "gate_count": len(gate_results),
                "failed_gates": decision.failed_gate_ids,
                "content_hash": record.content_hash,
            },
        )
        if self._audit_sink is not None:
            self._audit_sink.append(audit_evt)

        if not all_passed:
            raise MemoryRejectedError(
                f"Memory '{record.memory_id}' rejected by gate "
                f"'{failed[0].gate_id}': {failed[0].reason}",
                decision=decision,
            )

        return record, decision

    def list_staged(
        self,
        *,
        status: Optional[str] = None,
    ) -> List[StagedMemoryRecord]:
        """Return staged records, optionally filtered by status."""
        with self._lock:
            records = list(self._staged.values())
        if status is not None:
            records = [r for r in records if r.status == status]
        return sorted(records, key=lambda r: r.staged_at, reverse=True)

    def get_staged(self, staging_id: str) -> Optional[StagedMemoryRecord]:
        with self._lock:
            return self._staged.get(staging_id)

    def count_by_status(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            for sr in self._staged.values():
                counts[sr.status] = counts.get(sr.status, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class MemoryRejectedError(RuntimeError):
    """Raised when a record fails one or more quarantine gates."""

    def __init__(self, message: str, decision: QuarantineDecision) -> None:
        super().__init__(message)
        self.decision = decision
