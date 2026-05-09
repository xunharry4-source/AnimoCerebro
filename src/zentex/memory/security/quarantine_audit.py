from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.memory.security.quarantine import build_default_gates


class QuarantineGateAuditIssue(BaseModel):
    """One structural problem found in the default quarantine gate stack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class QuarantineGateAuditError(RuntimeError):
    """Raised when the default G38 quarantine gate stack is incomplete."""

    def __init__(self, message: str, *, issues: list[QuarantineGateAuditIssue]) -> None:
        self.issues = issues
        detail = "; ".join(f"{issue.path}: {issue.reason}" for issue in issues)
        super().__init__(f"{message}: {detail}" if detail else message)


class QuarantineGateAuditItem(BaseModel):
    """Audited metadata for one gate in the default 9-gate stack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=1)
    gate_id: str = Field(min_length=1)
    gate_name: str = Field(min_length=1)
    implementation_class: str = Field(min_length=1)
    has_check_method: bool


class QuarantineGateAuditReport(BaseModel):
    """Audit report proving the default quarantine stack is complete."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_status: str = Field(min_length=1)
    expected_gate_count: int = 9
    actual_gate_count: int = Field(ge=0)
    gate_items: list[QuarantineGateAuditItem] = Field(default_factory=list)
    gate_ids: list[str] = Field(default_factory=list)


EXPECTED_DEFAULT_GATE_IDS: tuple[str, ...] = (
    "G1_content_integrity",
    "G2_minimal_content",
    "G3_memory_layer",
    "G4_source_kind",
    "G5_affect_bound",
    "G6_valid_tier",
    "G7_conflict_risk",
    "G8_identity_boundary",
    "G9_brain_scope",
)

EXPECTED_DEFAULT_GATE_NAMES: tuple[str, ...] = (
    "Content Integrity",
    "Minimal Content",
    "Memory Layer",
    "Source Kind",
    "Affect Intensity Bound",
    "Valid Memory Tier",
    "Conflict Risk",
    "Identity Boundary",
    "Brain Scope",
)


def audit_default_quarantine_gates() -> QuarantineGateAuditReport:
    """
    Verify that the default G38 quarantine stack exposes the product-doc 9 gates.

    This is a structural audit only; behavioral rejection paths are covered by
    real tests through QuarantinedMemoryStore.
    """

    gates = build_default_gates()
    issues: list[QuarantineGateAuditIssue] = []
    items: list[QuarantineGateAuditItem] = []

    if len(gates) != len(EXPECTED_DEFAULT_GATE_IDS):
        issues.append(
            QuarantineGateAuditIssue(
                path="build_default_gates",
                reason=f"expected 9 gates, found {len(gates)}",
            )
        )

    for index, gate in enumerate(gates, start=1):
        gate_id = _required_attr(gate, "gate_id", issues, f"gates[{index - 1}]")
        gate_name = _required_attr(gate, "gate_name", issues, f"gates[{index - 1}]")
        has_check_method = callable(getattr(gate, "check", None))
        if not has_check_method:
            issues.append(
                QuarantineGateAuditIssue(
                    path=f"gates[{index - 1}].check",
                    reason="check method missing or not callable",
                )
            )
        expected_id = (
            EXPECTED_DEFAULT_GATE_IDS[index - 1]
            if index <= len(EXPECTED_DEFAULT_GATE_IDS)
            else None
        )
        expected_name = (
            EXPECTED_DEFAULT_GATE_NAMES[index - 1]
            if index <= len(EXPECTED_DEFAULT_GATE_NAMES)
            else None
        )
        if expected_id is not None and gate_id != expected_id:
            issues.append(
                QuarantineGateAuditIssue(
                    path=f"gates[{index - 1}].gate_id",
                    reason=f"expected {expected_id}, found {gate_id}",
                )
            )
        if expected_name is not None and gate_name != expected_name:
            issues.append(
                QuarantineGateAuditIssue(
                    path=f"gates[{index - 1}].gate_name",
                    reason=f"expected {expected_name}, found {gate_name}",
                )
            )
        items.append(
            QuarantineGateAuditItem(
                index=index,
                gate_id=gate_id,
                gate_name=gate_name,
                implementation_class=gate.__class__.__name__,
                has_check_method=has_check_method,
            )
        )

    if issues:
        raise QuarantineGateAuditError("default quarantine gate audit failed", issues=issues)

    return QuarantineGateAuditReport(
        audit_status="passed",
        actual_gate_count=len(gates),
        gate_items=items,
        gate_ids=[item.gate_id for item in items],
    )


def _required_attr(
    gate: Any,
    attr_name: str,
    issues: list[QuarantineGateAuditIssue],
    path: str,
) -> str:
    value = getattr(gate, attr_name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    issues.append(
        QuarantineGateAuditIssue(
            path=f"{path}.{attr_name}",
            reason="must be a non-empty string",
        )
    )
    return ""
