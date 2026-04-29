from __future__ import annotations

from zentex.reflection.label_auditor import ReflectionLabelAuditor
from zentex.reflection.models import ReflectionQuality, ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_label_auditor_real(real_ci_runtime) -> None:
    """功能：通过真实服务插入足量反思记录，验证 CleanLab 审计能识别部分误标质量标签。"""
    suffix = unique_suffix()
    svc = real_ci_runtime.reflection_service

    seeded_ids_by_quality: dict[str, list[str]] = {
        "poor": [],
        "fair": [],
        "good": [],
        "excellent": [],
    }
    templates = {
        "poor": "deployment failure regression unstable incident",
        "fair": "partial improvement mixed outcome moderate issue",
        "good": "stable reusable pattern successful workflow",
        "excellent": "high confidence repeatable evidence backed optimization",
    }

    for quality_name, base_text in templates.items():
        for index in range(30):
            record = svc.record_nine_question_reflection(
                subject=f"label-audit-{quality_name}-{suffix}-{index}",
                reflection_type=ReflectionType.LEARNING_REFLECTION,
                context={
                    "summary": f"{base_text} {suffix} item {index}",
                    "question_id": "q1",
                },
                trace_id=f"label-audit-{suffix}-{quality_name}-{index}",
            )
            updated = svc.update_reflection(
                record.reflection_id,
                {"quality": getattr(ReflectionQuality, quality_name.upper())},
            )
            seeded_ids_by_quality[quality_name].append(updated.reflection_id)

    intentionally_mislabeled = seeded_ids_by_quality["good"][:5]
    for reflection_id in intentionally_mislabeled:
        svc.update_reflection(reflection_id, {"quality": ReflectionQuality.POOR})

    records = [
        svc.get_reflection(reflection_id)
        for quality_ids in seeded_ids_by_quality.values()
        for reflection_id in quality_ids
    ]

    report = ReflectionLabelAuditor().audit(records)
    hits = [rid for rid in intentionally_mislabeled if rid in set(report.suspicious_ids)]

    assert report.total_audited >= 120
    assert report.cleanlab_issue_count >= 1
    assert len(hits) >= 3, f"expected at least 3 mislabeled reflections detected, got {len(hits)}"
