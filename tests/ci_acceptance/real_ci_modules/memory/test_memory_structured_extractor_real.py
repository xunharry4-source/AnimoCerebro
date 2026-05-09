from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.memory.extraction.structured_extractor import (
    StructuredExtractionError,
    extract_structured_memory_items,
)


def test_memory_structured_extractor_reads_five_kinds_from_real_record(real_ci_runtime) -> None:
    """功能：真实 remember/get_record/recall 后提取 fact/event/case/lesson/constraint 五类。"""

    suffix = unique_suffix()
    trace_id = f"trace-structured-{suffix}"
    structured_memory = {
        "facts": [
            {
                "statement": f"Q8 verification completed with exact outcome binding {suffix}.",
                "source": "task_outcomes",
            }
        ],
        "events": [
            {
                "event_type": "task_status_changed",
                "description": f"Task entered DONE only after verification bridge persisted outcome {suffix}.",
                "occurred_at": "2026-04-28T10:30:00Z",
            }
        ],
        "cases": [
            {
                "case_id": f"case-{suffix}",
                "condition": "Q8 task has verification.enabled=True",
                "action": "update_task_status(DONE)",
                "outcome": "task_outcomes row exists and recall can find the memory",
            }
        ],
        "lessons": [
            {
                "lesson": "Do not infer success from free text when structured task_outcomes exist.",
                "applies_to": "ExperienceExtractor",
            }
        ],
        "constraints": [
            {
                "rule": "service.py must stay a thin facade for memory extraction.",
                "scope": "memory.extraction",
                "non_bypassable": True,
            }
        ],
    }

    rec = real_ci_runtime.memory_service.remember(
        title=f"structured-memory-{suffix}",
        summary=f"structured extraction source {suffix}",
        content=f"structured-memory-content-{suffix}",
        layer="semantic",
        source="tests.ci_acceptance.memory",
        trace_id=trace_id,
        target_id=f"target-{suffix}",
        tags=["phase-m", suffix],
        structured_memory=structured_memory,
    )

    got = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert got is not None
    assert got.memory_id == rec.memory_id
    assert got.trace_id == trace_id
    assert got.payload["structured_memory"]["facts"][0]["statement"].endswith(f"{suffix}.")

    hits = real_ci_runtime.memory_service.recall(suffix, limit=20, trace_id=trace_id)
    assert any(getattr(hit, "memory_id", "") == rec.memory_id for hit in hits), "recall 未命中新写入结构化记忆"

    report = extract_structured_memory_items(got)

    assert report.source_memory_id == rec.memory_id
    assert report.trace_id == trace_id
    assert report.extraction_status == "extracted"
    assert report.item_count == 5
    assert report.counts_by_kind == {
        "fact": 1,
        "event": 1,
        "case": 1,
        "lesson": 1,
        "constraint": 1,
    }

    by_kind = {item.kind: item for item in report.items}
    assert by_kind["fact"].content == f"Q8 verification completed with exact outcome binding {suffix}."
    assert by_kind["fact"].evidence_path == "payload.structured_memory.facts[0].statement"
    assert by_kind["event"].attributes["event_type"] == "task_status_changed"
    assert by_kind["event"].content == f"Task entered DONE only after verification bridge persisted outcome {suffix}."
    assert by_kind["case"].attributes["case_id"] == f"case-{suffix}"
    assert by_kind["case"].content == (
        "Q8 task has verification.enabled=True -> update_task_status(DONE) -> "
        "task_outcomes row exists and recall can find the memory"
    )
    assert by_kind["lesson"].content == "Do not infer success from free text when structured task_outcomes exist."
    assert by_kind["constraint"].content == "service.py must stay a thin facade for memory extraction."
    assert by_kind["constraint"].attributes["non_bypassable"] is True
    assert all(item.source_memory_id == rec.memory_id for item in report.items)
    assert all(item.trace_id == trace_id for item in report.items)


def test_memory_structured_extractor_rejects_malformed_explicit_items(real_ci_runtime) -> None:
    """异常：显式结构化字段不合约时必须 fail-closed，不能静默跳过坏项。"""

    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"structured-malformed-{suffix}",
        content=f"structured-malformed-content-{suffix}",
        layer="semantic",
        source="tests.ci_acceptance.memory",
        trace_id=f"trace-malformed-{suffix}",
        tags=["phase-m", suffix],
        structured_memory={
            "facts": [{"statement": f"valid fact should not hide malformed items {suffix}"}],
            "lessons": [{"applies_to": "missing lesson field"}],
            "constraints": [{"rule": "", "scope": "memory.extraction", "non_bypassable": "yes"}],
        },
    )
    got = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert got is not None

    with pytest.raises(StructuredExtractionError) as exc_info:
        extract_structured_memory_items(got)

    issue_paths = {issue.path for issue in exc_info.value.issues}
    assert "payload.structured_memory.lessons[0].lesson" in issue_paths
    assert "payload.structured_memory.constraints[0].rule" in issue_paths
    assert "payload.structured_memory.constraints[0].non_bypassable" in issue_paths
    assert str(exc_info.value).startswith("structured memory extraction failed")


def test_memory_structured_extractor_returns_explicit_empty_report_for_unstructured_record(real_ci_runtime) -> None:
    """边界：无结构化字段时返回 empty 报告，且来源和 trace 仍可审计。"""

    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"structured-empty-{suffix}",
        content=f"unstructured content {suffix}",
        layer="semantic",
        source="tests.ci_acceptance.memory",
        trace_id=f"trace-empty-{suffix}",
        tags=["phase-m", suffix],
    )
    got = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert got is not None

    report = extract_structured_memory_items(got)

    assert report.source_memory_id == rec.memory_id
    assert report.trace_id == f"trace-empty-{suffix}"
    assert report.extraction_status == "empty"
    assert report.item_count == 0
    assert report.items == []
    assert report.counts_by_kind == {
        "fact": 0,
        "event": 0,
        "case": 0,
        "lesson": 0,
        "constraint": 0,
    }
