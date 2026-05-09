from __future__ import annotations

from typing import Any

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix

from zentex.memory.management.enhanced import EnhancedMemoryRecord
from zentex.memory.security.quarantine import (
    MemoryRejectedError,
    QuarantinedMemoryStore,
    build_default_gates,
)
from zentex.memory.security.quarantine_audit import (
    EXPECTED_DEFAULT_GATE_IDS,
    audit_default_quarantine_gates,
)


def _valid_record(suffix: str, **overrides: object) -> EnhancedMemoryRecord:
    data = {
        "memory_layer": "semantic",
        "source_kind": "operator",
        "title": f"valid quarantine memory {suffix}",
        "summary": f"valid quarantine summary {suffix}",
        "content": f"validated quarantine content with enough detail {suffix}",
        "trace_id": f"trace-quarantine-{suffix}",
        "tags": ["phase-m", suffix],
    }
    data.update(overrides)
    return EnhancedMemoryRecord(**data)


def _expect_rejected(
    *,
    record: EnhancedMemoryRecord,
    expected_gate_id: str,
    gates: list[Any] | None = None,
) -> MemoryRejectedError:
    audit_sink = []
    store = QuarantinedMemoryStore(gates=gates, audit_sink=audit_sink)

    with pytest.raises(MemoryRejectedError) as exc_info:
        store.validate_and_promote(record, operator="ci_quarantine_audit")

    decision = exc_info.value.decision
    assert decision.outcome == "rejected"
    assert decision.failed_gate_ids == [expected_gate_id]
    assert decision.gate_results[-1].gate_id == expected_gate_id
    assert decision.gate_results[-1].passed is False
    assert store.count_by_status() == {"rejected": 1}
    staged = store.list_staged(status="rejected")
    assert len(staged) == 1
    assert staged[0].record.memory_id == record.memory_id
    assert staged[0].decision is not None
    assert staged[0].decision.failed_gate_ids == [expected_gate_id]
    assert len(audit_sink) == 1
    assert audit_sink[0].action == "quarantine_rejected"
    assert audit_sink[0].memory_id == record.memory_id
    assert audit_sink[0].details["failed_gates"] == [expected_gate_id]
    assert audit_sink[0].details["gate_count"] == len(decision.gate_results)
    return exc_info.value


def test_memory_quarantine_default_gate_audit_reports_exact_nine_gate_stack() -> None:
    """查询：默认 G38 gate stack 必须精确包含 9 项产品校验栅栏。"""

    report = audit_default_quarantine_gates()

    assert report.audit_status == "passed"
    assert report.expected_gate_count == 9
    assert report.actual_gate_count == 9
    assert report.gate_ids == list(EXPECTED_DEFAULT_GATE_IDS)
    assert [item.index for item in report.gate_items] == list(range(1, 10))
    assert all(item.has_check_method is True for item in report.gate_items)
    assert [item.implementation_class for item in report.gate_items] == [
        "ContentIntegrityGate",
        "MinimalContentGate",
        "MemoryLayerGate",
        "SourceKindGate",
        "AffectBoundGate",
        "ValidTierGate",
        "ConflictRiskGate",
        "IdentityBoundaryGate",
        "BrainScopeGate",
    ]


def test_memory_quarantine_promotes_valid_record_after_all_nine_gates() -> None:
    """新增/查询：合法记录必须跑完 9 个 gate、写 promotion audit、进入 accepted staging。"""

    suffix = unique_suffix()
    audit_sink = []
    store = QuarantinedMemoryStore(audit_sink=audit_sink)
    record = _valid_record(suffix)

    promoted, decision = store.validate_and_promote(record, operator="ci_quarantine_audit")

    assert promoted.memory_id == record.memory_id
    assert decision.outcome == "accepted"
    assert decision.trust_level_on_accept == "tentative"
    assert decision.failed_gate_ids == []
    assert [result.gate_id for result in decision.gate_results] == list(EXPECTED_DEFAULT_GATE_IDS)
    assert all(result.passed is True for result in decision.gate_results)
    assert store.count_by_status() == {"accepted": 1}
    accepted = store.list_staged(status="accepted")
    assert len(accepted) == 1
    assert accepted[0].record.memory_id == record.memory_id
    assert accepted[0].decision is not None
    assert accepted[0].decision.outcome == "accepted"
    assert len(audit_sink) == 1
    assert audit_sink[0].action == "quarantine_promoted"
    assert audit_sink[0].memory_id == record.memory_id
    assert audit_sink[0].details["gate_count"] == 9
    assert audit_sink[0].details["failed_gates"] == []


def test_memory_quarantine_rejects_each_gate_failure_with_forensic_state() -> None:
    """异常：9 个 gate 的失败路径都必须真实拒绝并保留 quarantine/audit 证据。"""

    suffix = unique_suffix()
    base = _valid_record(suffix)

    cases: list[tuple[str, EnhancedMemoryRecord, list[Any] | None]] = [
        (
            "G1_content_integrity",
            base.model_copy(update={"content_hash": "tampered"}),
            None,
        ),
        (
            "G2_minimal_content",
            _valid_record(f"{suffix}-g2", title="x"),
            None,
        ),
        (
            "G3_memory_layer",
            _valid_record(f"{suffix}-g3", memory_layer="invented"),
            None,
        ),
        (
            "G4_source_kind",
            _valid_record(f"{suffix}-g4", source_kind="unknown_source"),
            None,
        ),
        (
            "G5_affect_bound",
            _valid_record(f"{suffix}-g5").model_copy(
                update={"affect_intensity": 1.5}
            ),
            None,
        ),
        (
            "G6_valid_tier",
            _valid_record(f"{suffix}-g6").model_copy(update={"memory_tier": "volatile"}),
            None,
        ),
        (
            "G7_conflict_risk",
            _valid_record(f"{suffix}-g7"),
            build_default_gates(conflict_checker=_always_conflicts),
        ),
        (
            "G8_identity_boundary",
            _valid_record(
                f"{suffix}-g8",
                source_kind="external_import",
                tags=["identity_kernel"],
            ),
            None,
        ),
        (
            "G9_brain_scope",
            _valid_record(f"{suffix}-g9", trace_id="foreign-brain-trace"),
            build_default_gates(
                scope_validator=lambda trace_id: trace_id.startswith(
                    "trace-quarantine-"
                )
            ),
        ),
    ]

    for expected_gate_id, record, gates in cases:
        rejection = _expect_rejected(
            record=record,
            expected_gate_id=expected_gate_id,
            gates=gates,
        )
        assert expected_gate_id in str(rejection)


def _always_conflicts(record: EnhancedMemoryRecord, context: dict[str, object]) -> bool:
    return True
