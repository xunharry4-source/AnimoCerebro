from __future__ import annotations

from typing import Any

from zentex.nine_questions.plan_evidence_registry import (
    COMPLETION_EVIDENCE_KINDS,
    EVIDENCE_REQUIREMENTS,
    build_plan_evidence_summary,
)
from zentex.nine_questions.plan_execution_evidence import (
    EXECUTION_EVIDENCE_REQUIREMENTS,
    build_plan_execution_evidence_summary,
)


class PlanRemainingWorkError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]], report: dict[str, Any]) -> None:
        self.failures = failures
        self.report = report
        super().__init__("Plan remaining work audit failed")


NON_MANIFEST_REQUIREMENTS = {
    "browser_e2e_validation": {
        "required_evidence": "真实浏览器访问 Q8/V1.0 页面并校验 Phase B/C/D、证据门禁和 waiting evidence 展示",
        "completion_condition": "Playwright 或等价浏览器 E2E 运行通过，并保留 URL、断言字段和截图/trace 证据",
    },
    "frontend_build_validation": {
        "required_evidence": "admin portal 全量 npm run build 通过",
        "completion_condition": "TypeScript build 和 Vite build exit_code=0；当前既有非 Q8 TS 错误不能隐藏",
    },
    "full_pytest_regression": {
        "required_evidence": "仓库 V1.0 相关全量真实 pytest 回归",
        "completion_condition": "相关 nine/reflection/learning/upgrade/web console/admin portal 测试全部真实通过",
    },
}


def build_plan_remaining_work_report(*, learning_service: Any) -> dict[str, Any]:
    evidence_summary = build_plan_evidence_summary(learning_service=learning_service)
    execution_summary = build_plan_execution_evidence_summary(learning_service=learning_service)
    completion_kinds = set(evidence_summary["completion_evidence_kinds"])
    execution_kinds = set(execution_summary["completed_execution_evidence_kinds"])

    evidence_items: list[dict[str, Any]] = []
    for source_kind in sorted(COMPLETION_EVIDENCE_KINDS):
        requirements = EVIDENCE_REQUIREMENTS[source_kind]
        matching_manifests = [
            item
            for item in evidence_summary["manifests"]
            if item.get("source_kind") == source_kind and item.get("counts_toward_completion") is True
        ]
        status = "completed" if source_kind in completion_kinds else "remaining"
        evidence_items.append(
            {
                "work_id": source_kind,
                "status": status,
                "required_evidence_kind": source_kind,
                "allowed_prefixes": list(requirements["allowed_prefixes"]),
                "minimum_evidence_count": requirements["minimum_evidence_count"],
                "required_fields": list(requirements["required_fields"]),
                "registered_completion_manifest_count": len(matching_manifests),
                "reason": None if status == "completed" else "completion_evidence_manifest_missing",
            }
        )

    non_manifest_items = []
    for work_id, spec in sorted(NON_MANIFEST_REQUIREMENTS.items()):
        status = "completed" if work_id in execution_kinds else "remaining"
        non_manifest_items.append(
            {
                "work_id": work_id,
                "status": status,
                "required_evidence": spec["required_evidence"],
                "completion_condition": spec["completion_condition"],
                "execution_requirements": EXECUTION_EVIDENCE_REQUIREMENTS.get(work_id),
                "registered_execution_evidence_count": sum(
                    1
                    for item in execution_summary["evidence"]
                    if item.get("evidence_kind") == work_id and item.get("exit_code") == 0
                ),
                "reason": None if status == "completed" else "real_execution_evidence_missing",
            }
        )

    remaining_items = [
        item
        for item in [*evidence_items, *non_manifest_items]
        if item["status"] != "completed"
    ]
    report = {
        "remaining_work_status": "complete" if not remaining_items else "incomplete",
        "remaining_count": len(remaining_items),
        "completed_evidence_kind_count": len(completion_kinds),
        "required_evidence_kind_count": len(COMPLETION_EVIDENCE_KINDS),
        "evidence_items": evidence_items,
        "non_manifest_items": non_manifest_items,
        "remaining_items": remaining_items,
        "evidence_summary": evidence_summary,
        "execution_evidence_summary": execution_summary,
        "full_plan_completion_claimed": not remaining_items,
    }
    return report


def assert_plan_remaining_work_complete(*, learning_service: Any) -> dict[str, Any]:
    report = build_plan_remaining_work_report(learning_service=learning_service)
    if report["remaining_work_status"] != "complete":
        raise PlanRemainingWorkError(
            [
                {
                    "reason": "plan_remaining_work_not_complete",
                    "remaining_count": report["remaining_count"],
                    "remaining_work_ids": [item["work_id"] for item in report["remaining_items"]],
                }
            ],
            report,
        )
    return report
